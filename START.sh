#!/bin/bash
# Быстрый запуск системы оценки

echo "🚀 ЗАПУСК СИСТЕМЫ ОЦЕНКИ НЕДВИЖИМОСТИ"
echo "======================================"

cd /home/ubuntu/realestate
source venv/bin/activate

echo ""
echo "📊 Шаг 1/2: Обновление агрегатов..."
python3 scripts/run_aggregation.py

echo ""
echo "🔥 Шаг 2/2: Запуск API сервера..."
echo ""
echo "✅ API будет доступен на: http://localhost:8000"
echo "📖 Документация: http://localhost:8000/docs"
echo ""
echo "Нажмите Ctrl+C для остановки"
echo ""

uvicorn api.v1.valuation:app --host 0.0.0.0 --port 8000
