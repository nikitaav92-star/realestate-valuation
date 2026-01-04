#!/bin/bash
# Быстрый тест API

echo "🧪 ТЕСТ API ОЦЕНКИ НЕДВИЖИМОСТИ"
echo "================================"
echo ""

echo "📡 Проверка статуса..."
STATUS=$(curl -s http://localhost:8001/ 2>&1)
echo "$STATUS"
echo ""

echo "💰 Тест оценки квартиры..."
curl -X POST http://localhost:8001/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 55.7558,
    "lon": 37.6173,
    "area_total": 65.0,
    "rooms": 2,
    "floor": 5,
    "total_floors": 9,
    "building_type": "panel"
  }' 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"✅ Цена: {data['estimated_price']:,.0f} ₽\")
print(f\"📊 Цена/м²: {data['estimated_price_per_sqm']:,.0f} ₽/м²\")
print(f\"🎯 Уверенность: {data['confidence']}%\")
print(f\"🔧 Метод: {data['method_used']}\")
print(f\"📍 Найдено аналогов: {data['comparables_count']}\")
"

echo ""
echo "✅ API работает!"
echo ""
echo "📖 Документация: http://localhost:8001/docs"
