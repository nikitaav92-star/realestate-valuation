#!/usr/bin/env python3
"""Применяет строгую фильтрацию к уже собранным данным."""

import json
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def apply_strict_filters():
    """Применяет строгую фильтрацию к собранным данным."""
    
    LOGGER.info("🔍 ПРИМЕНЕНИЕ СТРОГОЙ ФИЛЬТРАЦИИ К СОБРАННЫМ ДАННЫМ")
    LOGGER.info("=" * 60)
    
    # Читаем данные из файла
    try:
        with open('logs/CORRECT_cian_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_offers = data.get('all_offers', [])
        LOGGER.info(f"📁 Загружено {len(all_offers)} объявлений из файла")
        
    except Exception as e:
        LOGGER.error(f"❌ Ошибка чтения файла: {e}")
        return
    
    # Строгие фильтры
    MAX_PRICE = 30000000  # 30 млн ₽
    MIN_FLOOR = 2         # от 2 этажа
    ALLOWED_ROOMS = [0, 1, 2, 3]  # студия, 1, 2, 3 комнаты
    
    LOGGER.info("📋 СТРОГИЕ ФИЛЬТРЫ:")
    LOGGER.info(f"   💰 Цена: до {MAX_PRICE:,} ₽")
    LOGGER.info(f"   🏢 Этаж: от {MIN_FLOOR}")
    LOGGER.info(f"   🏠 Комнаты: {ALLOWED_ROOMS}")
    LOGGER.info("")
    
    strictly_valid = []
    
    for offer in all_offers:
        try:
            # Проверяем валидность
            if not offer.get('is_valid', False):
                continue
            
            # Извлекаем данные
            rooms = offer.get('rooms')
            area = offer.get('area')
            floor = offer.get('floor')
            price = offer.get('price_numeric')
            
            # СТРОГИЕ ПРОВЕРКИ
            validation_errors = []
            
            # 1. Проверка цены
            if not price or price > MAX_PRICE:
                validation_errors.append(f"Цена {price} > {MAX_PRICE}")
            
            # 2. Проверка этажа (КРИТИЧНО!)
            if floor is None:
                validation_errors.append("Этаж не указан")
            elif floor < MIN_FLOOR:
                validation_errors.append(f"Этаж {floor} < {MIN_FLOOR}")
            
            # 3. Проверка комнат
            if rooms is None:
                validation_errors.append("Комнаты не указаны")
            elif rooms not in ALLOWED_ROOMS:
                validation_errors.append(f"Комнат {rooms} не в списке {ALLOWED_ROOMS}")
            
            # Если все проверки пройдены
            if not validation_errors:
                strictly_valid.append(offer)
            else:
                LOGGER.warning(f"❌ ID {offer.get('id')}: {', '.join(validation_errors)}")
                
        except Exception as e:
            LOGGER.error(f"❌ Ошибка обработки объявления {offer.get('id')}: {e}")
            continue
    
    LOGGER.info(f"\n📊 РЕЗУЛЬТАТЫ СТРОГОЙ ФИЛЬТРАЦИИ:")
    LOGGER.info(f"   Всего объявлений: {len(all_offers)}")
    LOGGER.info(f"   Прошли строгую фильтрацию: {len(strictly_valid)}")
    LOGGER.info(f"   Отфильтровано: {len(all_offers) - len(strictly_valid)}")
    LOGGER.info("")
    
    if strictly_valid:
        LOGGER.info(f"✅ СТРОГО ВАЛИДНЫЕ ОБЪЯВЛЕНИЯ ({len(strictly_valid)}):")
        for i, offer in enumerate(strictly_valid, 1):
            LOGGER.info(f"\n{i}. {offer.get('title', 'N/A')}")
            LOGGER.info(f"   💰 {offer.get('price', 'N/A')}")
            LOGGER.info(f"   🏠 {offer.get('rooms', 'N/A')} комн. | {offer.get('area', 'N/A')} м² | {offer.get('floor', 'N/A')} эт.")
            LOGGER.info(f"   🔗 ID: {offer.get('id', 'N/A')}")
        
        # Сохраняем строго валидные данные
        output_file = "logs/STRICT_FILTERED_data.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'collection_info': {
                    'type': 'STRICT FILTERED CIAN DATA',
                    'filtered_at': '2025-10-11T21:50:00Z',
                    'strictly_valid_offers': len(strictly_valid),
                    'filters_applied': {
                        'max_price': MAX_PRICE,
                        'min_floor': MIN_FLOOR,
                        'allowed_rooms': ALLOWED_ROOMS,
                        'strict_mode': True
                    }
                },
                'strictly_valid_offers': strictly_valid
            }, f, ensure_ascii=False, indent=2)
        
        LOGGER.info(f"\n💾 Сохранено в файл: {output_file}")
        
        # Сохраняем в БД
        save_to_database(strictly_valid)
        
        return len(strictly_valid)
    else:
        LOGGER.error("❌ Нет строго валидных объявлений!")
        return 0

def save_to_database(offers):
    """Сохраняет строго валидные объявления в БД."""
    
    LOGGER.info(f"💾 Сохранение {len(offers)} строго валидных объявлений в БД...")
    
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
    
    LOGGER.info(f"💾 Сохранено в БД: {saved_count} строго валидных объявлений")

if __name__ == "__main__":
    valid_count = apply_strict_filters()
    
    if valid_count > 0:
        LOGGER.info(f"\n🎉 УСПЕХ: Найдено {valid_count} объявлений, строго соответствующих фильтрам!")
        
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
        LOGGER.error("\n❌ НЕУДАЧА: Строго валидные данные не найдены")

