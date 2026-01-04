# Bug: Parser Hang Due to Multiple Concurrent Processes

**Status:** Open  
**Priority:** P0  
**Created:** 2025-11-21  
**Owner:** AI Assistant  

## Description
- В Cursor запускаются несколько экземпляров Playwright-парсера (`python -m etl.collector_cian.cli ...`) почти одновременно.
- Каждый процесс открывает собственный Chromium + прокси, что съедает CPU/GPU и своп.
- При 2-3 процессах renderer Chrome занимает ~98% CPU → IDE зависает, команды не завершаются.
- Нет механизма блокировки или pid-файла, который запрещает повторный запуск.

## Impact
- Парсер зависает, приходится принудительно убивать процессы.
- Поток данных в `listings`/`listings_details` останавливается.
- Сбои в расписании systemd, потому что второй запуск висит, пока первый не завершится.

## Root Cause
1. `etl/collector_cian/cli.py` не проверяет, запущен ли уже другой процесс (нет file lock / pidfile).
2. Потоки Playwright используют бесконечные ожидания при парсинге деталей (нет глобального тайм-аута на объявление).
3. Интеграционные скрипты (`scripts/run_parser.sh`, systemd timer) могут стартовать повторно ещё до завершения предыдущего прохода.

## Proposed Solution
1. **Global Lock**
   - Реализовать файловый или PID-лок (`/tmp/cian_parser.lock`) через `fasteners` или стандартный `fcntl`.
   - При запуске CLI пытаться захватить лок → если уже занят, аккуратно выходить с кодом 1 и сообщением.
2. **Per-listing timeout**
   - Обернуть `parse_listing_detail` в `asyncio.wait_for` / ручной `time.perf_counter` с прерыванием после, например, 20 секунд.
   - Если тайм-аут, логировать предупреждение и продолжать к следующему объявлению.
3. **Command-line safeguards**
   - Флаг `--force` (или `CIAN_FORCE_RUN=1`) чтобы принудительно отключить лок, если нужно при отладке.
   - Логирование источника блокировки (PID, время запуска) для диагностики.
4. **Documentation**
   - Добавить раздел в `RUNBOOK.md`/`scripts/README` как очищать лок, если процесс упал.

## Test Cases
1. Запустить CLI дважды подряд: второй запуск должен завершиться за <1 секунды с сообщением «парсер уже запущен».
2. Смоделировать зависание в `parse_listing_detail` (например, `page.goto` не отвечает) → через N секунд логируется timeout и цикл продолжает работу.
3. Systemd timer: `systemctl start cian-scraper` два раза подряд → второй логирует блокировку, но не создаёт новый процесс Playwright.

## References
- `/PARSER_ISSUE_REPORT.md`
- `.speckit/tasks/current-sprint.md`

