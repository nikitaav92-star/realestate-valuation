#!/bin/bash
# Запуск мониторинга CIAN

cd /home/ubuntu/realestate
source venv/bin/activate

# Переменные БД
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=cian
export DB_USER=cian
export DB_PASSWORD=strongpass123

# Telegram (раскомментировать и заполнить)
# export TELEGRAM_BOT_TOKEN="your_token"
# export TELEGRAM_CHAT_ID="your_chat_id"

# Режимы:
# monitor - непрерывный мониторинг (каждые 15 мин)
# initial - первичный сбор (указать --pages)
# once    - однократный запуск

MODE=${1:-monitor}
PAGES=${2:-5}
INTERVAL=${3:-15}

echo "🚀 Запуск CIAN монитора"
echo "   Режим: $MODE"
echo "   Страниц: $PAGES"
echo "   Интервал: $INTERVAL мин"
echo ""

python -m etl.continuous_monitor --mode $MODE --pages $PAGES --interval $INTERVAL
