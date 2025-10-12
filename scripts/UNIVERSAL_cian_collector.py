#!/usr/bin/env python3
"""
УНИВЕРСАЛЬНЫЙ сборщик данных CIAN - пробует разные селекторы.
"""

import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def extract_with_multiple_selectors(page) -> List[Dict[str, Any]]:
    """Пробует разные селекторы для извлечения данных."""
    
    # Список возможных селекторов для карточек объявлений
    card_selectors = [
        '[data-name="OfferCard"]',
        '[data-name="LinkArea"]',
        '.c6e8ba5398--card',
        '.offer-card',
        '.listing-card',
        '[data-testid="offer-card"]',
        '.offer',
        '.listing',
        'article',
        '.card'
    ]
    
    for selector in card_selectors:
        try:
            LOGGER.info(f"🔍 Пробуем селектор: {selector}")
            
            # Проверяем есть ли элементы
            elements = page.query_selector_all(selector)
            if elements:
                LOGGER.info(f"✅ Найдено {len(elements)} элементов с селектором: {selector}")
                
                # Извлекаем данные
                offers_data = page.evaluate(f"""
                    () => {{
                        const cards = document.querySelectorAll('{selector}');
                        const realOffers = [];
                        
                        console.log('Found cards with selector {selector}:', cards.length);
                        
                        cards.forEach((card, index) => {{
                            try {{
                                // Ищем ссылку
                                const linkEl = card.querySelector('a[href*="cian.ru"]') ||
                                             card.querySelector('a[href*="/sale/flat/"]') ||
                                             card.querySelector('a[href*="/rent/flat/"]') ||
                                             card.querySelector('a');
                                
                                if (!linkEl) {{
                                    console.log('No link found for card', index);
                                    return;
                                }}
                                
                                const url = linkEl.href;
                                
                                // Ищем данные в разных местах
                                const titleEl = card.querySelector('h3') ||
                                             card.querySelector('h2') ||
                                             card.querySelector('.title') ||
                                             card.querySelector('[data-mark="OfferTitle"]') ||
                                             card.querySelector('.c6e8ba5398--title');
                                
                                const priceEl = card.querySelector('.price') ||
                                             card.querySelector('[data-mark="MainPrice"]') ||
                                             card.querySelector('.c6e8ba5398--price') ||
                                             card.querySelector('[data-testid="price"]');
                                
                                const addressEl = card.querySelector('.address') ||
                                                card.querySelector('.geo') ||
                                                card.querySelector('[data-mark="GeoLabel"]') ||
                                                card.querySelector('.c6e8ba5398--geo');
                                
                                const roomsEl = card.querySelector('.rooms') ||
                                              card.querySelector('[data-mark="RoomsCount"]') ||
                                              card.querySelector('.c6e8ba5398--rooms');
                                
                                const areaEl = card.querySelector('.area') ||
                                             card.querySelector('[data-mark="AreaValue"]') ||
                                             card.querySelector('.c6e8ba5398--area');
                                
                                const floorEl = card.querySelector('.floor') ||
                                              card.querySelector('[data-mark="FloorValue"]') ||
                                              card.querySelector('.c6e8ba5398--floor');
                                
                                // Извлекаем ID из URL
                                let offer_id = null;
                                const idMatch = url.match(/\\/(\\d+)\\//);
                                if (idMatch) {{
                                    offer_id = parseInt(idMatch[1]);
                                }}
                                
                                const offer = {{
                                    id: offer_id,
                                    url: url,
                                    title: titleEl ? titleEl.textContent.trim() : null,
                                    price: priceEl ? priceEl.textContent.trim() : null,
                                    address: addressEl ? addressEl.textContent.trim() : null,
                                    rooms: roomsEl ? roomsEl.textContent.trim() : null,
                                    area: areaEl ? areaEl.textContent.trim() : null,
                                    floor: floorEl ? floorEl.textContent.trim() : null,
                                    extracted_at: new Date().toISOString(),
                                    page_index: index + 1,
                                    selector_used: '{selector}'
                                }};
                                
                                // Добавляем если есть основные данные
                                if (offer.title && offer.price && offer.url) {{
                                    realOffers.push(offer);
                                    console.log('Extracted offer:', offer.title, offer.price);
                                }} else {{
                                    console.log('Incomplete offer data:', offer);
                                }}
                                
                            }} catch (e) {{
                                console.error('Error extracting offer:', e);
                            }}
                        }});
                        
                        return realOffers;
                    }}
                """)
                
                if offers_data:
                    LOGGER.info(f"✅ Успешно извлечено {len(offers_data)} объявлений с селектором: {selector}")
                    return offers_data
                else:
                    LOGGER.warning(f"⚠️ Селектор {selector} нашел элементы, но не извлек данные")
            else:
                LOGGER.info(f"❌ Селектор {selector} не нашел элементов")
                
        except Exception as e:
            LOGGER.warning(f"⚠️ Ошибка с селектором {selector}: {e}")
            continue
    
    LOGGER.error("❌ Ни один селектор не сработал")
    return []

def save_to_database(offers: List[Dict[str, Any]]) -> int:
    """Сохраняет объявления в базу данных."""
    if not offers:
        return 0
    
    try:
        import psycopg2
        
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="realdb",
            user="realuser",
            password="realpass"
        )
        
        cursor = conn.cursor()
        
        saved_count = 0
        for offer in offers:
            try:
                # Парсим данные
                price_str = offer.get('price', '').replace(' ', '').replace('₽', '').replace(',', '').replace('руб', '')
                price_numeric = None
                if price_str:
                    import re
                    numbers = re.findall(r'\d+', price_str)
                    if numbers:
                        price_numeric = int(''.join(numbers))
                
                # Парсим комнаты
                rooms = 0
                rooms_str = offer.get('rooms', '')
                if rooms_str:
                    if 'студия' in rooms_str.lower():
                        rooms = 0
                    else:
                        import re
                        numbers = re.findall(r'\d+', rooms_str)
                        if numbers:
                            rooms = int(numbers[0])
                
                # Парсим площадь
                area = None
                area_str = offer.get('area', '')
                if area_str:
                    import re
                    numbers = re.findall(r'\d+\.?\d*', area_str)
                    if numbers:
                        area = float(numbers[0])
                
                # Парсим этаж
                floor = 1
                floor_str = offer.get('floor', '')
                if floor_str:
                    import re
                    numbers = re.findall(r'\d+', floor_str)
                    if numbers:
                        floor = int(numbers[0])
                
                # Вставляем в БД
                cursor.execute("""
                    INSERT INTO listings (id, url, region, deal_type, rooms, area_total, 
                                        floor, address, seller_type, lat, lon, first_seen, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        last_seen = EXCLUDED.last_seen,
                        is_active = TRUE
                """, (
                    offer.get('id') or saved_count + 1000000,
                    offer.get('url', ''),
                    1,  # Москва
                    'sale',
                    rooms,
                    area or 0,
                    floor,
                    offer.get('address', ''),
                    'Unknown',
                    55.7558,
                    37.6176,
                    datetime.now(),
                    datetime.now()
                ))
                
                # Вставляем цену
                if price_numeric:
                    cursor.execute("""
                        INSERT INTO listing_prices (id, seen_at, price)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id, seen_at) DO NOTHING
                    """, (
                        offer.get('id') or saved_count + 1000000,
                        datetime.now(),
                        price_numeric
                    ))
                
                saved_count += 1
                LOGGER.info(f"💾 Сохранено: {offer.get('title', 'N/A')[:50]}... - {offer.get('price', 'N/A')}")
                
            except Exception as e:
                LOGGER.error(f"Error saving offer {offer.get('id')}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        return saved_count
        
    except Exception as e:
        LOGGER.error(f"Database error: {e}")
        return 0

def collect_real_cian_data():
    """Собирает РЕАЛЬНЫЕ данные с CIAN."""
    
    LOGGER.info("🚀 Запуск УНИВЕРСАЛЬНОГО сборщика CIAN...")
    LOGGER.info("⚠️  ЦЕЛЬ: Извлечь 10 РЕАЛЬНЫХ объявлений!")
    
    all_offers = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            # URL для Москвы, продажа квартир
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p=1"
            LOGGER.info(f"📄 Загрузка страницы: {url}")
            
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(8)  # Даем больше времени на загрузку
            
            # Сохраняем скриншот для анализа
            screenshot_path = Path(__file__).parent.parent / f"logs/page_analysis_{int(time.time())}.png"
            page.screenshot(path=str(screenshot_path))
            LOGGER.info(f"📸 Скриншот сохранен: {screenshot_path}")
            
            # Анализируем структуру страницы
            page_structure = page.evaluate("""
                () => {
                    const allElements = document.querySelectorAll('*');
                    const structure = {};
                    
                    allElements.forEach(el => {
                        const tag = el.tagName;
                        const className = el.className;
                        const dataName = el.getAttribute('data-name');
                        const dataTestid = el.getAttribute('data-testid');
                        const id = el.id;
                        
                        const key = `${tag}.${className}.${dataName}.${dataTestid}.${id}`;
                        structure[key] = (structure[key] || 0) + 1;
                    });
                    
                    // Возвращаем топ-20 самых частых элементов
                    return Object.entries(structure)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 20)
                        .map(([key, count]) => ({element: key, count: count}));
                }
            """)
            
            LOGGER.info("🔍 Анализ структуры страницы:")
            for item in page_structure:
                LOGGER.info(f"   {item['count']}x: {item['element']}")
            
            # Извлекаем данные
            LOGGER.info("🔍 Извлечение данных...")
            offers_data = extract_with_multiple_selectors(page)
            
            if offers_data:
                all_offers.extend(offers_data)
                
                LOGGER.info(f"✅ Извлечено {len(offers_data)} РЕАЛЬНЫХ объявлений!")
                
                # Показываем все объявления
                LOGGER.info(f"\n📋 ВСЕ {len(all_offers)} РЕАЛЬНЫХ ОБЪЯВЛЕНИЙ:")
                for i, offer in enumerate(all_offers, 1):
                    LOGGER.info(f"\n{i}. {offer.get('title', 'N/A')}")
                    LOGGER.info(f"   💰 {offer.get('price', 'N/A')}")
                    LOGGER.info(f"   📍 {offer.get('address', 'N/A')}")
                    LOGGER.info(f"   🏠 {offer.get('rooms', 'N/A')} | {offer.get('area', 'N/A')} | {offer.get('floor', 'N/A')}")
                    LOGGER.info(f"   🔗 {offer.get('url', 'N/A')}")
                    LOGGER.info(f"   🎯 Селектор: {offer.get('selector_used', 'N/A')}")
                
                # Сохраняем в файл
                output_file = "logs/REAL_cian_data_universal.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'collection_info': {
                            'type': 'REAL CIAN DATA - UNIVERSAL',
                            'collected_at': datetime.now().isoformat(),
                            'total_offers': len(all_offers),
                            'page_structure': page_structure,
                            'note': 'Реальные данные, извлеченные универсальным методом'
                        },
                        'offers': all_offers
                    }, f, ensure_ascii=False, indent=2)
                
                LOGGER.info(f"\n💾 Сохранено в файл: {output_file}")
                
                # Сохраняем в базу данных
                LOGGER.info("💾 Сохранение в базу данных...")
                saved_count = save_to_database(all_offers)
                LOGGER.info(f"💾 Сохранено в БД: {saved_count} объявлений")
                
                return len(all_offers)
            else:
                LOGGER.error("❌ РЕАЛЬНЫЕ данные не собраны!")
                return 0
                
        except Exception as e:
            LOGGER.error(f"❌ Ошибка сбора: {e}")
            return 0
        finally:
            browser.close()

if __name__ == "__main__":
    offers_count = collect_real_cian_data()
    
    if offers_count > 0:
        LOGGER.info(f"\n🎉 УСПЕХ: Собрано {offers_count} РЕАЛЬНЫХ объявлений с CIAN!")
        
        # Проверяем БД
        import subprocess
        result = subprocess.run([
            "docker", "exec", "realestate-postgres-1", "psql", 
            "-U", "realuser", "-d", "realdb", "-c", 
            "SELECT COUNT(*) as total_listings FROM listings;"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            count_line = result.stdout.strip().split('\n')[-2]
            count = count_line.strip()
            LOGGER.info(f"📊 Записей в БД: {count}")
    else:
        LOGGER.error("\n❌ НЕУДАЧА: Реальные данные не собраны")
        sys.exit(1)

