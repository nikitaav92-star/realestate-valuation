
## Сбор данных CIAN
1. Установите зависимости: `pip install -r requirements.txt`.
2. Подготовьте браузер Playwright: `playwright install chromium`.
3. Команда сбора: `python -m etl.collector_cian.cli pull --pages 1`.
   - При блокировке HTTP-клиента скрипт автоматически переключится на Playwright.
   - Для ручного прохождения капчи можно запустить `CIAN_HEADLESS=false python -m etl.collector_cian.cli pull ...` (см. код).
   - Для авторизованных запросов Playwright читает `CIAN_COOKIES` или `CIAN_STORAGE_STATE` (путь к `storage-state.json`).

## Публикация на домене
См. `infra/README.md`.
Кратко: DNS A → IP VPS; Nginx+Certbot; Metabase: https://realestate.ourdocs.org/ ; Prefect: https://realestate.ourdocs.org/prefect/
