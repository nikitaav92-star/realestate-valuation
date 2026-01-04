#!/bin/bash

# 🤖 Script to start Telegram Valuation Bot

echo "🤖 Starting Real Estate Valuation Bot..."
echo ""

# Check if token is set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Error: TELEGRAM_BOT_TOKEN not set!"
    echo ""
    echo "Please run:"
    echo "  export TELEGRAM_BOT_TOKEN='your-token-here'"
    echo ""
    echo "Get token from @BotFather in Telegram"
    exit 1
fi

# Check if API is running
if ! curl -s http://localhost:8001/ > /dev/null; then
    echo "⚠️  Warning: Valuation API (port 8001) is not responding"
    echo "Please start the API first:"
    echo "  cd /home/ubuntu/realestate"
    echo "  source venv/bin/activate"
    echo "  uvicorn api.v1.valuation:app --host 0.0.0.0 --port 8001 &"
    echo ""
fi

# Install dependencies if needed
if ! python3 -c "import telegram" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
    echo ""
fi

# Start bot
echo "✅ Starting bot..."
python3 bot.py
