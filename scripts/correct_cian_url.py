#!/usr/bin/env python3
"""Создает корректный URL для CIAN с заданными фильтрами."""

import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def create_correct_cian_url():
    """Создает корректный URL для CIAN с заданными фильтрами."""
    
    LOGGER.info("🔧 СОЗДАНИЕ КОРРЕКТНОГО URL ДЛЯ CIAN")
    LOGGER.info("=" * 60)
    
    LOGGER.info("📋 ЗАДАННЫЕ ФИЛЬТРЫ:")
    LOGGER.info("   💰 Цена: до 30 000 000 ₽")
    LOGGER.info("   🏢 Этаж: от 2 (не первый этаж)")
    LOGGER.info("   🏠 Комнаты: студия (0), 1-к, 2-к, 3-к")
    LOGGER.info("   🏘️ Тип: вторичка")
    LOGGER.info("   💼 Сделка: продажа")
    LOGGER.info("   📍 Регион: Москва")
    LOGGER.info("")
    
    # Базовые параметры
    base_url = "https://www.cian.ru/cat.php"
    
    # Параметры фильтров
    params = {
        "deal_type": "sale",           # Продажа
        "engine_version": "2",         # Версия движка
        "offer_type": "flat",          # Квартиры
        "region": "1",                 # Москва
        "building_status": "secondary", # Вторичка
        "price_min": "1000000",        # Минимум 1 млн
        "price_max": "30000000",       # Максимум 30 млн
        "floor_min": "2",              # Минимум 2 этаж
        "room": "0,1,2,3",             # Студия, 1, 2, 3 комнаты
        "p": "1"                       # Страница
    }
    
    # Создаем URL
    param_strings = []
    for key, value in params.items():
        param_strings.append(f"{key}={value}")
    
    correct_url = base_url + "?" + "&".join(param_strings)
    
    LOGGER.info("✅ КОРРЕКТНЫЙ URL:")
    LOGGER.info(f"   {correct_url}")
    LOGGER.info("")
    
    # Альтернативный формат (более детальный)
    detailed_url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&building_status=secondary&price_min=1000000&price_max=30000000&floor_min=2&room=0&room=1&room=2&room=3&p=1"
    
    LOGGER.info("🔍 АЛЬТЕРНАТИВНЫЙ ФОРМАТ:")
    LOGGER.info(f"   {detailed_url}")
    LOGGER.info("")
    
    # JSON формат для API
    json_query = {
        "jsonQuery": {
            "region": {
                "type": "terms",
                "value": [1]
            },
            "engine_version": {
                "type": "term", 
                "value": 2
            },
            "deal_type": {
                "type": "term",
                "value": "sale"
            },
            "offer_type": {
                "type": "term",
                "value": "flat"
            },
            "building_status": {
                "type": "term",
                "value": "secondary"
            },
            "price": {
                "type": "range",
                "value": {
                    "gte": 1000000,
                    "lte": 30000000
                }
            },
            "floor": {
                "type": "range",
                "value": {
                    "gte": 2
                }
            },
            "room": {
                "type": "terms",
                "value": [0, 1, 2, 3]
            }
        },
        "limit": 20,
        "sort": {
            "type": "term",
            "value": "creation_date_desc"
        }
    }
    
    LOGGER.info("📄 JSON QUERY ДЛЯ API:")
    import json
    LOGGER.info(json.dumps(json_query, indent=2, ensure_ascii=False))
    LOGGER.info("")
    
    # Сравнение с текущим URL
    current_url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p=1"
    
    LOGGER.info("🔄 СРАВНЕНИЕ URL:")
    LOGGER.info(f"   ТЕКУЩИЙ:  {current_url}")
    LOGGER.info(f"   КОРРЕКТНЫЙ: {correct_url}")
    LOGGER.info("")
    
    LOGGER.info("❌ ПРОБЛЕМЫ ТЕКУЩЕГО URL:")
    LOGGER.info("   • НЕТ фильтра по цене (price_min/max)")
    LOGGER.info("   • НЕТ фильтра по этажу (floor_min)")
    LOGGER.info("   • НЕТ фильтра по комнатам (room)")
    LOGGER.info("   • НЕТ фильтра по типу (building_status)")
    LOGGER.info("")
    
    LOGGER.info("✅ РЕШЕНИЕ:")
    LOGGER.info("   Заменить URL в скрипте на корректный с фильтрами")
    
    return correct_url

if __name__ == "__main__":
    create_correct_cian_url()

