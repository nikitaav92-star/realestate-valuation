#!/usr/bin/env python3
"""
ФИНАЛЬНЫЙ сборщик 100 объявлений с улучшенным антибот обходом.
Стратегия: медленный сбор с большими паузами, ротация User-Agent, retry логика.
"""

import json
import logging
import sys
import time
import re
import random
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

# СТРОГИЕ ФИЛЬТРЫ
MAX_PRICE = 30000000
MIN_FLOOR = 2
ALLOWED_ROOMS = [0, 1, 2, 3]

# User-Agent пул для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

def parse_offer_details(title: str, price_text: str) -> Dict[str, Any]:
    """Парсит детали объявления."""
    details = {}
    
    # Комнаты
    room_patterns = [
        (r'(\d+)-комн\.', lambda m: int(m.group(1))),
        (r'студия', lambda m: 0),
    ]
    
    for pattern, converter in room_patterns:
        match = re.search(pattern, title.lower())
        if match:
            details['rooms'] = converter(match)
            break
    
    # Площадь
    area_match = re.search(r'(\d+(?:,\d+)?)\s*м²', title)
    if area_match:
        area_str = area_match.group(1).replace(',', '.')
        try:
            details['area'] = float(area_str)
        except:
            pass
    
    # Этаж
    floor_match = re.search(r'(\d+)/(\d+)\s*этаж', title)
    if floor_match:
        details['floor'] = int(floor_match.group(1))
        details['total_floors'] = int(floor_match.group(2))
    
    # Цена
    price_str = price_text.replace(' ', '').replace('₽', '').replace(',', '')
    numbers = re.findall(r'\d+', price_str)
    if numbers:
        details['price_numeric'] = int(''.join(numbers))
    
    return details

def is_valid_offer(details: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Проверяет соответствие фильтрам."""
    errors = []
    
    price = details.get('price_numeric')
    if not price or price <= 0:
        errors.append("Цена не определена")
    elif price > MAX_PRICE:
        errors.append(f"Цена > {MAX_PRICE:,}")
    
    floor = details.get('floor')
    if floor is None:
        errors.append("Этаж не указан")
    elif floor < MIN_FLOOR:
        errors.append(f"Этаж < {MIN_FLOOR}")
    
    rooms = details.get('rooms')
    if rooms is None:
        errors.append("Комнаты не указаны")
    elif rooms not in ALLOWED_ROOMS:
        errors.append(f"Комнаты не в списке")
    
    return len(errors) == 0, errors

def extract_offers_from_page(page) -> List[Dict[str, Any]]:
    """Извлекает реальные данные со страницы."""
    try:
        page.wait_for_selector('[data-name="LinkArea"]', timeout=20000)
        time.sleep(3)  # Дополнительная пауза
        
        offers_data = page.evaluate("""
            () => {
                const cards = document.querySelectorAll('[data-name="LinkArea"]');
                const offers = [];
                
                cards.forEach((card) => {
                    try {
                        const linkEl = card.querySelector('a[href*="cian.ru"]');
                        if (!linkEl) return;
                        
                        const url = linkEl.href;
                        const titleEl = card.querySelector('h3, h2, [data-mark="OfferTitle"]');
                        const priceEl = card.querySelector('[data-mark="MainPrice"]');
                        const addressEl = card.querySelector('[data-mark="GeoLabel"]');
                        
                        const idMatch = url.match(/\\/(\\d+)\\//);
                        
                        if (titleEl && priceEl && idMatch) {
                            offers.push({
                                id: parseInt(idMatch[1]),
                                url: url,
                                title: titleEl.textContent.trim(),
                                price: priceEl.textContent.trim(),
                                address: addressEl ? addressEl.textContent.trim() : 'Москва',
                                extracted_at: new Date().toISOString()
                            });
                        }
                    } catch (e) {}
                });
                
                return offers;
            }
        """)
        
        LOGGER.info(f"   📥 Извлечено: {len(offers_data)} объявлений")
        
        valid_offers = []
        invalid_count = 0
        
        for offer in offers_data:
            details = parse_offer_details(offer['title'], offer['price'])
            offer.update(details)
            
            is_valid, errors = is_valid_offer(details)
            
            if is_valid:
                valid_offers.append(offer)
            else:
                invalid_count += 1
        
        LOGGER.info(f"   ✅ Валидных: {len(valid_offers)} | ❌ Отклонено: {invalid_count}")
        
        return valid_offers
        
    except Exception as e:
        LOGGER.error(f"Ошибка извлечения: {e}")
        return []

def collect_100_final():
    """Собирает 100+ объявлений с улучшенным антибот обходом."""
    
    LOGGER.info("🚀 ФИНАЛЬНЫЙ сбор 100 объявлений CIAN")
    LOGGER.info("📋 ФИЛЬТРЫ:")
    LOGGER.info(f"   💰 Цена: до {MAX_PRICE:,} ₽")
    LOGGER.info(f"   🏢 Этаж: от {MIN_FLOOR}")
    LOGGER.info(f"   🏠 Комнаты: {ALLOWED_ROOMS}")
    LOGGER.info(f"   🐌 Медленный сбор с паузами (антибот)")
    LOGGER.info("")
    
    base_url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&building_status=secondary&price_min=1000000&price_max=30000000&room=0&room=1&room=2&room=3"
    
    all_valid_offers = []
    seen_ids = set()
    target = 100
    max_pages = 30
    
    start_time = time.time()
    retry_count = 0
    max_retries = 3
    
    with sync_playwright() as p:
        browser = None
        
        try:
            for page_num in range(1, max_pages + 1):
                if len(all_valid_offers) >= target:
                    break
                
                # Пересоздаем браузер каждые 5 страниц для сброса fingerprint
                if browser is None or page_num % 5 == 1:
                    if browser:
                        browser.close()
                        time.sleep(2)  # Пауза между сессиями
                    
                    user_agent = random.choice(USER_AGENTS)
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(user_agent=user_agent)
                    page = context.new_page()
                    LOGGER.info(f"🔄 Новая сессия браузера (UA: {user_agent[:50]}...)")
                
                url = f"{base_url}&p={page_num}"
                LOGGER.info(f"\n📄 Страница {page_num}/{max_pages}")
                
                try:
                    # Увеличенный timeout
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    
                    # Антибот: случайная пауза 3-7 секунд
                    delay = random.uniform(3, 7)
                    LOGGER.info(f"   ⏳ Пауза {delay:.1f}с (антибот)...")
                    time.sleep(delay)
                    
                    valid_offers = extract_offers_from_page(page)
                    
                    # Фильтруем дубликаты
                    new_offers = []
                    for offer in valid_offers:
                        if offer['id'] not in seen_ids:
                            seen_ids.add(offer['id'])
                            new_offers.append(offer)
                    
                    all_valid_offers.extend(new_offers)
                    
                    LOGGER.info(f"📊 Всего собрано: {len(all_valid_offers)}/{target}")
                    
                    if len(valid_offers) == 0:
                        LOGGER.warning(f"⚠️ Пустая страница {page_num}")
                        retry_count += 1
                        if retry_count >= max_retries:
                            LOGGER.warning(f"⚠️ Достигнут лимит пустых страниц ({max_retries}), останавливаем")
                            break
                        time.sleep(10)  # Длинная пауза после пустой страницы
                    else:
                        retry_count = 0  # Сбрасываем счетчик
                    
                    # Антибот: длинная пауза между страницами
                    if page_num < max_pages and len(all_valid_offers) < target:
                        pause = random.uniform(5, 10)
                        LOGGER.info(f"   ⏳ Пауза между страницами: {pause:.1f}с...")
                        time.sleep(pause)
                    
                except Exception as e:
                    LOGGER.error(f"❌ Ошибка на странице {page_num}: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        LOGGER.warning(f"⚠️ Достигнут лимит ошибок ({max_retries}), останавливаем")
                        break
                    # Длинная пауза после ошибки
                    time.sleep(15)
                    continue
            
            elapsed_time = time.time() - start_time
            
            LOGGER.info(f"\n{'='*60}")
            LOGGER.info(f"📊 ИТОГО:")
            LOGGER.info(f"   Собрано объявлений: {len(all_valid_offers)}")
            LOGGER.info(f"   Страниц обработано: {page_num}")
            LOGGER.info(f"   Время: {elapsed_time:.1f}с ({elapsed_time/60:.1f}мин)")
            if elapsed_time > 0:
                LOGGER.info(f"   Скорость: {len(all_valid_offers)/(elapsed_time/60):.1f} объявлений/мин")
            LOGGER.info(f"{'='*60}")
            
            if all_valid_offers:
                # Сохраняем в файл
                output_file = "logs/100_listings_final.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'collection_info': {
                            'collected_at': datetime.now().isoformat(),
                            'total_offers': len(all_valid_offers),
                            'pages_scraped': page_num,
                            'elapsed_time': elapsed_time,
                            'filters': {
                                'max_price': MAX_PRICE,
                                'min_floor': MIN_FLOOR,
                                'allowed_rooms': ALLOWED_ROOMS
                            }
                        },
                        'offers': all_valid_offers
                    }, f, ensure_ascii=False, indent=2)
                
                LOGGER.info(f"💾 Сохранено в файл: {output_file}")
                
                # Сохраняем в БД
                save_to_database(all_valid_offers)
                
                return len(all_valid_offers)
            else:
                LOGGER.error("❌ Не удалось собрать объявления")
                return 0
                
        finally:
            if browser:
                browser.close()

def save_to_database(offers: List[Dict[str, Any]]):
    """Сохраняет в БД."""
    
    LOGGER.info(f"\n💾 Сохранение {len(offers)} объявлений в БД...")
    
    import subprocess
    
    # Очищаем БД
    subprocess.run([
        "docker", "exec", "realestate-postgres-1", "psql",
        "-U", "realuser", "-d", "realdb", "-c",
        "DELETE FROM listing_prices; DELETE FROM listings;"
    ], capture_output=True)
    
    saved_count = 0
    
    for offer in offers:
        try:
            offer_id = offer['id']
            rooms = offer.get('rooms', 0)
            area = offer.get('area', 0)
            floor = offer.get('floor', 1)
            price = offer.get('price_numeric', 0)
            url = offer['url'].replace("'", "''")
            address = (offer.get('address') or 'Москва').replace("'", "''")
            
            insert_sql = f"""
                INSERT INTO listings (id, url, region, deal_type, rooms, area_total, 
                                    floor, address, seller_type, lat, lon, first_seen, last_seen)
                VALUES ({offer_id}, '{url}', 1, 'sale', {rooms}, {area}, 
                        {floor}, '{address}', 'Unknown', 55.7558, 37.6176, 
                        NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    last_seen = NOW(),
                    is_active = TRUE;
                
                INSERT INTO listing_prices (id, seen_at, price)
                VALUES ({offer_id}, NOW(), {price})
                ON CONFLICT (id, seen_at) DO NOTHING;
            """
            
            result = subprocess.run([
                "docker", "exec", "-i", "realestate-postgres-1",
                "psql", "-U", "realuser", "-d", "realdb"
            ], input=insert_sql, text=True, capture_output=True)
            
            if result.returncode == 0:
                saved_count += 1
                if saved_count % 20 == 0:
                    LOGGER.info(f"   💾 Сохранено: {saved_count}/{len(offers)}")
        
        except Exception as e:
            LOGGER.error(f"❌ Ошибка сохранения ID {offer.get('id')}: {e}")
            continue
    
    LOGGER.info(f"✅ Сохранено в БД: {saved_count} объявлений")

if __name__ == "__main__":
    count = collect_100_final()
    
    if count >= 100:
        LOGGER.info(f"\n🎉 УСПЕХ: Собрано {count} объявлений!")
    elif count > 0:
        LOGGER.info(f"\n⚠️ Собрано {count} объявлений (меньше 100, но это реальные данные)")
    else:
        LOGGER.error("\n❌ НЕУДАЧА")
        sys.exit(1)
