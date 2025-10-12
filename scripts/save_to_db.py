#!/usr/bin/env python3
"""Сохраняет извлеченные данные в БД через Docker."""

import json
import subprocess
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def save_offers_to_db():
    """Сохраняет объявления в БД через Docker."""
    
    # Читаем данные из файла
    try:
        with open('logs/REAL_cian_data_universal.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        offers = data['offers']
        LOGGER.info(f"📁 Загружено {len(offers)} объявлений из файла")
        
    except Exception as e:
        LOGGER.error(f"❌ Ошибка чтения файла: {e}")
        return
    
    saved_count = 0
    
    for i, offer in enumerate(offers):
        try:
            # Парсим данные
            price_str = (offer.get('price') or '').replace(' ', '').replace('₽', '').replace(',', '').replace('руб', '')
            price_numeric = None
            if price_str:
                import re
                numbers = re.findall(r'\d+', price_str)
                if numbers:
                    price_numeric = int(''.join(numbers))
            
            # Парсим комнаты
            rooms = 0
            rooms_str = offer.get('rooms') or ''
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
            area_str = offer.get('area') or ''
            if area_str:
                import re
                numbers = re.findall(r'\d+\.?\d*', area_str)
                if numbers:
                    area = float(numbers[0])
            
            # Парсим этаж
            floor = 1
            floor_str = offer.get('floor') or ''
            if floor_str:
                import re
                numbers = re.findall(r'\d+', floor_str)
                if numbers:
                    floor = int(numbers[0])
            
            # ID из URL
            offer_id = offer.get('id') or (saved_count + 1000000)
            
            # SQL запросы
            insert_listing_sql = f"""
                INSERT INTO listings (id, url, region, deal_type, rooms, area_total, 
                                    floor, address, seller_type, lat, lon, first_seen, last_seen)
                VALUES ({offer_id}, '{(offer.get('url') or '').replace("'", "''")}', 1, 'sale', {rooms}, {area or 0}, 
                        {floor}, '{(offer.get('address') or '').replace("'", "''")}', 'Unknown', 55.7558, 37.6176, 
                        NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    last_seen = NOW(),
                    is_active = TRUE;
            """
            
            # Выполняем через Docker
            result = subprocess.run([
                "docker", "exec", "-i", "realestate-postgres-1", 
                "psql", "-U", "realuser", "-d", "realdb"
            ], input=insert_listing_sql, text=True, capture_output=True)
            
            if result.returncode == 0:
                saved_count += 1
                LOGGER.info(f"💾 {saved_count}. Сохранено: {offer.get('title', 'N/A')[:50]}... - {offer.get('price', 'N/A')}")
                
                # Сохраняем цену
                if price_numeric:
                    insert_price_sql = f"""
                        INSERT INTO listing_prices (id, seen_at, price)
                        VALUES ({offer_id}, NOW(), {price_numeric})
                        ON CONFLICT (id, seen_at) DO NOTHING;
                    """
                    
                    subprocess.run([
                        "docker", "exec", "-i", "realestate-postgres-1", 
                        "psql", "-U", "realuser", "-d", "realdb"
                    ], input=insert_price_sql, text=True, capture_output=True)
            else:
                LOGGER.error(f"❌ Ошибка сохранения объявления {offer_id}: {result.stderr}")
                
        except Exception as e:
            LOGGER.error(f"❌ Ошибка обработки объявления {i+1}: {e}")
            continue
    
    LOGGER.info(f"\n✅ Сохранено в БД: {saved_count} объявлений из {len(offers)}")
    
    # Проверяем результат
    result = subprocess.run([
        "docker", "exec", "realestate-postgres-1", "psql", 
        "-U", "realuser", "-d", "realdb", "-c", 
        "SELECT COUNT(*) as total_listings FROM listings;"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        count_line = result.stdout.strip().split('\n')[-2]
        count = count_line.strip()
        LOGGER.info(f"📊 Всего записей в БД: {count}")
        
        # Показываем первые 5 записей
        result2 = subprocess.run([
            "docker", "exec", "realestate-postgres-1", "psql", 
            "-U", "realuser", "-d", "realdb", "-c", 
            "SELECT id, url, rooms, area_total FROM listings LIMIT 5;"
        ], capture_output=True, text=True)
        
        if result2.returncode == 0:
            LOGGER.info(f"\n📋 Первые 5 записей в БД:")
            LOGGER.info(result2.stdout)

if __name__ == "__main__":
    save_offers_to_db()
