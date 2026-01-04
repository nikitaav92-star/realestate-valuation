#!/bin/bash
# Парсинг по ценовым диапазонам
# Каждый диапазон = отдельный набор объявлений

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG="/tmp/cian_multi_price.log"
PAGES=100  # страниц на каждый диапазон

echo "$(date): === ЗАПУСК МУЛЬТИ-ЦЕНОВОГО ПАРСИНГА ===" >> $LOG

# Список payload файлов
PAYLOADS=(
    "etl/collector_cian/payloads/base.yaml"           # до 10 млн
    "etl/collector_cian/payloads/price_10_15m.yaml"   # 10-15 млн
    "etl/collector_cian/payloads/price_15_20m.yaml"   # 15-20 млн
    "etl/collector_cian/payloads/price_20_30m.yaml"   # 20-30 млн
)

for payload in "${PAYLOADS[@]}"; do
    echo "" >> $LOG
    echo "$(date): ========================================" >> $LOG
    echo "$(date): ДИАПАЗОН: $payload" >> $LOG
    echo "$(date): ========================================" >> $LOG

    rm -f /tmp/cian_parser.lock

    COUNT_BEFORE=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
    echo "$(date): В базе до: $COUNT_BEFORE" >> $LOG

    python -m etl.collector_cian.cli to-db --payload "$payload" --pages $PAGES >> $LOG 2>&1
    EXIT_CODE=$?

    COUNT_AFTER=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
    ADDED=$((COUNT_AFTER - COUNT_BEFORE))

    echo "$(date): В базе после: $COUNT_AFTER (+$ADDED новых)" >> $LOG
    echo "$(date): Диапазон завершён с кодом $EXIT_CODE" >> $LOG

    # Пауза между диапазонами
    echo "$(date): Пауза 60 сек..." >> $LOG
    sleep 60
done

echo "" >> $LOG
echo "$(date): === ПАРСИНГ ЗАВЕРШЁН ===" >> $LOG
FINAL_COUNT=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
echo "$(date): Итого в базе: $FINAL_COUNT объявлений" >> $LOG
