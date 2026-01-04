#!/bin/bash
# Quick test script for investment calculator

echo "🧪 Testing Investment Calculator..."
echo ""

# Test 1: Basic API call
echo "1️⃣ Testing API /estimate with interest_price..."
curl -s -X POST http://localhost:8001/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 55.7558,
    "lon": 37.6173,
    "area_total": 71.7,
    "rooms": 2
  }' | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"✅ Market: {data['estimated_price']:,.0f} ₽\"); print(f\"💎 Interest: {data.get('interest_price', 'N/A') if isinstance(data.get('interest_price'), (int, float)) else 'N/A'}\")"

echo ""
echo "2️⃣ Checking database migration..."
PGPASSWORD=strongpass123 psql -h localhost -U realuser -d realdb -t -c "\d valuation_history" | grep -q "interest_price" && echo "✅ DB fields added" || echo "❌ DB migration failed"

echo ""
echo "3️⃣ Checking UI files..."
grep -q "interestPrice" /home/ubuntu/realestate/static/index.html && echo "✅ UI updated" || echo "❌ UI not updated"

echo ""
echo "4️⃣ Checking module..."
python3 -c "from api.v1.investment_calculator import calculate_interest_price; print('✅ Module imported')" 2>/dev/null || echo "❌ Module import failed"

echo ""
echo "🎉 All tests completed!"
echo ""
echo "🌐 Access: https://rating.ourdocs.org"
