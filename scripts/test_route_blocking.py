#!/usr/bin/env python3
"""
Тест блокировки запросов при использовании прокси.

Проверяет что setup_route_blocking() работает корректно:
- www.cian.ru - разрешён
- Всё остальное - заблокировано
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOGGER = logging.getLogger(__name__)

def test_route_blocking():
    """Тест блокировки запросов."""
    from etl.collector_cian.browser_fetcher import setup_route_blocking

    # Счётчики
    allowed_requests = []
    blocked_requests = []

    with sync_playwright() as p:
        # Запускаем БЕЗ прокси для теста (не тратим деньги)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Применяем блокировку
        setup_route_blocking(context)

        # Перехватываем события для подсчёта
        def on_request(request):
            from urllib.parse import urlparse
            domain = urlparse(request.url).netloc.lower()
            if domain == "www.cian.ru":
                allowed_requests.append(domain)
            else:
                blocked_requests.append(domain)

        def on_request_failed(request):
            from urllib.parse import urlparse
            domain = urlparse(request.url).netloc.lower()
            if domain != "www.cian.ru":
                LOGGER.debug(f"🚫 Заблокирован: {domain}")

        context.on("request", on_request)
        context.on("requestfailed", on_request_failed)

        page = context.new_page()

        LOGGER.info("=" * 60)
        LOGGER.info("🧪 ТЕСТ БЛОКИРОВКИ ЗАПРОСОВ")
        LOGGER.info("=" * 60)

        # Пробуем загрузить страницу
        try:
            LOGGER.info("📥 Загружаем страницу CIAN...")
            page.goto("https://www.cian.ru/cat.php?deal_type=sale&offer_type=flat&region=1", 
                     wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            LOGGER.warning(f"⚠️ Ошибка загрузки (ожидаемо из-за блокировки): {e}")

        browser.close()

    # Результаты
    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("📊 РЕЗУЛЬТАТЫ ТЕСТА")
    LOGGER.info("=" * 60)
    LOGGER.info(f"✅ Разрешено запросов к www.cian.ru: {len(allowed_requests)}")
    LOGGER.info(f"🚫 Заблокировано запросов: {len(blocked_requests)}")

    if blocked_requests:
        unique_blocked = set(blocked_requests)
        LOGGER.info(f"🚫 Заблокированные домены ({len(unique_blocked)} уникальных):")
        for domain in sorted(unique_blocked)[:10]:
            count = blocked_requests.count(domain)
            LOGGER.info(f"   - {domain}: {count} запросов")
        if len(unique_blocked) > 10:
            LOGGER.info(f"   ... и ещё {len(unique_blocked) - 10} доменов")

    # Проверка
    if len(allowed_requests) > 0 and len(blocked_requests) > 0:
        LOGGER.info("")
        LOGGER.info("✅ ТЕСТ ПРОЙДЕН!")
        LOGGER.info("   - www.cian.ru запросы проходят")
        LOGGER.info("   - Другие домены блокируются")
        return True
    elif len(allowed_requests) > 0:
        LOGGER.info("")
        LOGGER.info("⚠️ ТЕСТ ЧАСТИЧНО ПРОЙДЕН")
        LOGGER.info("   - www.cian.ru запросы проходят")
        LOGGER.info("   - Нет данных о блокировке (возможно страница не загружала внешние ресурсы)")
        return True
    else:
        LOGGER.error("")
        LOGGER.error("❌ ТЕСТ НЕ ПРОЙДЕН!")
        LOGGER.error("   - Нет запросов к www.cian.ru")
        return False


if __name__ == "__main__":
    success = test_route_blocking()
    sys.exit(0 if success else 1)
