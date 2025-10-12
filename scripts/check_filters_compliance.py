#!/usr/bin/env python3
"""Проверяет соответствие результатов заданным фильтрам."""

import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def check_filters_compliance():
    """Проверяет соответствие результатов заданным фильтрам."""
    
    LOGGER.info("🔍 ПРОВЕРКА СООТВЕТСТВИЯ ФИЛЬТРАМ")
    LOGGER.info("=" * 60)
    
    # Заданные фильтры
    LOGGER.info("📋 ЗАДАННЫЕ ФИЛЬТРЫ:")
    LOGGER.info("   💰 Цена: до 30 000 000 ₽")
    LOGGER.info("   🏢 Этаж: от 2 (не первый этаж)")
    LOGGER.info("   🏠 Комнаты: студия (0), 1-к, 2-к, 3-к")
    LOGGER.info("   🏘️ Тип: вторичка")
    LOGGER.info("   💼 Сделка: продажа")
    LOGGER.info("")
    
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
        WHERE l.rooms >= 0
        ORDER BY lp.price DESC;
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
    
    LOGGER.info(f"📊 Всего объявлений в БД: {len(data_lines)}")
    LOGGER.info("=" * 60)
    
    # Проверяем каждый фильтр
    total_count = len(data_lines)
    price_violations = []
    floor_violations = []
    rooms_violations = []
    compliant = []
    
    for line in data_lines:
        if not line:
            continue
            
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 6:
            try:
                offer_id = parts[0]
                rooms = int(parts[1]) if parts[1] else 0
                area = float(parts[2]) if parts[2] else 0
                floor = int(parts[3]) if parts[3] else 0
                price = int(parts[4]) if parts[4] else 0
                url = parts[5]
                
                violations = []
                
                # Проверка цены (до 30 млн)
                if price > 30000000:
                    violations.append(f"Цена {price:,} ₽ > 30 млн")
                    price_violations.append((offer_id, price, rooms, area, floor))
                
                # Проверка этажа (от 2)
                if floor < 2:
                    violations.append(f"Этаж {floor} < 2")
                    floor_violations.append((offer_id, price, rooms, area, floor))
                
                # Проверка комнат (0, 1, 2, 3)
                if rooms not in [0, 1, 2, 3]:
                    violations.append(f"Комнат {rooms} не в списке (0,1,2,3)")
                    rooms_violations.append((offer_id, price, rooms, area, floor))
                
                if not violations:
                    compliant.append((offer_id, price, rooms, area, floor))
                    
            except Exception as e:
                LOGGER.error(f"❌ Ошибка парсинга: {e}")
                continue
    
    # Результаты проверки
    LOGGER.info("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ:")
    LOGGER.info(f"   ✅ Соответствуют фильтрам: {len(compliant)} из {total_count}")
    LOGGER.info(f"   ❌ Нарушения по цене: {len(price_violations)}")
    LOGGER.info(f"   ❌ Нарушения по этажу: {len(floor_violations)}")
    LOGGER.info(f"   ❌ Нарушения по комнатам: {len(rooms_violations)}")
    LOGGER.info("")
    
    # Показываем нарушения
    if price_violations:
        LOGGER.info("💰 НАРУШЕНИЯ ПО ЦЕНЕ (> 30 млн ₽):")
        for offer_id, price, rooms, area, floor in price_violations:
            price_formatted = f"{price:,} ₽".replace(",", " ")
            LOGGER.info(f"   ID {offer_id}: {price_formatted} ({rooms}-комн, {area} м², {floor} эт)")
        LOGGER.info("")
    
    if floor_violations:
        LOGGER.info("🏢 НАРУШЕНИЯ ПО ЭТАЖУ (< 2):")
        for offer_id, price, rooms, area, floor in floor_violations:
            price_formatted = f"{price:,} ₽".replace(",", " ")
            LOGGER.info(f"   ID {offer_id}: этаж {floor} ({rooms}-комн, {area} м², {price_formatted})")
        LOGGER.info("")
    
    if rooms_violations:
        LOGGER.info("🏠 НАРУШЕНИЯ ПО КОМНАТАМ (не 0,1,2,3):")
        for offer_id, price, rooms, area, floor in rooms_violations:
            price_formatted = f"{price:,} ₽".replace(",", " ")
            LOGGER.info(f"   ID {offer_id}: {rooms} комнат ({area} м², {floor} эт, {price_formatted})")
        LOGGER.info("")
    
    # Показываем соответствующие фильтрам
    if compliant:
        LOGGER.info("✅ СООТВЕТСТВУЮТ ФИЛЬТРАМ:")
        for offer_id, price, rooms, area, floor in compliant:
            price_formatted = f"{price:,} ₽".replace(",", " ")
            room_text = "Студия" if rooms == 0 else f"{rooms}-комн"
            LOGGER.info(f"   ID {offer_id}: {room_text}, {area} м², {floor} эт, {price_formatted}")
    
    LOGGER.info("")
    LOGGER.info("🎯 ВЫВОД:")
    compliance_rate = (len(compliant) / total_count * 100) if total_count > 0 else 0
    LOGGER.info(f"   Соответствие фильтрам: {compliance_rate:.1f}% ({len(compliant)}/{total_count})")
    
    if compliance_rate < 80:
        LOGGER.info("   ⚠️  Низкое соответствие фильтрам!")
        LOGGER.info("   💡 Рекомендация: обновить URL запроса с правильными фильтрами")
    else:
        LOGGER.info("   ✅ Хорошее соответствие фильтрам")

if __name__ == "__main__":
    check_filters_compliance()

