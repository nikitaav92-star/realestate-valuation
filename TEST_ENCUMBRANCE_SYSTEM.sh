#!/bin/bash
# Комплексный тест системы анализа обременений

echo "🧪 ТЕСТ СИСТЕМЫ АНАЛИЗА ОБРЕМЕНЕНИЙ"
echo "===================================="
echo ""

cd /home/ubuntu/realestate
source venv/bin/activate

echo "1️⃣ Тест анализатора (встроенные примеры)..."
python3 etl/encumbrance_analyzer.py
echo ""

echo "2️⃣ Анализ существующих описаний в БД..."
python3 scripts/analyze_existing_descriptions.py
echo ""

echo "3️⃣ Проверка статистики в БД..."
export PGPASSWORD=strongpass123
psql -h localhost -U realuser -d realdb -c "
SELECT 
    '✅ Статистика' as status,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE has_encumbrances = TRUE) as with_encumbrances,
    COUNT(*) FILTER (WHERE is_error = TRUE) as errors,
    ROUND(COUNT(*) FILTER (WHERE has_encumbrances = TRUE)::numeric / COUNT(*)::numeric * 100, 1) as encumbrance_percent
FROM listings 
WHERE is_active = TRUE;
"
echo ""

echo "4️⃣ Детали найденных обременений..."
psql -h localhost -U realuser -d realdb -c "
SELECT 
    id,
    url,
    LEFT(address_full, 50) as address,
    encumbrance_types,
    ROUND(encumbrance_confidence::numeric, 2) as confidence
FROM listings 
WHERE is_active = TRUE AND has_encumbrances = TRUE
ORDER BY encumbrance_confidence DESC;
"
echo ""

echo "✅ Тестирование завершено!"
echo ""
echo "📊 Для просмотра веб-интерфейса запустите:"
echo "   ./START_WEB_UI.sh"
echo ""
echo "   Затем откройте: http://localhost:5000"
