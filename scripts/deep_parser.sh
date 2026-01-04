#!/bin/bash
# Глубокий парсер - собирает ВСЕ объявления по ценовым диапазонам

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG_DIR="/tmp/cian_deep"
mkdir -p $LOG_DIR

PAGES_PER_PAYLOAD=100  # максимум страниц на один payload

echo "$(date): === ГЛУБОКИЙ ПАРСЕР ЗАПУЩЕН ===" | tee -a $LOG_DIR/main.log

get_count() {
    PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' '
}

COUNT_BEFORE=$(get_count)
echo "$(date): В базе до: $COUNT_BEFORE" | tee -a $LOG_DIR/main.log

# Парсим все payload'ы последовательно
for payload in etl/collector_cian/payloads/deep/*.yaml; do
    name=$(basename $payload .yaml)
    echo "$(date): Парсинг $name..." | tee -a $LOG_DIR/main.log
    
    CIAN_FORCE_RUN=1 python -m etl.collector_cian.cli to-db \
        --payload "$payload" \
        --pages $PAGES_PER_PAYLOAD \
        >> $LOG_DIR/${name}.log 2>&1
    
    count=$(get_count)
    echo "$(date): $name завершён, в базе: $count" | tee -a $LOG_DIR/main.log
    
    # Пауза между payload'ами
    sleep 30
done

COUNT_AFTER=$(get_count)
ADDED=$((COUNT_AFTER - COUNT_BEFORE))

echo "" | tee -a $LOG_DIR/main.log
echo "$(date): === ГЛУБОКИЙ ПАРСИНГ ЗАВЕРШЁН ===" | tee -a $LOG_DIR/main.log
echo "$(date): Было: $COUNT_BEFORE, стало: $COUNT_AFTER (+$ADDED)" | tee -a $LOG_DIR/main.log
