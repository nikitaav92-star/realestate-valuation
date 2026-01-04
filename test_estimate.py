#!/usr/bin/env python3
"""Быстрый тест системы оценки без API сервера."""
import sys
import os
sys.path.insert(0, '/home/ubuntu/realestate')

from etl.valuation import (
    PropertyFeatures, ValuationRequest, HybridEngine,
    BuildingType, BuildingHeight
)

print("=" * 80)
print("🧪 ТЕСТ СИСТЕМЫ ОЦЕНКИ")
print("=" * 80)

# Пример квартиры
features = PropertyFeatures(
    lat=55.7558,           # Координаты (центр Москвы)
    lon=37.6173,
    area_total=65.0,       # 65 м²
    rooms=2,               # 2 комнаты
    floor=5,               # 5 этаж
    total_floors=9,        # в 9-этажке
    building_type=BuildingType.PANEL,         # панельный дом
    building_height=BuildingHeight.MEDIUM     # средняя высотность
)

print("\n📋 Тестовая квартира:")
print(f"  📍 Координаты: {features.lat}, {features.lon}")
print(f"  📐 Площадь: {features.area_total} м²")
print(f"  🏠 Комнат: {features.rooms}")
print(f"  🏢 Этаж: {features.floor}/{features.total_floors}")
print(f"  🏗️  Тип: {features.building_type.value}")

request = ValuationRequest(
    features=features,
    k=10,                    # Найти 10 похожих
    max_distance_km=5.0,     # В радиусе 5 км
    max_age_days=90          # За последние 90 дней
)

print("\n🔄 Запуск оценки...\n")

try:
    engine = HybridEngine()
    result = engine.estimate(request)
    
    print("=" * 80)
    print("✅ РЕЗУЛЬТАТ ОЦЕНКИ")
    print("=" * 80)
    print()
    print(f"💰 Оценочная стоимость: {result.estimated_price:,.0f} ₽")
    print(f"📊 Цена за м²: {result.estimated_price_per_sqm:,.0f} ₽/м²")
    print(f"📈 Диапазон цен: {result.price_range_low:,.0f} - {result.price_range_high:,.0f} ₽")
    print(f"🎯 Уверенность: {result.confidence}%")
    print(f"🔧 Метод: {result.method_used}")
    print(f"⚖️  Веса: Grid {result.grid_weight:.0%} | KNN {result.knn_weight:.0%}")
    
    if result.knn_estimate and result.knn_estimate.comparables:
        print(f"\n🔍 Найдено сопоставимых: {len(result.knn_estimate.comparables)}")
        print(f"\n📍 Топ-5 похожих объектов:")
        for i, comp in enumerate(result.knn_estimate.comparables[:5], 1):
            print(f"  {i}. ID {comp.listing_id}: {comp.price:,.0f} ₽ "
                  f"({comp.price_per_sqm:,.0f} ₽/м²) | "
                  f"Расст: {comp.distance_km:.1f} км | "
                  f"Схожесть: {comp.similarity_score:.0f}%")
    
    if result.grid_estimate:
        print(f"\n📊 Grid детали:")
        print(f"  Уровень: {result.grid_estimate.fallback_level}")
        print(f"  Выборка: {result.grid_estimate.sample_size} объявлений")
        print(f"  Уверенность: {result.grid_estimate.confidence}%")
    
    print("\n" + "=" * 80)
    print("✅ ТЕСТ ПРОЙДЕН УСПЕШНО")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

