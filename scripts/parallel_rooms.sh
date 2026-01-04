#!/bin/bash
# Параллельный парсинг по комнатам и ценовым диапазонам
# 8 воркеров = 8 браузеров одновременно

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG_DIR="/tmp/cian_parallel"
rm -rf $LOG_DIR
mkdir -p $LOG_DIR

PAGES=100  # страниц на каждый сегмент

echo "$(date): === ЗАПУСК ПАРАЛЛЕЛЬНОГО ПАРСИНГА (8 воркеров) ==="
echo "Фильтры: вторичка, без апартаментов, без долей"

COUNT_BEFORE=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
echo "$(date): В базе до: $COUNT_BEFORE"

# Функция для запуска воркера
run_worker() {
    local WORKER_ID=$1
    local PAYLOAD=$2
    local DESC=$3
    local LOG_FILE="$LOG_DIR/worker_${WORKER_ID}.log"

    echo "$(date): Воркер $WORKER_ID ($DESC) запущен" >> $LOG_FILE
    CIAN_FORCE_RUN=1 python -m etl.collector_cian.cli to-db --payload "$PAYLOAD" --pages $PAGES >> $LOG_FILE 2>&1
    echo "$(date): Воркер $WORKER_ID завершён" >> $LOG_FILE
}

echo "$(date): Запуск 8 воркеров..."

# 1кк квартиры
run_worker 1 "etl/collector_cian/payloads/1k_5_10m.yaml" "1кк 5-10млн" &
PID1=$!
echo "Воркер 1 (1кк 5-10млн): PID $PID1"

run_worker 2 "etl/collector_cian/payloads/1k_10_15m.yaml" "1кк 10-15млн" &
PID2=$!
echo "Воркер 2 (1кк 10-15млн): PID $PID2"

# 2кк квартиры
run_worker 3 "etl/collector_cian/payloads/2k_5_10m.yaml" "2кк 5-10млн" &
PID3=$!
echo "Воркер 3 (2кк 5-10млн): PID $PID3"

run_worker 4 "etl/collector_cian/payloads/2k_10_15m.yaml" "2кк 10-15млн" &
PID4=$!
echo "Воркер 4 (2кк 10-15млн): PID $PID4"

run_worker 5 "etl/collector_cian/payloads/2k_15_20m.yaml" "2кк 15-20млн" &
PID5=$!
echo "Воркер 5 (2кк 15-20млн): PID $PID5"

# 3кк квартиры
run_worker 6 "etl/collector_cian/payloads/3k_10_20m.yaml" "3кк 10-20млн" &
PID6=$!
echo "Воркер 6 (3кк 10-20млн): PID $PID6"

run_worker 7 "etl/collector_cian/payloads/3k_20m_plus.yaml" "3кк 20млн+" &
PID7=$!
echo "Воркер 7 (3кк 20млн+): PID $PID7"

# 4+кк квартиры
run_worker 8 "etl/collector_cian/payloads/4k_plus.yaml" "4+кк" &
PID8=$!
echo "Воркер 8 (4+кк): PID $PID8"

echo ""
echo "$(date): Все 8 воркеров запущены!"
echo "PIDs: $PID1 $PID2 $PID3 $PID4 $PID5 $PID6 $PID7 $PID8"
echo "Логи: $LOG_DIR/worker_*.log"
echo ""

# Ждём завершения
wait $PID1 $PID2 $PID3 $PID4 $PID5 $PID6 $PID7 $PID8

echo ""
echo "$(date): === ВСЕ ВОРКЕРЫ ЗАВЕРШЕНЫ ==="
COUNT_AFTER=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
ADDED=$((COUNT_AFTER - COUNT_BEFORE))
echo "$(date): Итого в базе: $COUNT_AFTER (+$ADDED новых)"
