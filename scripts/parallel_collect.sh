#!/bin/bash
# Параллельный парсинг с несколькими процессами
# Каждый процесс = отдельный ценовой диапазон = отдельный браузер
# Фильтры: вторичка, без апартаментов, без долей

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG_DIR="/tmp/cian_parallel"
mkdir -p $LOG_DIR

PAGES=100  # страниц на каждый диапазон

echo "$(date): === ЗАПУСК ПАРАЛЛЕЛЬНОГО ПАРСИНГА ==="
echo "Фильтры: вторичка, без апартаментов, без долей"

COUNT_BEFORE=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
echo "$(date): В базе до: $COUNT_BEFORE"

# Функция для запуска воркера
run_worker() {
    local WORKER_ID=$1
    local PAYLOAD=$2
    local PRICE_RANGE=$3
    local LOG_FILE="$LOG_DIR/worker_${WORKER_ID}.log"

    echo "$(date): Воркер $WORKER_ID ($PRICE_RANGE) запущен" >> $LOG_FILE
    echo "$(date): Payload: $PAYLOAD" >> $LOG_FILE

    # Каждый воркер использует --force-run чтобы не блокироваться
    CIAN_FORCE_RUN=1 python -m etl.collector_cian.cli to-db --payload "$PAYLOAD" --pages $PAGES >> $LOG_FILE 2>&1

    echo "$(date): Воркер $WORKER_ID завершён" >> $LOG_FILE
}

# Запускаем воркеры параллельно - 5 ценовых диапазонов
echo "$(date): Запуск 5 воркеров..."

run_worker 1 "etl/collector_cian/payloads/base.yaml" "до 10 млн" &
PID1=$!
echo "Воркер 1 (до 10млн): PID $PID1"

run_worker 2 "etl/collector_cian/payloads/price_10_15m.yaml" "10-15 млн" &
PID2=$!
echo "Воркер 2 (10-15млн): PID $PID2"

run_worker 3 "etl/collector_cian/payloads/price_15_20m.yaml" "15-20 млн" &
PID3=$!
echo "Воркер 3 (15-20млн): PID $PID3"

run_worker 4 "etl/collector_cian/payloads/price_20_30m.yaml" "20-30 млн" &
PID4=$!
echo "Воркер 4 (20-30млн): PID $PID4"

run_worker 5 "etl/collector_cian/payloads/price_30_50m.yaml" "30-50 млн" &
PID5=$!
echo "Воркер 5 (30-50млн): PID $PID5"

echo ""
echo "$(date): Все 5 воркеров запущены."
echo "PIDs: $PID1 $PID2 $PID3 $PID4 $PID5"
echo ""
echo "Логи воркеров: $LOG_DIR/worker_*.log"
echo ""

# Ждём завершения всех воркеров
wait $PID1 $PID2 $PID3 $PID4 $PID5

echo ""
echo "$(date): === ВСЕ ВОРКЕРЫ ЗАВЕРШЕНЫ ==="

# Итоговая статистика
COUNT_AFTER=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
ADDED=$((COUNT_AFTER - COUNT_BEFORE))
echo "$(date): Итого в базе: $COUNT_AFTER объявлений (+$ADDED новых)"
