#!/usr/bin/env python3
"""
ФИНАЛЬНЫЙ сборщик CIAN с ПОЛНОЙ фильтрацией.
Фильтрует объявления ПОСЛЕ извлечения, так как CIAN игнорирует некоторые URL фильтры.
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

def extract_and_validate_offers(page) -> List[Dict[str, Any]]:
    """Извлекает и валидирует объявления с полной фильтрацией."""
    try:
        # Ждем загрузки объявлений
        page.wait_for_selector('[data-name="LinkArea"]', timeout=15000)
        time.sleep(3)
        
        # Извлекаем данные
        offers_data = page.evaluate("""
            () => {
                const cards = document.querySelectorAll('[data-name="LinkArea"]');
                const realOffers = [];
                
                console.log('Found cards:', cards.length);
                
                cards.forEach((card, index) => {
                    try {
                        // Ищем ссылку на объявление
                        const linkEl = card.querySelector('a[href*="cian.ru"]');
                        
                        if (!linkEl) {
                            console.log('No link found for card', index);
                            return;
                        }
                        
                        const url = linkEl.href;
                        
                        // Извлекаем данные
                        const titleEl = card.querySelector('h3') ||
                                       card.querySelector('h2') ||
                                       card.querySelector('.title') ||
                                       card.querySelector('[data-mark="OfferTitle"]');
                        
                        const priceEl = card.querySelector('.price') ||
                                       card.querySelector('[data-mark="MainPrice"]') ||
                                       card.querySelector('[data-testid="price"]');
                        
                        const addressEl = card.querySelector('.address') ||
                                        card.querySelector('.geo') ||
                                        card.querySelector('[data-mark="GeoLabel"]');
                        
                        // Извлекаем ID из URL
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
                            extracted_at: new Date().toISOString(),
                            page_index: index + 1,
                            selector_used: '[data-name="LinkArea"]'
                        };
                        
                        // Добавляем только если есть основные данные
                        if (offer.title && offer.price && offer.url) {
                            realOffers.push(offer);
                            console.log('Extracted offer:', offer.title, offer.price);
                        }
                        
                    } catch (e) {
                        console.error('Error extracting offer:', e);
                    }
                });
                
                return realOffers;
            }
        """)
        
        # Валидируем каждый offer
        valid_offers = []
        
        for offer in offers_data:
            validated_offer = parse_and_validate_offer(offer)
            if validated_offer.get('is_valid', False):
                valid_offers.append(validated_offer)
        
        return valid_offers
        
    except Exception as e:
        LOGGER.error(f"Error extracting offers: {e}")
        return []

def parse_and_validate_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Парсит и валидирует объявление по ВСЕМ фильтрам."""
    
    # ЗАДАННЫЕ ФИЛЬТРЫ
    MAX_PRICE = 30000000  # 30 млн ₽
    MIN_FLOOR = 2         # от 2 этажа
    ALLOWED_ROOMS = [0, 1, 2, 3]  # студия, 1, 2, 3 комнаты
    
    title = offer.get('title', '')
    
    # Парсим данные из title
    parsed_info = {}
    
    # Парсим комнаты
    room_patterns = [
        r'(\d+)-комн\.',
        r'(\d+)комн',
        r'(\d+)\s*комнат',
        r'студия',
        r'однушка',
        r'двушка',
        r'трешка'
    ]
    
    for pattern in room_patterns:
        import re
        match = re.search(pattern, title.lower())
        if match:
            if 'студия' in pattern or 'однушка' in pattern:
                parsed_info['rooms'] = 0
            elif 'двушка' in pattern:
                parsed_info['rooms'] = 2
            elif 'трешка' in pattern:
                parsed_info['rooms'] = 3
            else:
                parsed_info['rooms'] = int(match.group(1))
            break
    
    # Парсим площадь
    area_patterns = [
        r'(\d+(?:,\d+)?)\s*м²',
        r'(\d+(?:\.\d+)?)\s*м2',
        r'(\d+(?:,\d+)?)\s*кв\.м',
        r'(\d+(?:\.\d+)?)\s*кв\s*м'
    ]
    
    for pattern in area_patterns:
        import re
        match = re.search(pattern, title.lower())
        if match:
            area_str = match.group(1).replace(',', '.')
            try:
                parsed_info['area'] = float(area_str)
            except:
                pass
            break
    
    # Парсим этаж
    floor_patterns = [
        r'(\d+)/(\d+)\s*этаж',
        r'(\d+)\/(\d+)\s*эт',
        r'(\d+)/(\d+)',
        r'(\d+)\s*этаж'
    ]
    
    for pattern in floor_patterns:
        import re
        match = re.search(pattern, title.lower())
        if match:
            if len(match.groups()) >= 2:
                parsed_info['floor'] = int(match.group(1))
                parsed_info['total_floors'] = int(match.group(2))
            else:
                parsed_info['floor'] = int(match.group(1))
            break
    
    # Парсим цену
    price_str = offer.get('price', '').replace(' ', '').replace('₽', '').replace(',', '').replace('руб', '')
    price_numeric = None
    if price_str:
        import re
        numbers = re.findall(r'\d+', price_str)
        if numbers:
            price_numeric = int(''.join(numbers))
    
    # СТРОГАЯ ВАЛИДАЦИЯ ПО ВСЕМ ФИЛЬТРАМ
    validation_errors = []
    
    # 1. Проверка цены
    if price_numeric and price_numeric > MAX_PRICE:
        validation_errors.append(f"Цена {price_numeric:,} ₽ > {MAX_PRICE:,} ₽")
    
    # 2. Проверка этажа (КРИТИЧНО!)
    if 'floor' not in parsed_info:
        validation_errors.append("Этаж не указан - ИСКЛЮЧАЕМ")
    elif parsed_info['floor'] < MIN_FLOOR:
        validation_errors.append(f"Этаж {parsed_info['floor']} < {MIN_FLOOR}")
    
    # 3. Проверка комнат
    if 'rooms' not in parsed_info:
        validation_errors.append("Комнаты не указаны - ИСКЛЮЧАЕМ")
    elif parsed_info['rooms'] not in ALLOWED_ROOMS:
        validation_errors.append(f"Комнат {parsed_info['rooms']} не в списке {ALLOWED_ROOMS}")
    
    # 4. Дополнительные проверки
    if not price_numeric or price_numeric <= 0:
        validation_errors.append("Цена не определена или некорректна")
    
    # Объединяем данные
    validated_offer = {
        **offer,
        **parsed_info,
        'price_numeric': price_numeric,
        'validation_errors': validation_errors,
        'is_valid': len(validation_errors) == 0
    }
    
    return validated_offer

def save_valid_offers_to_db(offers: List[Dict[str, Any]]) -> int:
    """Сохраняет только валидные объявления в БД."""
    
    if not offers:
        LOGGER.warning("⚠️ Нет валидных объявлений для сохранения")
        return 0
    
    LOGGER.info(f"💾 Сохранение {len(offers)} валидных объявлений в БД...")
    
    saved_count = 0
    
    for offer in offers:
        try:
            import subprocess
            
            # Параметры
            offer_id = offer.get('id') or (saved_count + 1000000)
            rooms = offer.get('rooms', 0)
            area = offer.get('area', 0)
            floor = offer.get('floor', 1)
            price = offer.get('price_numeric', 0)
            url = offer.get('url', '')
            
            # SQL запрос
            insert_sql = f"""
                INSERT INTO listings (id, url, region, deal_type, rooms, area_total, 
                                    floor, address, seller_type, lat, lon, first_seen, last_seen)
                VALUES ({offer_id}, '{url}', 1, 'sale', {rooms}, {area}, 
                        {floor}, 'Unknown', 'Unknown', 55.7558, 37.6176, 
                        NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    last_seen = NOW(),
                    is_active = TRUE;
            """
            
            # Выполняем через Docker
            result = subprocess.run([
                "docker", "exec", "-i", "realestate-postgres-1", 
                "psql", "-U", "realuser", "-d", "realdb"
            ], input=insert_sql, text=True, capture_output=True)
            
            if result.returncode == 0:
                saved_count += 1
                
                # Сохраняем цену
                if price > 0:
                    price_sql = f"""
                        INSERT INTO listing_prices (id, seen_at, price)
                        VALUES ({offer_id}, NOW(), {price})
                        ON CONFLICT (id, seen_at) DO NOTHING;
                    """
                    
                    subprocess.run([
                        "docker", "exec", "-i", "realestate-postgres-1", 
                        "psql", "-U", "realuser", "-d", "realdb"
                    ], input=price_sql, text=True, capture_output=True)
                
                LOGGER.info(f"💾 {saved_count}. Сохранено: {offer.get('title', 'N/A')[:50]}... - {offer.get('price', 'N/A')}")
                
        except Exception as e:
            LOGGER.error(f"❌ Ошибка сохранения объявления {offer.get('id')}: {e}")
            continue
    
    return saved_count

def collect_final_cian_data():
    """ФИНАЛЬНЫЙ сбор данных с CIAN с полной фильтрацией."""
    
    LOGGER.info("🚀 Запуск ФИНАЛЬНОГО сборщика CIAN с ПОЛНОЙ фильтрацией...")
    LOGGER.info("📋 ФИЛЬТРЫ:")
    LOGGER.info("   💰 Цена: до 30 000 000 ₽")
    LOGGER.info("   🏢 Этаж: от 2 (СТРОГАЯ проверка)")
    LOGGER.info("   🏠 Комнаты: 0, 1, 2, 3 (СТРОГАЯ проверка)")
    LOGGER.info("   🏘️ Тип: вторичка")
    LOGGER.info("   ⚠️  Пост-фильтрация включена!")
    LOGGER.info("")
    
    # URL с базовыми фильтрами
    url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&building_status=secondary&price_min=1000000&price_max=30000000&room=0&room=1&room=2&room=3&p=1"
    
    LOGGER.info(f"🔗 URL: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            LOGGER.info("📄 Загрузка страницы...")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)
            
            # Извлекаем и валидируем данные
            LOGGER.info("🔍 Извлечение и валидация данных...")
            valid_offers = extract_and_validate_offers(page)
            
            if valid_offers:
                LOGGER.info(f"✅ Найдено {len(valid_offers)} объявлений, соответствующих ВСЕМ фильтрам!")
                
                # Показываем валидные объявления
                LOGGER.info(f"\n✅ ВАЛИДНЫЕ ОБЪЯВЛЕНИЯ ({len(valid_offers)}):")
                for i, offer in enumerate(valid_offers, 1):
                    LOGGER.info(f"\n{i}. {offer.get('title', 'N/A')}")
                    LOGGER.info(f"   💰 {offer.get('price', 'N/A')}")
                    LOGGER.info(f"   🏠 {offer.get('rooms', 'N/A')} комн. | {offer.get('area', 'N/A')} м² | {offer.get('floor', 'N/A')} эт.")
                    LOGGER.info(f"   🔗 ID: {offer.get('id', 'N/A')}")
                
                # Сохраняем в файл
                output_file = "logs/FINAL_cian_data.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'collection_info': {
                            'type': 'FINAL CIAN DATA - STRICT FILTERING',
                            'collected_at': datetime.now().isoformat(),
                            'valid_offers': len(valid_offers),
                            'filters_applied': {
                                'max_price': 30000000,
                                'min_floor': 2,
                                'allowed_rooms': [0, 1, 2, 3],
                                'building_status': 'secondary',
                                'post_filtering': True
                            },
                            'url_used': url
                        },
                        'valid_offers': valid_offers
                    }, f, ensure_ascii=False, indent=2)
                
                LOGGER.info(f"\n💾 Сохранено в файл: {output_file}")
                
                # Сохраняем в БД
                saved_count = save_valid_offers_to_db(valid_offers)
                LOGGER.info(f"💾 Сохранено в БД: {saved_count} валидных объявлений")
                
                return len(valid_offers)
            else:
                LOGGER.error("❌ Валидные данные не найдены")
                return 0
                
        except Exception as e:
            LOGGER.error(f"❌ Ошибка сбора: {e}")
            return 0
        finally:
            browser.close()

if __name__ == "__main__":
    valid_count = collect_final_cian_data()
    
    if valid_count > 0:
        LOGGER.info(f"\n🎉 УСПЕХ: Собрано {valid_count} объявлений, соответствующих ВСЕМ фильтрам!")
        
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
            LOGGER.info(f"📊 Всего записей в БД: {count}")
    else:
        LOGGER.error("\n❌ НЕУДАЧА: Валидные данные не собраны")
        sys.exit(1)

