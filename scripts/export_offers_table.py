#!/usr/bin/env python3
"""Export CIAN offers to readable table format."""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def format_price(price):
    """Format price in millions."""
    return f"{price / 1000000:.2f} млн ₽"

def export_to_table():
    """Export offers to readable table."""
    
    data_file = Path("logs/demo_cian_data.json")
    
    if not data_file.exists():
        LOGGER.error("❌ Data file not found")
        return
    
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    offers = data['offers']
    
    # Print header
    LOGGER.info("\n" + "="*150)
    LOGGER.info("🏠 CIAN ОБЪЯВЛЕНИЯ - ПОЛНЫЙ СПИСОК")
    LOGGER.info("="*150)
    LOGGER.info(f"Всего объявлений: {len(offers)}")
    LOGGER.info("="*150 + "\n")
    
    # Table header
    header = f"{'№':<5} {'Название':<30} {'Цена':<15} {'Адрес':<35} {'Комнат':<7} {'Площадь':<10} {'Этаж':<10} {'Продавец':<12} {'AI':<15}"
    LOGGER.info(header)
    LOGGER.info("-"*150)
    
    # Print each offer
    for i, offer in enumerate(offers, 1):
        row = (
            f"{i:<5} "
            f"{offer['title'][:28]:<30} "
            f"{format_price(offer['price_numeric']):<15} "
            f"{offer['address'][:33]:<35} "
            f"{offer['rooms']:<7} "
            f"{offer['area_total']:<10} "
            f"{offer['floor']:<10} "
            f"{offer['seller_type']:<12} "
            f"{offer['condition_label'][:10]} ({offer['condition_score']})"
        )
        LOGGER.info(row)
        
        # Add separator every 10 rows
        if i % 10 == 0:
            LOGGER.info("-"*150)
    
    LOGGER.info("\n" + "="*150)
    
    # Statistics
    avg_price = sum(o['price_numeric'] for o in offers) / len(offers)
    min_price = min(o['price_numeric'] for o in offers)
    max_price = max(o['price_numeric'] for o in offers)
    
    avg_area = sum(o['area_total'] for o in offers) / len(offers)
    avg_score = sum(o['condition_score'] for o in offers) / len(offers)
    
    LOGGER.info("📊 СТАТИСТИКА:")
    LOGGER.info(f"   Цена: {format_price(min_price)} - {format_price(max_price)} (средняя: {format_price(avg_price)})")
    LOGGER.info(f"   Площадь: средняя {avg_area:.1f} м²")
    LOGGER.info(f"   AI оценка: средняя {avg_score:.1f}/5")
    LOGGER.info(f"   Распределение по комнатам:")
    
    rooms_dist = {}
    for offer in offers:
        rooms = offer['rooms']
        rooms_dist[rooms] = rooms_dist.get(rooms, 0) + 1
    
    for rooms in sorted(rooms_dist.keys()):
        room_label = "Студия" if rooms == 0 else f"{rooms}-комн"
        LOGGER.info(f"      {room_label}: {rooms_dist[rooms]} объявлений")
    
    LOGGER.info("="*150 + "\n")

if __name__ == "__main__":
    export_to_table()

