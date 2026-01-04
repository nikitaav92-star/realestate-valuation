#!/bin/bash
# Бесконечный парсер CIAN с ротацией прокси
# Автоматически перезапускается и обновляет прокси

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG_DIR="/tmp/cian_infinite"
rm -rf $LOG_DIR
mkdir -p $LOG_DIR

PAGES_PER_CYCLE=50  # страниц за цикл (чтобы не банили)
PAUSE_BETWEEN_CYCLES=60  # пауза между циклами (секунды)
PROXY_REFRESH_INTERVAL=3600  # обновлять прокси каждый час

PAYLOADS=(
    "etl/collector_cian/payloads/1kk_optimal.yaml"
    "etl/collector_cian/payloads/2kk_optimal.yaml"
    "etl/collector_cian/payloads/3kk_optimal.yaml"
    "etl/collector_cian/payloads/4kk_plus_optimal.yaml"
)

LAST_PROXY_REFRESH=$(date +%s)
CYCLE=0

echo "$(date): === БЕСКОНЕЧНЫЙ ПАРСЕР CIAN ЗАПУЩЕН ===" | tee -a $LOG_DIR/main.log
echo "Фильтры: вторичка, без апартаментов, без долей, не первый этаж, до 30 млн, до 100 м²" | tee -a $LOG_DIR/main.log
echo "Страниц за цикл: $PAGES_PER_CYCLE" | tee -a $LOG_DIR/main.log
echo "" | tee -a $LOG_DIR/main.log

refresh_proxies() {
    echo "$(date): 🔄 Обновление прокси..." | tee -a $LOG_DIR/main.log
    python config/refresh_proxies.py >> $LOG_DIR/proxy.log 2>&1
    if [ $? -eq 0 ]; then
        echo "$(date): ✅ Прокси обновлены" | tee -a $LOG_DIR/main.log
        LAST_PROXY_REFRESH=$(date +%s)
    else
        echo "$(date): ❌ Ошибка обновления прокси" | tee -a $LOG_DIR/main.log
    fi
}

get_count() {
    PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' '
}

run_worker() {
    local WORKER_ID=$1
    local PAYLOAD=$2
    local LOG_FILE="$LOG_DIR/worker_${WORKER_ID}_cycle_${CYCLE}.log"

    echo "$(date): Воркер $WORKER_ID запущен (payload: $(basename $PAYLOAD))" >> $LOG_FILE
    CIAN_FORCE_RUN=1 python -m etl.collector_cian.cli to-db --payload "$PAYLOAD" --pages $PAGES_PER_CYCLE >> $LOG_FILE 2>&1
    local EXIT_CODE=$?
    echo "$(date): Воркер $WORKER_ID завершён (код $EXIT_CODE)" >> $LOG_FILE
    return $EXIT_CODE
}

# Первоначальное обновление прокси
refresh_proxies

while true; do
    CYCLE=$((CYCLE + 1))
    echo "" | tee -a $LOG_DIR/main.log
    echo "$(date): === ЦИКЛ $CYCLE ===" | tee -a $LOG_DIR/main.log

    COUNT_BEFORE=$(get_count)
    echo "$(date): В базе до: $COUNT_BEFORE" | tee -a $LOG_DIR/main.log

    # Проверка необходимости обновления прокси
    CURRENT_TIME=$(date +%s)
    TIME_SINCE_REFRESH=$((CURRENT_TIME - LAST_PROXY_REFRESH))
    if [ $TIME_SINCE_REFRESH -gt $PROXY_REFRESH_INTERVAL ]; then
        refresh_proxies
    fi

    # Запуск 4 воркеров параллельно
    echo "$(date): Запуск 4 воркеров..." | tee -a $LOG_DIR/main.log

    for i in 0 1 2 3; do
        run_worker $((i+1)) "${PAYLOADS[$i]}" &
        PIDS[$i]=$!
    done

    # Ожидание завершения всех воркеров
    for i in 0 1 2 3; do
        wait ${PIDS[$i]}
    done

    COUNT_AFTER=$(get_count)
    ADDED=$((COUNT_AFTER - COUNT_BEFORE))

    echo "$(date): Цикл $CYCLE завершён. В базе: $COUNT_AFTER (+$ADDED новых)" | tee -a $LOG_DIR/main.log

    # Проверка на rate limiting (если добавлено мало - увеличить паузу)
    if [ $ADDED -lt 10 ]; then
        echo "$(date): ⚠️ Мало новых записей, возможно rate limiting. Пауза 5 минут..." | tee -a $LOG_DIR/main.log
        refresh_proxies  # Обновляем прокси при проблемах
        sleep 300
    else
        echo "$(date): Пауза $PAUSE_BETWEEN_CYCLES секунд..." | tee -a $LOG_DIR/main.log
        sleep $PAUSE_BETWEEN_CYCLES
    fi
done
