# Current Sprint Tasks

**Sprint:** November 2025 - Week 1  
**Focus:** Data Quality & Automation

## In Progress

### TASK-001: Fix OfferSubtitle Parsing
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** ✅ Complete  
**Effort:** 2 hours  
**Completed:** 2025-11-19

**Objective:**
Update HTML parser to extract rooms/area from OfferSubtitle when OfferTitle has promotional text.

**Acceptance Criteria:**
- [x] Parser checks both OfferTitle and OfferSubtitle
- [x] Prefers OfferSubtitle if it contains property details (regex: `/\d+-комн|м²|этаж/`)
- [x] Implementation complete in `browser_fetcher.py`
- [x] Logic verified and working

**Implementation Steps:**
1. Read current `browser_fetcher.py:224-254`
2. Refactor to check subtitle first, fallback to title
3. Add regex-based heuristic to detect promotional vs. property text
4. Write unit tests with real HTML samples
5. Run integration test: `python -m etl.collector_cian.cli to-db --pages 1`
6. Verify in DB: `SELECT COUNT(*) FROM listings WHERE rooms IS NOT NULL`

**Files to Modify:**
- `etl/collector_cian/browser_fetcher.py` (line 224-254)
- `tests/test_mapper.py` (new tests)

**Related:**
- Bug: `.speckit/bugs/incomplete-data.md`
- Constitution: Data Integrity principle

---

### TASK-007: Restore Address Extraction
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** 🟡 In Progress  
**Effort:** 3 hours  
**Created:** 2025-11-21

**Objective:**
Вернуть ≥90% покрытия адресов в карточках (`offer["address"]`) и детальных данных (`address_full`).

**Acceptance Criteria:**
- [ ] Карточки используют breadcrumbs + специфичные селекторы CIAN (GeoLabel, breadcrumbs).
- [ ] Адрес очищается от «На карте», метро и времени пешком (unit tests).
- [ ] Детальный парсер логирует метод, который дал `address_full`, и заполняет ≥80% объявлений на тестовой странице.
- [ ] В отчёте `ADDRESS_EXTRACTION_PROBLEM.md` отмечено решение (или создан follow-up).

**Implementation Steps:**
1. Проанализировать DOM CIAN и определить основные контейнеры адреса.
2. Добавить сбор всех частей адреса и гибкую валидацию (город/округ/улица/дом).
3. Реализовать функцию `clean_address_text(text: str) -> str` с агрессивной очисткой.
4. Обновить `parse_listing_detail` чтобы использовать breadcrumbs и fallback на атрибуты.
5. Добавитьлогирование и тесты очистки.

**Related:**
- Bug: `.speckit/bugs/address-parser-regression.md`
- Report: `/ADDRESS_EXTRACTION_PROBLEM.md`

---

### TASK-008: Prevent Parser Hang
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** 🟢 Ready  
**Effort:** 2 hours  
**Created:** 2025-11-21

**Objective:**
Исключить одновременный запуск нескольких Playwright-процессов и зависания при долгом парсинге деталей.

**Acceptance Criteria:**
- [ ] CLI захватывает файловый лок (`/tmp/cian_parser.lock`) и завершает второй запуск с понятным сообщением.
- [ ] Есть флаг `--force`/`CIAN_FORCE_RUN=1` для обхода лока вручную.
- [ ] `parse_listing_detail`/детальный парсинг прерывается после выделенного тайм-аута и пишет в лог.
- [ ] Документация (RUNBOOK/README) описывает очистку лока.

**Implementation Steps:**
1. Добавить модуль блокировки (например, `fcntl`/`fasteners`) в `etl/collector_cian/cli.py`.
2. Логировать PID/время, записавшие лок; по провалу — завершать выполнение.
3. Ограничить время обработки одной карточки, выбрасывая кастомное исключение при тайм-ауте.
4. Обновить скрипты/документацию с инструкцией по снятию лока.

**Related:**
- Bug: `.speckit/bugs/parser-hang-multiple-processes.md`
- Report: `/PARSER_ISSUE_REPORT.md`

---

### TASK-009: Autonomous Collector Command
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** 🟡 In Progress  
**Effort:** 4 hours  
**Created:** 2025-11-21

**Objective:**
Добавить CLI-команду, которая собирает до 100 000 объявлений пакетами, отслеживает прогресс и соблюдает тайм-ауты/локи.

**Acceptance Criteria:**
- [ ] Подкоманда `autonomous` с параметрами `--target-offers`, `--pages-per-run`, `--sleep-seconds`, `--max-runtime`.
- [ ] Логи пишутся в `logs/autonomous_collector.log` плюс stdout.
- [ ] После каждого чанка логируется количество объявлений, адресов и процент заполнения.
- [ ] Встроенные ограничения: счётчик неудач, смена прокси, уважение глобального лока.

**Implementation Steps:**
1. Вынести повторяющийся код из `command_to_db` в общую функцию `_collect_and_process`.
2. Реализовать цикл с остановкой по целевому количеству объявлений/времени/итерациям.
3. Добавить дополнительные аргументы в `argparse`.
4. Обновить `RUNBOOK.md` с инструкциями по ручному запуску.

**Related:**
- Spec: `.speckit/specifications/autonomous-parser.md`

---

### TASK-012: Bootstrap PG DSN for Autonomous Runs
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** 🟡 In Progress  
**Effort:** 1 hour  
**Created:** 2025-11-23

**Objective:**
Гарантировать, что автономный сборщик автоматически находит строку подключения к PostgreSQL и не требует ручного экспорта `PG_DSN`.

**Acceptance Criteria:**
- [ ] CLI автоматически загружает `.env`, задокументированный в `PRODUCTION_REQUIREMENTS.md`.
- [ ] `get_db_connection` поддерживает каскадный поиск DSN (`PG_DSN` → `PG_DSN_INTERNAL` → составление из компонент).
- [ ] Лог содержит понятную ошибку, если переменные так и не найдены.
- [ ] В `RUNBOOK.md` описаны шаги по подготовке `.env` перед запуском autonomous.

**Implementation Steps:**
1. Добавить `load_dotenv` в `etl/collector_cian/cli.py`.
2. Реализовать helper для построения DSN в `etl/upsert.py`, включая дефолт для dev.
3. Создать/описать `.env` с локальными credential'ами.
4. Обновить документацию (RUNBOOK) и закрыть баг `.speckit/bugs/pg-dsn-missing.md`.

**Related:**
- Spec: `.speckit/specifications/pg-dsn-bootstrap.md`
- Bug: `.speckit/bugs/pg-dsn-missing.md`

---

### TASK-010: Listing Deduplication
**Priority:** P1 (High)  
**Assignee:** AI Assistant  
**Status:** 🟢 Ready  
**Effort:** 2 hours  
**Created:** 2025-11-21

**Objective:**
Создать сервисный скрипт, который удаляет дубликаты в таблице `listings` по `url`, оставляя свежие записи.

**Acceptance Criteria:**
- [ ] `scripts/deduplicate_listings.py` использует SQL с `ROW_NUMBER()` и отчёт по количеству удалённых строк.
- [ ] Скрипт выполняет `VACUUM ANALYZE listings` после очистки.
- [ ] Команда задокументирована в `RUNBOOK.md`.

---

### TASK-011: Systemd Timer for Autonomous Parser
**Priority:** P1 (High)  
**Assignee:** AI Assistant  
**Status:** 🟢 Ready  
**Effort:** 2 hours  
**Created:** 2025-11-21

**Objective:**
Настроить systemd service + timer, который каждые N минут запускает `cli autonomous` без ручного вмешательства.

**Acceptance Criteria:**
- [ ] Скрипт `scripts/setup_autonomous_parser.sh` создаёт unit и timer.
- [ ] Таймер использует переменные окружения (`CIAN_DETAIL_TIMEOUT`, `CIAN_FORCE_RUN=0`).
- [ ] В `RUNBOOK.md` описаны команды `systemctl status cian-autonomous.service` и `journalctl`.

---

## Backlog (Prioritized)

### TASK-002: Improve Address Extraction
**Priority:** P1 (High)  
**Effort:** 1 hour  
**Status:** ✅ Complete  
**Completed:** 2025-11-19

**Description:**
Current address extraction misses some listings. Add fallback selectors and validation.

**Steps:**
- [x] Try multiple selectors: `[data-name='GeoLabel']`, `[data-name='SpecialGeo']`
- [x] Validate: address must contain "Москва" or metro station name
- [x] Log warnings for missing addresses
- [x] Fallback to geo-related CSS classes

---

### TASK-003: Enable --parse-details by Default
**Priority:** P1 (High)  
**Effort:** 4 hours

**Description:**
Make detailed parsing (photos, descriptions, dates) the default behavior.

**Steps:**
- Update CLI arg parser default value
- Test performance impact (should be <5 min for 4 pages)
- Update README with new behavior
- Add monitoring for detail parsing failures

---

### TASK-004: Setup Automated Daily Scraping
**Priority:** P2 (Medium)  
**Effort:** 2 hours  
**Status:** ✅ Complete  
**Completed:** 2025-11-19

**Description:**
Configure systemd timer to run scraper daily at 3 AM Moscow time.

**Steps:**
- [x] Create systemd service file
- [x] Create timer file
- [x] Create setup script
- [x] Ready for installation

**Files:**
- `infra/systemd/cian-scraper.service` - systemd service
- `infra/systemd/cian-scraper.timer` - systemd timer
- `scripts/setup_daily_scraper.sh` - installation script

**Usage:**
```bash
sudo ./scripts/setup_daily_scraper.sh
```

---

### TASK-005: Add Data Quality Metrics
**Priority:** P2 (Medium)  
**Effort:** 3 hours  
**Status:** ✅ Complete  
**Completed:** 2025-11-19

**Description:**
Create SQL view and logging for data completeness tracking.

**SQL View:**
- [x] Created `data_quality_metrics` view
- [x] Created `data_quality_metrics_recent` view (last 7 days)
- [x] Created `apartment_shares_detected` view
- [x] Added logging to `cli.py` after upsert
- [x] Created script `apply_data_quality_views.sh`

**Files:**
- `db/views_data_quality.sql` - SQL views
- `etl/collector_cian/cli.py` - logging added
- `scripts/apply_data_quality_views.sh` - setup script

---

### TASK-006: Write Integration Tests
**Priority:** P2 (Medium)  
**Effort:** 4 hours

**Test Cases:**
- End-to-end: Scrape 1 page → Verify DB insert
- Proxy failure → Retry with different proxy
- CAPTCHA encountered → Solve and continue
- Duplicate listing → Update price, don't create new row

---

## Completed ✅

- ✅ TASK-000: Setup SpecKit structure (2025-11-03)

---

**Notes:**
- Use `/speckit.implement TASK-XXX` to auto-implement tasks
- Update status as work progresses
- Link commits to task IDs in commit messages
