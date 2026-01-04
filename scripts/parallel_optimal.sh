#!/bin/bash
# Оптимальный параллельный парсинг
# Фильтры: вторичка, без апартаментов, без долей, НЕ первый этаж, до 30 млн
# 4 воркера по количеству комнат: 1кк, 2кк, 3кк, 4+кк

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG_DIR="/tmp/cian_parallel"
rm -rf $LOG_DIR
mkdir -p $LOG_DIR

PAGES=200  # страниц на каждый сегмент (до 5600 объявлений на сегмент)

echo "$(date): === ОПТИМАЛЬНЫЙ ПАРАЛЛЕЛЬНЫЙ ПАРСИНГ ==="
echo "Фильтры: вторичка, без апартаментов, без долей, НЕ первый этаж, до 30 млн"
echo "4 воркера: 1кк, 2кк, 3кк, 4+кк"
echo ""

COUNT_BEFORE=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
echo "$(date): В базе до: $COUNT_BEFORE"

run_worker() {
    local WORKER_ID=$1
    local PAYLOAD=$2
    local DESC=$3
    local LOG_FILE="$LOG_DIR/worker_${WORKER_ID}.log"

    echo "$(date): Воркер $WORKER_ID ($DESC) запущен" >> $LOG_FILE
    CIAN_FORCE_RUN=1 python -m etl.collector_cian.cli to-db --payload "$PAYLOAD" --pages $PAGES >> $LOG_FILE 2>&1

    local EXIT_CODE=$?
    echo "$(date): Воркер $WORKER_ID завершён (код $EXIT_CODE)" >> $LOG_FILE
}

echo "$(date): Запуск 4 воркеров..."

run_worker 1 "etl/collector_cian/payloads/1kk_optimal.yaml" "1кк до 30млн" &
PID1=$!
echo "Воркер 1 (1кк): PID $PID1"

run_worker 2 "etl/collector_cian/payloads/2kk_optimal.yaml" "2кк до 30млн" &
PID2=$!
echo "Воркер 2 (2кк): PID $PID2"

run_worker 3 "etl/collector_cian/payloads/3kk_optimal.yaml" "3кк до 30млн" &
PID3=$!
echo "Воркер 3 (3кк): PID $PID3"

run_worker 4 "etl/collector_cian/payloads/4kk_plus_optimal.yaml" "4+кк до 30млн" &
PID4=$!
echo "Воркер 4 (4+кк): PID $PID4"

echo ""
echo "$(date): Все 4 воркера запущены!"
echo "PIDs: $PID1 $PID2 $PID3 $PID4"
echo "Логи: $LOG_DIR/worker_*.log"
echo ""
echo "21 000 объявлений ÷ 4 воркера = ~5250 на воркер"
echo "200 страниц × 28 = до 5600 объявлений на воркер"
echo ""

wait $PID1 $PID2 $PID3 $PID4

echo ""
echo "$(date): === ВСЕ ВОРКЕРЫ ЗАВЕРШЕНЫ ==="
COUNT_AFTER=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
ADDED=$((COUNT_AFTER - COUNT_BEFORE))
echo "$(date): Итого в базе: $COUNT_AFTER (+$ADDED новых)"
