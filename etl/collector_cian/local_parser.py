#!/usr/bin/env python3
"""
Локальные мини-парсеры для конкретных регионов/адресов.

АРХИТЕКТУРА:
═══════════════════════════════════════════════════════════════════════════════
1. ПРОКСИ = ТОЛЬКО ДЛЯ COOKIES (через get_cookies_with_proxy.py)
2. ПАРСИНГ = ВСЕГДА БЕЗ ПРОКСИ (используем сохранённые cookies)
3. Используем существующую инфраструктуру: mapper, upsert, browser_fetcher
═══════════════════════════════════════════════════════════════════════════════

ИСПОЛЬЗОВАНИЕ:
    # Парсинг Дмитровского района
    python -m etl.collector_cian.local_parser --location dmitrov --pages 10

    # Парсинг конкретного города
    python -m etl.collector_cian.local_parser --subdomain yahroma --pages 5

    # Кастомный URL
    python -m etl.collector_cian.local_parser --url "https://www.cian.ru/cat.php?..." --pages 3
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, Page

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from etl.collector_cian.browser_fetcher import (
    _parse_offers_from_html,
    clean_address_text,
)
from etl.collector_cian.mapper import to_listing, to_price
from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed

LOGGER = logging.getLogger(__name__)

# Конфигурация локаций
# Ключ = короткое имя, значение = dict с параметрами
LOCATIONS = {
    "dmitrov": {
        "name": "Дмитровский район МО",
        "subdomain": None,  # Используем www.cian.ru
        "region": 4593,     # Московская область
        "address_filters": ["дмитров", "яхром", "икша", "некрасов", "деденев", "рогачёв"],
        "description": "Дмитров, Яхрома, Икша и окрестности",
    },
    "yahroma": {
        "name": "Яхрома",
        "subdomain": "yahroma",  # yahroma.cian.ru
        "region": None,
        "address_filters": ["яхром"],
        "description": "Город Яхрома",
    },
    "serpuhov": {
        "name": "Серпухов",
        "subdomain": "serpuhov",
        "region": None,
        "address_filters": ["серпухов"],
        "description": "Серпухов и район",
    },
    "kolomna": {
        "name": "Коломна",
        "subdomain": "kolomna",
        "region": None,
        "address_filters": ["коломн"],
        "description": "Коломна и район",
    },
}

DEFAULT_STORAGE_PATH = Path(__file__).resolve().parents[2] / "config/cian_browser_state.json"


def build_local_url(
    location_key: str = None,
    subdomain: str = None,
    region: int = None,
    page: int = 1,
    deal_type: str = "sale",
    offer_type: str = "flat",
    secondary_only: bool = True,
    rooms: List[int] = None,
) -> str:
    """
    Строит URL для локального парсера.

    Parameters
    ----------
    location_key : str
        Ключ из LOCATIONS dict
    subdomain : str
        Поддомен ЦИАН (dmitrov, yahroma, etc.)
    region : int
        ID региона (4593 = МО)
    page : int
        Номер страницы
    """
    query = {
        "deal_type": deal_type,
        "engine_version": 2,
        "offer_type": offer_type,
        "sort": "creation_date_desc",
        "p": page,
    }

    # Определяем базовый домен
    base_domain = "www.cian.ru"

    if location_key and location_key in LOCATIONS:
        loc = LOCATIONS[location_key]
        if loc.get("subdomain"):
            base_domain = f"{loc['subdomain']}.cian.ru"
        if loc.get("region"):
            query["region"] = loc["region"]
    elif subdomain:
        base_domain = f"{subdomain}.cian.ru"

    if region:
        query["region"] = region

    # Вторичка
    if secondary_only:
        query["object_type[0]"] = 1

    # Комнаты
    if rooms:
        for r in rooms:
            query[f"room{r}"] = 1
    else:
        # По умолчанию все комнаты
        for r in [0, 1, 2, 3, 4, 5, 6]:
            query[f"room{r}"] = 1

    params = urlencode(query, doseq=True)
    return f"https://{base_domain}/cat.php?{params}"


def parse_page(page: Page, url: str) -> List[Dict[str, Any]]:
    """
    Парсит одну страницу и возвращает offers.

    Использует _parse_offers_from_html из browser_fetcher.
    """
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if not response:
            LOGGER.warning(f"Нет ответа от {url}")
            return []

        if response.status == 429:
            LOGGER.error(f"❌ Rate limit (429)! Нужно обновить cookies.")
            LOGGER.info("💡 Запустите: python config/get_cookies_with_proxy.py")
            return []

        if response.status >= 400:
            LOGGER.warning(f"HTTP {response.status} для {url}")
            return []

        # Ждём загрузку контента
        page.wait_for_timeout(2000)

        # Парсим через существующую функцию
        offers = _parse_offers_from_html(page)
        return offers

    except Exception as e:
        LOGGER.error(f"Ошибка парсинга {url}: {e}")
        return []


def filter_by_address(offers: List[Dict], address_filters: List[str]) -> List[Dict]:
    """
    Фильтрует offers по адресу.

    Parameters
    ----------
    offers : list
        Список объявлений
    address_filters : list
        Список подстрок для поиска в адресе (lowercase)
    """
    if not address_filters:
        return offers

    filtered = []
    for offer in offers:
        address = (offer.get("address") or "").lower()
        if any(f in address for f in address_filters):
            filtered.append(offer)

    return filtered


def save_to_db(offers: List[Dict]) -> tuple[int, int]:
    """
    Сохраняет offers в БД через существующий upsert.

    Returns
    -------
    tuple
        (saved_count, price_updates_count)
    """
    conn = get_db_connection()
    saved = 0
    prices = 0

    try:
        for offer in offers:
            try:
                listing = to_listing(offer)
                price = to_price(offer)

                upsert_listing(conn, listing)
                saved += 1

                if upsert_price_if_changed(conn, listing.id, price.price):
                    prices += 1

            except ValueError as e:
                # Skip newbuildings, shares, etc.
                LOGGER.debug(f"Пропуск: {e}")
                continue
            except Exception as e:
                LOGGER.warning(f"Ошибка сохранения offer: {e}")
                continue

        conn.commit()

    except Exception as e:
        conn.rollback()
        LOGGER.error(f"Ошибка при сохранении: {e}")
    finally:
        conn.close()

    return saved, prices


def collect_local(
    location_key: str = None,
    subdomain: str = None,
    custom_url: str = None,
    pages: int = 10,
    address_filters: List[str] = None,
    save: bool = True,
) -> List[Dict]:
    """
    Главная функция сбора данных для локального региона.

    ВАЖНО: Работает БЕЗ ПРОКСИ, используя сохранённые cookies!

    Parameters
    ----------
    location_key : str
        Ключ локации из LOCATIONS
    subdomain : str
        Поддомен ЦИАН
    custom_url : str
        Кастомный URL (без параметра page)
    pages : int
        Количество страниц
    address_filters : list
        Фильтры адресов
    save : bool
        Сохранять в БД

    Returns
    -------
    list
        Все собранные offers
    """
    storage_path = Path(os.getenv("CIAN_STORAGE_STATE", str(DEFAULT_STORAGE_PATH)))

    if not storage_path.exists():
        LOGGER.error(f"❌ Cookies не найдены: {storage_path}")
        LOGGER.info("💡 Сначала получите cookies: python config/get_cookies_with_proxy.py")
        return []

    # Проверяем возраст cookies
    age_hours = (time.time() - storage_path.stat().st_mtime) / 3600
    if age_hours > 24:
        LOGGER.warning(f"⚠️ Cookies устарели ({age_hours:.1f} часов)")
        LOGGER.info("💡 Рекомендуется обновить: python config/get_cookies_with_proxy.py")

    # Определяем фильтры адресов
    if address_filters is None and location_key and location_key in LOCATIONS:
        address_filters = LOCATIONS[location_key].get("address_filters", [])

    location_name = "Custom"
    if location_key and location_key in LOCATIONS:
        location_name = LOCATIONS[location_key]["name"]
    elif subdomain:
        location_name = subdomain.capitalize()

    LOGGER.info("=" * 60)
    LOGGER.info(f"🏠 Локальный парсер: {location_name}")
    LOGGER.info("=" * 60)
    LOGGER.info(f"📄 Страниц: {pages}")
    LOGGER.info(f"🔍 Фильтры адресов: {address_filters or 'нет'}")
    LOGGER.info(f"📂 Cookies: {storage_path}")
    LOGGER.info(f"💾 Сохранение в БД: {'да' if save else 'нет'}")
    LOGGER.info("")

    all_offers = []

    with sync_playwright() as p:
        # ВАЖНО: Запуск БЕЗ ПРОКСИ!
        LOGGER.info("🔓 Запуск браузера БЕЗ ПРОКСИ (используем cookies)")
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            storage_state=str(storage_path),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = context.new_page()

        for page_num in range(1, pages + 1):
            # Строим URL
            if custom_url:
                url = custom_url + f"&p={page_num}" if "?" in custom_url else custom_url + f"?p={page_num}"
            else:
                url = build_local_url(
                    location_key=location_key,
                    subdomain=subdomain,
                    page=page_num,
                )

            LOGGER.info(f"📄 Страница {page_num}/{pages}")

            offers = parse_page(page, url)

            if not offers:
                LOGGER.info(f"  ⚠️ Нет объявлений, останавливаемся")
                break

            # Фильтруем по адресу
            if address_filters:
                filtered = filter_by_address(offers, address_filters)
                LOGGER.info(f"  ✓ Найдено {len(offers)} → отфильтровано {len(filtered)}")
                all_offers.extend(filtered)

                # Логируем найденные
                for o in filtered[:3]:
                    addr = o.get("address", "N/A")[:50]
                    price = o.get("price", 0)
                    LOGGER.info(f"    • {addr} - {price:,} ₽")
            else:
                all_offers.extend(offers)
                LOGGER.info(f"  ✓ Найдено {len(offers)} объявлений")

            # Пауза между страницами
            time.sleep(2)

        browser.close()

    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info(f"📊 ИТОГО: {len(all_offers)} объявлений")

    if save and all_offers:
        saved, prices = save_to_db(all_offers)
        LOGGER.info(f"💾 Сохранено: {saved} листингов, {prices} новых цен")

    LOGGER.info("=" * 60)

    return all_offers


def main():
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Локальный парсер ЦИАН для конкретных регионов (БЕЗ ПРОКСИ)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python -m etl.collector_cian.local_parser --location dmitrov --pages 10
  python -m etl.collector_cian.local_parser --subdomain yahroma --pages 5
  python -m etl.collector_cian.local_parser --url "https://www.cian.ru/cat.php?..." --pages 3

Доступные локации:
""" + "\n".join(f"  {k}: {v['description']}" for k, v in LOCATIONS.items())
    )

    parser.add_argument(
        "--location", "-l",
        choices=list(LOCATIONS.keys()),
        help="Предустановленная локация",
    )
    parser.add_argument(
        "--subdomain", "-s",
        help="Поддомен ЦИАН (dmitrov, yahroma, etc.)",
    )
    parser.add_argument(
        "--url", "-u",
        help="Кастомный URL (без параметра page)",
    )
    parser.add_argument(
        "--pages", "-p",
        type=int,
        default=10,
        help="Количество страниц (default: 10)",
    )
    parser.add_argument(
        "--filter", "-f",
        action="append",
        dest="filters",
        help="Фильтр по адресу (можно указать несколько)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять в БД",
    )
    parser.add_argument(
        "--list-locations",
        action="store_true",
        help="Показать доступные локации",
    )

    args = parser.parse_args()

    if args.list_locations:
        print("\nДоступные локации:")
        print("=" * 50)
        for key, loc in LOCATIONS.items():
            print(f"  {key:15} - {loc['description']}")
            if loc.get("subdomain"):
                print(f"                   → {loc['subdomain']}.cian.ru")
            if loc.get("address_filters"):
                print(f"                   → фильтры: {', '.join(loc['address_filters'])}")
        print()
        return

    if not args.location and not args.subdomain and not args.url:
        parser.error("Укажите --location, --subdomain или --url")

    offers = collect_local(
        location_key=args.location,
        subdomain=args.subdomain,
        custom_url=args.url,
        pages=args.pages,
        address_filters=args.filters,
        save=not args.no_save,
    )

    LOGGER.info(f"\n✅ Готово! Собрано {len(offers)} объявлений")


if __name__ == "__main__":
    main()
