#!/usr/bin/env python3
"""Продолжает сбор еще 50 объявлений, начиная со страницы 21."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Импортируем все из основного скрипта
from collect_100_final import *

if __name__ == "__main__":
    import json
    
    # Загружаем уже собранные данные
    try:
        with open('logs/100_listings_final.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        existing_offers = existing_data['offers']
        existing_ids = {offer['id'] for offer in existing_offers}
        LOGGER.info(f"📁 Загружено {len(existing_offers)} существующих объявлений")
    except:
        existing_offers = []
        existing_ids = set()
    
    # Модифицируем функцию сбора для продолжения
    LOGGER.info("🚀 Продолжаем сбор (страницы 21-40)")
    
    base_url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&building_status=secondary&price_min=1000000&price_max=30000000&room=0&room=1&room=2&room=3"
    
    all_valid_offers = existing_offers.copy()
    seen_ids = existing_ids.copy()
    target = 100
    start_page = 21
    max_pages = 40
    
    start_time = time.time()
    retry_count = 0
    max_retries = 3
    
    with sync_playwright() as p:
        browser = None
        
        try:
            for page_num in range(start_page, max_pages + 1):
                if len(all_valid_offers) >= target:
                    break
                
                if browser is None or (page_num - start_page) % 5 == 0:
                    if browser:
                        browser.close()
                        time.sleep(2)
                    
                    user_agent = random.choice(USER_AGENTS)
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(user_agent=user_agent)
                    page = context.new_page()
                    LOGGER.info(f"🔄 Новая сессия браузера")
                
                url = f"{base_url}&p={page_num}"
                LOGGER.info(f"\n📄 Страница {page_num}/{max_pages}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    
                    delay = random.uniform(3, 7)
                    LOGGER.info(f"   ⏳ Пауза {delay:.1f}с...")
                    time.sleep(delay)
                    
                    valid_offers = extract_offers_from_page(page)
                    
                    new_offers = []
                    for offer in valid_offers:
                        if offer['id'] not in seen_ids:
                            seen_ids.add(offer['id'])
                            new_offers.append(offer)
                    
                    all_valid_offers.extend(new_offers)
                    
                    LOGGER.info(f"📊 Всего собрано: {len(all_valid_offers)}/{target}")
                    
                    if len(valid_offers) == 0:
                        retry_count += 1
                        if retry_count >= max_retries:
                            break
                        time.sleep(10)
                    else:
                        retry_count = 0
                    
                    if page_num < max_pages and len(all_valid_offers) < target:
                        pause = random.uniform(5, 10)
                        time.sleep(pause)
                    
                except Exception as e:
                    LOGGER.error(f"❌ Ошибка: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        break
                    time.sleep(15)
                    continue
            
            elapsed_time = time.time() - start_time
            
            LOGGER.info(f"\n{'='*60}")
            LOGGER.info(f"📊 ИТОГО:")
            LOGGER.info(f"   Собрано объявлений: {len(all_valid_offers)}")
            LOGGER.info(f"   Новых: {len(all_valid_offers) - len(existing_offers)}")
            LOGGER.info(f"   Время: {elapsed_time:.1f}с ({elapsed_time/60:.1f}мин)")
            LOGGER.info(f"{'='*60}")
            
            if all_valid_offers:
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
                
                LOGGER.info(f"💾 Обновлен файл: {output_file}")
                
                # Сохраняем в БД только новые
                new_only = [o for o in all_valid_offers if o['id'] not in existing_ids]
                if new_only:
                    LOGGER.info(f"💾 Сохранение {len(new_only)} новых объявлений в БД...")
                    
                    import subprocess
                    saved_count = 0
                    
                    for offer in new_only:
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
                        
                        except Exception as e:
                            continue
                    
                    LOGGER.info(f"✅ Сохранено в БД: {saved_count} новых объявлений")
                
        finally:
            if browser:
                browser.close()
    
    if len(all_valid_offers) >= 100:
        LOGGER.info(f"\n🎉 УСПЕХ: Собрано {len(all_valid_offers)} объявлений!")
    else:
        LOGGER.info(f"\n⚠️ Собрано {len(all_valid_offers)} объявлений")
