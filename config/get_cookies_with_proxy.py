#!/usr/bin/env python3
"""
Получение cookies через прокси для дальнейшего использования БЕЗ прокси.

ВАЖНО: Этот скрипт должен запускаться РЕДКО (раз в день/неделю).
Все остальные запросы должны идти БЕЗ прокси, используя сохраненные cookies.
"""
import sys
import os
import random
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright, Page
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOGGER = logging.getLogger(__name__)

STORAGE_STATE_PATH = Path(__file__).parent / "cian_browser_state.json"


def get_cookies_with_proxy(save_to: str = str(STORAGE_STATE_PATH)):
    """
    Получить cookies через прокси и сохранить для дальнейшего использования БЕЗ прокси.

    Процесс:
    1. Загрузить прокси из пула
    2. Запустить браузер С ПРОКСИ + stealth fingerprint
    3. Открыть CIAN с имитацией человеческого поведения
    4. Сохранить cookies/storage state
    5. Эти cookies использовать для всех последующих запросов БЕЗ прокси

    Parameters
    ----------
    save_to : str
        Путь для сохранения cookies
    """
    from etl.collector_cian.proxy_manager import ProxyRotator, ProxyConfig
    from etl.collector_cian.browser_fetcher import setup_route_blocking
    from etl.antibot.fingerprint import create_stealth_context
    from etl.antibot.behavior import HumanBehavior, BehaviorPresets

    LOGGER.info("=" * 60)
    LOGGER.info("🔐 Получение cookies через прокси (с имитацией поведения)")
    LOGGER.info("=" * 60)

    # Инициализировать ротатор прокси
    try:
        rotator = ProxyRotator()
        stats = rotator.get_stats()
        LOGGER.info(f"📊 Прокси пул: {stats['available_proxies']}/{stats['total_proxies']} доступно")

        # Получить прокси
        proxy_url = rotator.get_next_proxy()

        if not proxy_url:
            LOGGER.error("❌ Нет доступных прокси!")
            LOGGER.info("💡 Запустите: python config/refresh_proxies.py")
            return False

        proxy_config = ProxyConfig.from_url(proxy_url)
        LOGGER.info(f"✅ Используем прокси: {proxy_config.server}")

    except Exception as e:
        LOGGER.error(f"❌ Ошибка при инициализации прокси: {e}")
        LOGGER.info("💡 Попробуем без прокси...")
        proxy_config = None

    # Запустить браузер
    with sync_playwright() as p:
        try:
            if proxy_config:
                LOGGER.info("🌐 Запуск браузера С ПРОКСИ...")
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                    proxy={
                        "server": proxy_config.server,
                        "username": proxy_config.username,
                        "password": proxy_config.password,
                    }
                )
            else:
                LOGGER.info("🌐 Запуск браузера БЕЗ ПРОКСИ (fallback)...")
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ]
                )

            # КРИТИЧНО: Создаём stealth context с fingerprint painting
            LOGGER.info("🎭 Создание stealth context с fingerprint...")
            context = create_stealth_context(browser)

            # Блокировать все запросы кроме www.cian.ru при использовании прокси
            if proxy_config:
                setup_route_blocking(context)

            page = context.new_page()

            # Открыть CIAN для получения cookies
            LOGGER.info("📥 Загрузка CIAN для получения cookies...")
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"

            try:
                response = page.goto(url, wait_until="load", timeout=60000)

                if response and response.status >= 400:
                    LOGGER.error(f"❌ Ошибка HTTP {response.status}")
                    return False

                # КРИТИЧНО: Имитация человеческого поведения
                LOGGER.info("🎭 Имитация человеческого поведения...")
                behavior = HumanBehavior(BehaviorPresets.cautious())

                # Начальная пауза как у реального пользователя
                behavior.random_delay()

                # Движение мыши
                behavior.random_mouse_movement(page)
                time.sleep(random.uniform(0.5, 1.0))

                # Скролл вниз (как будто смотрим объявления)
                behavior.scroll_page(page, direction="down", distance=random.randint(300, 800))
                behavior.random_delay()

                # Ещё движение мыши
                behavior.random_mouse_movement(page)
                time.sleep(random.uniform(0.3, 0.7))

                # Скролл обратно вверх
                behavior.scroll_page(page, direction="up", distance=random.randint(100, 300))

                # Имитация чтения страницы
                behavior.simulate_reading(page, random.randint(500, 1500))

                # Финальное движение мыши
                behavior.random_mouse_movement(page)

                # Проверить что страница загрузилась (не капча)
                title = page.title()
                LOGGER.info(f"📄 Страница: {title[:50]}...")

                # Если капча - пробуем ещё раз с дополнительной имитацией
                if "captcha" in title.lower():
                    LOGGER.warning("⚠️ Обнаружена капча, дополнительная имитация...")
                    behavior.page_interaction_sequence(page)
                    page.reload(wait_until="load")
                    time.sleep(random.uniform(2, 4))
                    behavior.random_mouse_movement(page)
                    behavior.scroll_page(page, direction="down", distance=400)
                    title = page.title()
                    LOGGER.info(f"📄 После перезагрузки: {title[:50]}...")

                # Проверяем успех
                if "captcha" in title.lower():
                    LOGGER.error("❌ Не удалось обойти капчу")
                    return False

                # Сохранить cookies и storage state
                LOGGER.info(f"💾 Сохранение cookies в {save_to}...")
                context.storage_state(path=save_to)

                # Проверить что файл создан
                if os.path.exists(save_to):
                    file_size = os.path.getsize(save_to)
                    LOGGER.info(f"✅ Cookies сохранены успешно ({file_size} bytes)")
                    LOGGER.info("")
                    LOGGER.info("=" * 60)
                    LOGGER.info("🎉 ГОТОВО! Cookies получены через прокси")
                    LOGGER.info("=" * 60)
                    LOGGER.info("")
                    LOGGER.info("💡 Теперь вы можете парсить БЕЗ прокси:")
                    LOGGER.info("   python -m etl.collector_cian.cli to-db --pages 10 --parse-details")
                    LOGGER.info("")
                    LOGGER.info("⚠️  Эти cookies действительны ~24 часа")
                    LOGGER.info("⚠️  Обновляйте cookies раз в день через этот скрипт")
                    LOGGER.info("")
                    return True
                else:
                    LOGGER.error("❌ Файл cookies не создан!")
                    return False

            except Exception as e:
                LOGGER.error(f"❌ Ошибка при загрузке страницы: {e}")
                return False

        except Exception as e:
            LOGGER.error(f"❌ Ошибка при запуске браузера: {e}")
            return False

        finally:
            try:
                browser.close()
            except:
                pass


def check_cookies_age():
    """Проверить возраст сохраненных cookies."""
    if not STORAGE_STATE_PATH.exists():
        LOGGER.warning("⚠️  Cookies не найдены!")
        return None

    import time
    age_seconds = time.time() - STORAGE_STATE_PATH.stat().st_mtime
    age_hours = age_seconds / 3600

    if age_hours > 24:
        LOGGER.warning(f"⚠️  Cookies устарели ({age_hours:.1f} часов). Рекомендуется обновить!")
        return age_hours
    else:
        LOGGER.info(f"✅ Cookies актуальны ({age_hours:.1f} часов)")
        return age_hours


def refresh_cookies_if_needed(force: bool = False) -> bool:
    """
    Обновить cookies через прокси если нужно.

    Используется для автоматического восстановления при блокировке.

    Parameters
    ----------
    force : bool
        Принудительно обновить, даже если cookies актуальны

    Returns
    -------
    bool
        True если cookies обновлены успешно
    """
    if not force and STORAGE_STATE_PATH.exists():
        age = check_cookies_age()
        if age and age < 12:  # Обновляем если старше 12 часов при авто-обновлении
            LOGGER.info("✅ Cookies актуальны, обновление не требуется")
            return True

    LOGGER.info("🔄 Автоматическое обновление cookies через прокси...")
    return get_cookies_with_proxy(str(STORAGE_STATE_PATH))


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Получить cookies через прокси для дальнейшего использования БЕЗ прокси")
    parser.add_argument("--check", action="store_true", help="Только проверить возраст cookies")
    parser.add_argument("--force", action="store_true", help="Принудительно обновить cookies")
    parser.add_argument("--output", default=str(STORAGE_STATE_PATH), help="Путь для сохранения cookies")
    
    args = parser.parse_args()
    
    if args.check:
        age = check_cookies_age()
        if age is None:
            LOGGER.info("💡 Запустите без --check для получения cookies")
            sys.exit(1)
        elif age > 24:
            LOGGER.info("💡 Запустите без --check для обновления cookies")
            sys.exit(1)
        else:
            sys.exit(0)
    
    # Проверить нужно ли обновлять
    if not args.force and STORAGE_STATE_PATH.exists():
        age = check_cookies_age()
        if age and age < 24:
            LOGGER.info("✅ Cookies еще актуальны, обновление не требуется")
            LOGGER.info("💡 Используйте --force для принудительного обновления")
            sys.exit(0)
    
    # Получить cookies
    success = get_cookies_with_proxy(args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

