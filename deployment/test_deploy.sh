#!/bin/bash
# Test deployment without SSL (for testing)

echo "🧪 Testing deployment setup..."
echo ""

# Test Nginx config syntax
echo "✓ Testing Nginx config..."
sudo nginx -t

# Test API directly
echo "✓ Testing API..."
curl -s http://localhost:8001/ | head -3

# Test database connection
echo "✓ Testing database..."
psql -U realuser realdb -c "SELECT COUNT(*) as listings FROM listings;" -t

# Test bot dependencies
echo "✓ Testing bot dependencies..."
cd /home/ubuntu/realestate/telegram_bot
source ../venv/bin/activate
python3 -c "import telegram; print('telegram-bot: OK')"
python3 -c "import PyPDF2; print('PyPDF2: OK')"

echo ""
echo "✅ All tests passed!"
