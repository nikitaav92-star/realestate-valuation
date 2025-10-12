#!/usr/bin/env python3
"""
ИСПРАВЛЕННЫЙ сборщик данных CIAN - извлекает РЕАЛЬНЫЕ данные объявлений.
Исправляет критическую ошибку оригинального скрипта.
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
from etl.antibot.behavior import HumanBehavior
from etl.antibot.captcha import CaptchaSolver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def extract_real_offer_data(page) -> List[Dict[str, Any]]:
    """Извлекает РЕАЛЬНЫЕ данные объявлений с CIAN."""
    try:
        # Ждем загрузки объявлений
        page.wait_for_selector('[data-name="OfferCard"]', timeout=15000)
        time.sleep(2)  # Дополнительное время для полной загрузки
        
        # Извлекаем РЕАЛЬНЫЕ данные через JavaScript
        offers_data = page.evaluate("""
            () => {
                const cards = document.querySelectorAll('[data-name="OfferCard"]');
                const realOffers = [];
                
                console.log('Found cards:', cards.length);
                
                cards.forEach((card, index) => {
                    try {
                        // Ищем ссылку на объявление
                        const linkEl = card.querySelector('[data-name="LinkArea"] a') || 
                                      card.querySelector('a[href*="/sale/flat/"]') ||
                                      card.querySelector('a[href*="/rent/flat/"]') ||
                                      card.querySelector('a[href*="cian.ru"]');
                        
                        if (!linkEl) {
                            console.log('No link found for card', index);
                            return;
                        }
                        
                        const url = linkEl.href;
                        
                        // Извлекаем данные из разных возможных селекторов
                        const titleEl = card.querySelector('[data-mark="OfferTitle"]') || 
                                       card.querySelector('.c6e8ba5398--title') ||
                                       card.querySelector('[data-name="OfferTitle"]') ||
                                       card.querySelector('h3') ||
                                       card.querySelector('.title');
                        
                        const priceEl = card.querySelector('[data-mark="MainPrice"]') || 
                                       card.querySelector('.c6e8ba5398--price') ||
                                       card.querySelector('[data-name="MainPrice"]') ||
                                       card.querySelector('.price') ||
                                       card.querySelector('[data-testid="price"]');
                        
                        const addressEl = card.querySelector('[data-mark="GeoLabel"]') || 
                                         card.querySelector('.c6e8ba5398--geo') ||
                                         card.querySelector('[data-name="GeoLabel"]') ||
                                         card.querySelector('.address') ||
                                         card.querySelector('.geo');
                        
                        const roomsEl = card.querySelector('[data-mark="RoomsCount"]') || 
                                       card.querySelector('.c6e8ba5398--rooms') ||
                                       card.querySelector('[data-name="RoomsCount"]') ||
                                       card.querySelector('.rooms');
                        
                        const areaEl = card.querySelector('[data-mark="AreaValue"]') || 
                                      card.querySelector('.c6e8ba5398--area') ||
                                      card.querySelector('[data-name="AreaValue"]') ||
                                      card.querySelector('.area');
                        
                        const floorEl = card.querySelector('[data-mark="FloorValue"]') || 
                                       card.querySelector('.c6e8ba5398--floor') ||
                                       card.querySelector('[data-name="FloorValue"]') ||
                                       card.querySelector('.floor');
                        
                        // Пытаемся извлечь ID из URL
                        let offer_id = null;
                        const idMatch = url.match(/\\/(\\d+)\\//);
                        if (idMatch) {
                            offer_id = parseInt(idMatch[1]);
                        }
                        
                        const offer = {
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
                            raw_html: card.innerHTML.substring(0, 500)  // Для отладки
                        };
                        
                        // Добавляем только если есть основные данные
                        if (offer.title && offer.price && offer.url) {
                            realOffers.push(offer);
                            console.log('Extracted offer:', offer.title, offer.price);
                        } else {
                            console.log('Incomplete offer data:', offer);
                        }
                        
                    } catch (e) {
                        console.error('Error extracting offer:', e);
                    }
                });
                
                return realOffers;
            }
        """)
        
        return offers_data
    except Exception as e:
        LOGGER.error(f"Error extracting offers: {e}")
        # Попробуем альтернативный способ
        try:
            # Берем скриншот для отладки
            screenshot_path = Path(__file__).parent.parent / f"logs/debug_page_{int(time.time())}.png"
            page.screenshot(path=str(screenshot_path))
            LOGGER.info(f"Screenshot saved: {screenshot_path}")
        except:
            pass
        return []

def save_to_database(offers: List[Dict[str, Any]]) -> int:
    """Сохраняет объявления в базу данных."""
    if not offers:
        return 0
    
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Подключение к БД
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
                    # Извлекаем только цифры
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
                    offer.get('id') or saved_count + 1000000,  # Генерируем ID если нет
                    offer.get('url', ''),
                    1,  # Москва
                    'sale',  # Предполагаем продажу
                    rooms,
                    area or 0,
                    floor,
                    offer.get('address', ''),
                    'Unknown',  # Заглушка для продавца
                    55.7558,  # Заглушка для координат
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
                LOGGER.info(f"💾 Сохранено объявление: {offer.get('title', 'N/A')[:50]}... - {offer.get('price', 'N/A')}")
                
            except Exception as e:
                LOGGER.error(f"Error saving offer {offer.get('id')}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        return saved_count
        
    except Exception as e:
        LOGGER.error(f"Database error: {e}")
        return 0

def collect_real_cian_data(max_pages=1):
    """Собирает РЕАЛЬНЫЕ данные с CIAN."""
    
    LOGGER.info("🚀 Запуск ИСПРАВЛЕННОГО сбора данных с CIAN...")
    LOGGER.info("⚠️  ЦЕЛЬ: Извлечь 10 РЕАЛЬНЫХ объявлений!")
    
    all_offers = []
    successful_pages = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            for page_num in range(1, max_pages + 1):
                start_time = time.time()
                
                # URL для Москвы, продажа квартир
                url = f"https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p={page_num}"
                LOGGER.info(f"📄 Загрузка страницы {page_num}: {url}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(5)  # Даем время на загрузку
                    
                    # Извлекаем РЕАЛЬНЫЕ данные
                    LOGGER.info(f"🔍 Извлечение РЕАЛЬНЫХ данных со страницы {page_num}...")
                    page_offers = extract_real_offer_data(page)
                    
                    if page_offers:
                        all_offers.extend(page_offers)
                        successful_pages += 1
                        
                        page_time = time.time() - start_time
                        
                        LOGGER.info(f"✅ Страница {page_num}: {len(page_offers)} РЕАЛЬНЫХ объявлений | Всего: {len(all_offers)} | Время: {page_time:.1f}s")
                        
                        # Показываем первое объявление как пример
                        if page_offers:
                            first = page_offers[0]
                            LOGGER.info(f"   📋 Пример: {first.get('title', 'N/A')[:50]}... - {first.get('price', 'N/A')}")
                            LOGGER.info(f"   🔗 URL: {first.get('url', 'N/A')}")
                        
                        # Если набрали 10 объявлений, останавливаемся
                        if len(all_offers) >= 10:
                            LOGGER.info(f"🎯 ДОСТИГНУТА ЦЕЛЬ: {len(all_offers)} объявлений!")
                            break
                    else:
                        LOGGER.warning(f"⚠️ Страница {page_num}: Данные не извлечены")
                    
                except Exception as e:
                    LOGGER.error(f"❌ Ошибка на странице {page_num}: {e}")
                    continue
            
            # Сохраняем результаты
            if all_offers:
                # Сохраняем в файл
                output_file = "logs/REAL_cian_data_fixed.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'collection_info': {
                            'type': 'REAL CIAN DATA - FIXED',
                            'collected_at': datetime.now().isoformat(),
                            'total_offers': len(all_offers),
                            'successful_pages': successful_pages,
                            'note': 'Это РЕАЛЬНЫЕ данные, извлеченные с CIAN исправленным скриптом'
                        },
                        'offers': all_offers
                    }, f, ensure_ascii=False, indent=2)
                
                LOGGER.info(f"\n💾 Сохранено {len(all_offers)} РЕАЛЬНЫХ объявлений в: {output_file}")
                
                # Сохраняем в базу данных
                LOGGER.info("💾 Сохранение в базу данных...")
                saved_count = save_to_database(all_offers)
                LOGGER.info(f"💾 Сохранено в БД: {saved_count} объявлений")
                
                # Показываем все объявления
                LOGGER.info(f"\n📋 ВСЕ {len(all_offers)} РЕАЛЬНЫХ ОБЪЯВЛЕНИЙ:")
                for i, offer in enumerate(all_offers, 1):
                    LOGGER.info(f"\n{i}. {offer.get('title', 'N/A')}")
                    LOGGER.info(f"   💰 {offer.get('price', 'N/A')}")
                    LOGGER.info(f"   📍 {offer.get('address', 'N/A')}")
                    LOGGER.info(f"   🏠 {offer.get('rooms', 'N/A')} | {offer.get('area', 'N/A')} | {offer.get('floor', 'N/A')}")
                    LOGGER.info(f"   🔗 {offer.get('url', 'N/A')}")
                
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
    offers_count = collect_real_cian_data(max_pages=1)
    
    if offers_count > 0:
        LOGGER.info(f"\n🎉 УСПЕХ: Собрано {offers_count} РЕАЛЬНЫХ объявлений с CIAN!")
        LOGGER.info("📁 Проверьте logs/REAL_cian_data_fixed.json и базу данных")
        
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
