#!/usr/bin/env python3
"""Парсит детальную информацию из title объявлений."""

import json
import re
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def parse_title_info(title):
    """Парсит информацию из title объявления."""
    if not title:
        return {}
    
    info = {}
    
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
        match = re.search(pattern, title.lower())
        if match:
            if 'студия' in pattern or 'однушка' in pattern:
                info['rooms'] = 0
            elif 'двушка' in pattern:
                info['rooms'] = 2
            elif 'трешка' in pattern:
                info['rooms'] = 3
            else:
                info['rooms'] = int(match.group(1))
            break
    
    # Парсим площадь
    area_patterns = [
        r'(\d+(?:,\d+)?)\s*м²',
        r'(\d+(?:\.\d+)?)\s*м2',
        r'(\d+(?:,\d+)?)\s*кв\.м',
        r'(\d+(?:\.\d+)?)\s*кв\s*м'
    ]
    
    for pattern in area_patterns:
        match = re.search(pattern, title.lower())
        if match:
            area_str = match.group(1).replace(',', '.')
            try:
                info['area'] = float(area_str)
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
        match = re.search(pattern, title.lower())
        if match:
            if len(match.groups()) >= 2:
                info['floor'] = int(match.group(1))
                info['total_floors'] = int(match.group(2))
            else:
                info['floor'] = int(match.group(1))
            break
    
    return info

def update_database_with_parsed_data():
    """Обновляет БД с парсированными данными из title."""
    
    # Читаем данные из файла
    try:
        with open('logs/REAL_cian_data_universal.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        offers = data['offers']
        LOGGER.info(f"📁 Загружено {len(offers)} объявлений для парсинга")
        
    except Exception as e:
        LOGGER.error(f"❌ Ошибка чтения файла: {e}")
        return
    
    updated_count = 0
    
    for offer in offers:
        try:
            title = offer.get('title', '')
            offer_id = offer.get('id')
            
            if not title or not offer_id:
                continue
            
            # Парсим данные из title
            parsed_info = parse_title_info(title)
            
            # Обновляем БД
            if parsed_info:
                update_sql = "UPDATE listings SET "
                updates = []
                params = []
                
                if 'rooms' in parsed_info:
                    updates.append("rooms = %s")
                    params.append(parsed_info['rooms'])
                
                if 'area' in parsed_info:
                    updates.append("area_total = %s")
                    params.append(parsed_info['area'])
                
                if 'floor' in parsed_info:
                    updates.append("floor = %s")
                    params.append(parsed_info['floor'])
                
                if updates:
                    update_sql += ", ".join(updates) + " WHERE id = %s"
                    params.append(offer_id)
                    
                    # Выполняем через Docker
                    import subprocess
                    
                    # Создаем SQL с параметрами
                    final_sql = update_sql
                    for i, param in enumerate(params[:-1]):
                        final_sql = final_sql.replace(f'%s', str(param), 1)
                    final_sql = final_sql.replace(f'%s', str(params[-1]))
                    
                    result = subprocess.run([
                        "docker", "exec", "-i", "realestate-postgres-1", 
                        "psql", "-U", "realuser", "-d", "realdb"
                    ], input=final_sql + ";", text=True, capture_output=True)
                    
                    if result.returncode == 0:
                        updated_count += 1
                        LOGGER.info(f"💾 Обновлено {updated_count}. ID {offer_id}: {title[:50]}...")
                        if 'rooms' in parsed_info:
                            LOGGER.info(f"   🏠 Комнаты: {parsed_info['rooms']}")
                        if 'area' in parsed_info:
                            LOGGER.info(f"   📐 Площадь: {parsed_info['area']} м²")
                        if 'floor' in parsed_info:
                            LOGGER.info(f"   🏢 Этаж: {parsed_info['floor']}")
                    else:
                        LOGGER.error(f"❌ Ошибка обновления ID {offer_id}: {result.stderr}")
                        
        except Exception as e:
            LOGGER.error(f"❌ Ошибка обработки объявления {offer.get('id')}: {e}")
            continue
    
    LOGGER.info(f"\n✅ Обновлено в БД: {updated_count} объявлений из {len(offers)}")
    
    # Показываем обновленные записи
    import subprocess
    result = subprocess.run([
        "docker", "exec", "realestate-postgres-1", "psql", 
        "-U", "realuser", "-d", "realdb", "-c", 
        "SELECT id, rooms, area_total, floor, url FROM listings WHERE rooms > 0 OR area_total > 0 LIMIT 10;"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        LOGGER.info(f"\n📋 ОБНОВЛЕННЫЕ ЗАПИСИ В БД:")
        LOGGER.info(result.stdout)

if __name__ == "__main__":
    update_database_with_parsed_data()

