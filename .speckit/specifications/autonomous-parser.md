# Specification: Autonomous CIAN Parser

**Status:** Draft  
**Author:** AI Assistant  
**Date:** 2025-11-21  

## 1. Purpose
- Восстановить и удерживать ≥90 % заполненных адресов на карточках и детальных страницах.
- Гарантированно собирать большие объёмы (до 100 000 объявлений) без ручного вмешательства.
- Нормализовать адреса через ФИАС сразу после детального парсинга.
- Обеспечить автоматический запуск каждые N минут и защиту от зависаний/двойных запусков.

## 2. Requirements
1. **Address coverage**
   - Минимум 24 объявления в выборке (≈1 страница) заполняются адресами.
   - Для ≥100 объявлений сохраняются `address_full` и `fias_address`.
2. **Mass collection**
   - CLI-команда, которая собирает до 100 000 объявлений пакетами (страницы × чанки), автоматически возобновляется и пишет прогресс в лог.
   - Паузы между чанками и смена прокси при повторных ошибках.
3. **Deduplication**
   - Скрипт, удаляющий дубликаты по `url`, оставляя последнюю запись (по `updated_at`).
4. **Scheduling**
   - systemd-service + timer, запускающий автономную команду каждые X минут.
5. **Observability**
   - Логи в `logs/autonomous_collector.log` + стандартный stdout.
   - Сводка по количеству собранных объявлений, адресов и нормализованных записей.

## 3. Architecture
### Components
1. `etl/collector_cian/browser_fetcher.py`
   - Уже содержит улучшения адресов и тайм-аутов.
2. `etl/collector_cian/cli.py`
   - **Новая подкоманда `autonomous`**:
     - Параметры: `--target-offers`, `--pages-per-run`, `--sleep-seconds`, `--max-runtime`, `--parse-details`.
     - Использует существующие функции `_collect_responses()` + `_process_offers()`.
     - Логирует прогресс, метрики адресов и вызывает нормализацию ФИАС по мере появления `address_full`.
3. `scripts/deduplicate_listings.py`
   - Запускает SQL с `ROW_NUMBER()` для удаления дублей по `url`.
   - После удаления выполняет `VACUUM ANALYZE listings`.
4. `scripts/setup_autonomous_parser.sh`
   - Устанавливает systemd unit + timer, указывая `python3 -m etl.collector_cian.cli autonomous`.
   - Принимает параметры: интервал запуска, pages per run, target offers per iteration.
5. `RUNBOOK.md`
   - Разделы:
     - Как запускать `autonomous` вручную.
     - Как включать/отключать таймер.
     - Как запускать дедупликацию.
6. `.speckit/tasks/current-sprint.md`
   - Задачи: `TASK-009 Autonomous Collector`, `TASK-010 Deduplication Script`, `TASK-011 Timer Setup`.

### Data flow (Autonomous Command)
```
payload.yaml -> command_autonomous()
    -> asyncio.collect(payload, pages_per_run) OR Playwright fallback
    -> _process_offers() -> PostgreSQL
    -> (optional) normalize_address() for records with address_full
    -> log progress & stats
    -> sleep -> next chunk
```

### Error handling
- Глобальный файловый лок (`/tmp/cian_parser.lock`) предотвращает параллельные запуски.
- Внутри автономного цикла: счётчик неудач → смена прокси → пропуск чанка после max_failures.
- Тайм-ауты на детальном парсинге уже заданы (`CIAN_DETAIL_TIMEOUT`).

## 4. Metrics & Acceptance
1. **24 объявлений**: после `--pages 1` метрика `pct_address >= 90`.
2. **100 объявлений**: `autonomous --target-offers 100 --pages-per-run 5` -> `fias_address` заполнен минимум у 80% записей.
3. **100k**: `autonomous --target-offers 100000 --pages-per-run 50 --sleep 30` завершает цикл без ручного вмешательства (проверяется в тестовом окружении).
4. **Deduplication**:
   - До запуска: `SELECT COUNT(*) - COUNT(DISTINCT url) FROM listings;`
   - После: значение должно быть 0.
5. **Scheduler**:
   - `systemctl list-timers | grep cian-autonomous` показывает активный таймер.
   - Журналы `journalctl -u cian-autonomous.service -n 20` содержат прогресс.

## 5. Testing Strategy
1. **Unit**:
   - мок `command_autonomous` с фейковым `_process_offers` → проверка остановки по `target_offers`.
   - дедупликация: создать временные записи, убедиться, что остаётся одна запись на `url`.
2. **Integration (manual)**:
   - `python3 -m etl.collector_cian.cli autonomous --target-offers 120 --pages-per-run 6`.
   - Проверить таблицы `listings` и `listing_details`.
   - Выполнить `python3 scripts/deduplicate_listings.py`.
3. **Operational**:
   - Установить таймер, перезагрузить сервис, убедиться, что лок блокирует параллельные запуски.

## 6. Open Questions / Risks
- CIAN может ограничивать доступ при массивных запросах → необходимо следить за паузами, ротацией прокси и, возможно, добавлять случайное `sleep`.
- Для дедупликации важно не удалить «исторические» записи, если они необходимы для аналитики — скрипт должен работать только по действующей таблице `listings` (где лежит активная запись).
- Необходимость в очередях/redis? Пока откладываем, т.к. однопоточный режим достаточно стабильный.




