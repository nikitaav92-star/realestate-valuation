#!/usr/bin/env python3
"""Показывает красивые результаты из БД."""

import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def format_price(price):
    """Форматирует цену в читаемый вид."""
    if not price:
        return "N/A"
    return f"{price:,} ₽".replace(",", " ")

def format_price_per_sqm(price, area):
    """Вычисляет цену за м²."""
    if not price or not area or area == 0:
        return "N/A"
    return f"{int(price/area):,} ₽/м²".replace(",", " ")

def show_database_results():
    """Показывает результаты из БД в красивом виде."""
    
    LOGGER.info("🏠 РЕАЛЬНЫЕ ОБЪЯВЛЕНИЯ CIAN В БАЗЕ ДАННЫХ")
    LOGGER.info("=" * 80)
    
    # Получаем данные из БД
    result = subprocess.run([
        "docker", "exec", "realestate-postgres-1", "psql", 
        "-U", "realuser", "-d", "realdb", "-c", """
        SELECT 
            l.id, 
            l.rooms, 
            l.area_total, 
            l.floor, 
            lp.price,
            l.url
        FROM listings l 
        LEFT JOIN listing_prices lp ON l.id = lp.id 
        WHERE l.rooms > 0 AND l.area_total > 0
        ORDER BY l.area_total DESC
        LIMIT 15;
        """
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        LOGGER.error(f"❌ Ошибка БД: {result.stderr}")
        return
    
    # Парсим результат
    lines = result.stdout.strip().split('\n')
    if len(lines) < 4:
        LOGGER.error("❌ Нет данных в БД")
        return
    
    # Пропускаем заголовки и разделители
    data_lines = []
    for line in lines[3:]:
        if line.strip() and not line.startswith('(') and not line.startswith('-'):
            data_lines.append(line.strip())
    
    LOGGER.info(f"📊 Найдено {len(data_lines)} объявлений с полной информацией")
    LOGGER.info("=" * 80)
    
    # Показываем данные
    for i, line in enumerate(data_lines, 1):
        if not line:
            continue
            
        # Парсим строку (формат: id | rooms | area | floor | price | url)
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 6:
            try:
                offer_id = parts[0]
                rooms = int(parts[1]) if parts[1] else 0
                area = float(parts[2]) if parts[2] else 0
                floor = int(parts[3]) if parts[3] else 0
                price = int(parts[4]) if parts[4] else 0
                url = parts[5]
                
                # Форматируем
                room_text = "Студия" if rooms == 0 else f"{rooms}-комн"
                price_formatted = format_price(price)
                price_per_sqm = format_price_per_sqm(price, area)
                
                LOGGER.info(f"{i:2d}. {room_text} квартира, {area:.1f} м², {floor} этаж")
                LOGGER.info(f"    💰 {price_formatted} ({price_per_sqm})")
                LOGGER.info(f"    🔗 ID: {offer_id}")
                LOGGER.info(f"    📄 {url}")
                LOGGER.info("")
                
            except Exception as e:
                LOGGER.error(f"❌ Ошибка парсинга строки {i}: {e}")
                continue
    
    # Статистика
    LOGGER.info("📈 СТАТИСТИКА:")
    
    # Подсчитываем статистику
    total_offers = len(data_lines)
    total_price = 0
    total_area = 0
    room_counts = {}
    
    for line in data_lines:
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 5:
            try:
                rooms = int(parts[1]) if parts[1] else 0
                area = float(parts[2]) if parts[2] else 0
                price = int(parts[4]) if parts[4] else 0
                
                total_price += price
                total_area += area
                room_counts[rooms] = room_counts.get(rooms, 0) + 1
                
            except:
                continue
    
    if total_offers > 0:
        avg_price = total_price / total_offers
        avg_area = total_area / total_offers
        
        LOGGER.info(f"   📊 Всего объявлений: {total_offers}")
        LOGGER.info(f"   💰 Средняя цена: {format_price(int(avg_price))}")
        LOGGER.info(f"   📐 Средняя площадь: {avg_area:.1f} м²")
        LOGGER.info(f"   💵 Средняя цена за м²: {format_price_per_sqm(int(avg_price), avg_area)}")
        
        LOGGER.info(f"\n   🏠 Распределение по комнатам:")
        for rooms in sorted(room_counts.keys()):
            count = room_counts[rooms]
            room_text = "Студия" if rooms == 0 else f"{rooms}-комн"
            LOGGER.info(f"      {room_text}: {count} объявлений")
    
    LOGGER.info("=" * 80)

if __name__ == "__main__":
    show_database_results()

