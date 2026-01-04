#!/bin/bash
# Полный сбор ВСЕХ объявлений по узким ценовым сегментам (1 млн)
# 8 параллельных воркеров для максимальной скорости
# С проверкой дубликатов - пропускаем сегменты где 95%+ дубликатов

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG_DIR="/tmp/cian_collect_all"
COMPLETED_FILE="/home/ubuntu/realestate/data/completed_segments.txt"
mkdir -p $LOG_DIR
mkdir -p "$(dirname $COMPLETED_FILE)"
touch "$COMPLETED_FILE"

PAGES=54        # Максимум страниц на CIAN
PARALLEL=8      # Параллельных воркеров
PAUSE=5         # Пауза между запусками (сек)
MIN_NEW_PCT=5   # Минимум % новых для продолжения парсинга сегмента

echo "$(date): === ПОЛНЫЙ СБОР ВСЕХ ОБЪЯВЛЕНИЙ ===" | tee -a $LOG_DIR/main.log
echo "Сегменты: 5-100 млн рублей, 10-200 м²" | tee -a $LOG_DIR/main.log
echo "Страниц на сегмент: $PAGES" | tee -a $LOG_DIR/main.log
echo "Параллельных воркеров: $PARALLEL" | tee -a $LOG_DIR/main.log
echo "Порог новых: $MIN_NEW_PCT%" | tee -a $LOG_DIR/main.log

get_count() {
    PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' '
}

# Проверка - сегмент уже полностью собран?
is_completed() {
    local name=$1
    grep -q "^${name}$" "$COMPLETED_FILE" 2>/dev/null
}

# Отметить сегмент как завершённый
mark_completed() {
    local name=$1
    if ! is_completed "$name"; then
        echo "$name" >> "$COMPLETED_FILE"
        echo "$(date): ✅ Сегмент $name помечен как завершённый (95%+ дубликатов)" >> $LOG_DIR/progress.log
    fi
}

COUNT_START=$(get_count)
echo "$(date): В базе до старта: $COUNT_START" | tee -a $LOG_DIR/main.log

# Список всех payload'ов - перемешиваем чтобы парсить 1kk,2kk,3kk,4kk параллельно
# Сортируем по цене, чтобы 1kk_5M, 2kk_5M, 3kk_5M шли рядом
PAYLOADS=($(ls etl/collector_cian/payloads/deep/*.yaml 2>/dev/null | sed 's/.*_\([0-9]*\)_[0-9]*\.yaml/\1 &/' | sort -n | cut -d' ' -f2))
TOTAL=${#PAYLOADS[@]}

# Считаем сколько уже завершено
COMPLETED_COUNT=$(wc -l < "$COMPLETED_FILE" 2>/dev/null || echo 0)
REMAINING=$((TOTAL - COMPLETED_COUNT))

echo "$(date): Всего сегментов: $TOTAL, завершено: $COMPLETED_COUNT, осталось: $REMAINING" | tee -a $LOG_DIR/main.log
echo "" | tee -a $LOG_DIR/main.log

# Функция запуска одного payload
run_payload() {
    local payload=$1
    local name=$(basename $payload .yaml)
    local log="$LOG_DIR/${name}.log"

    # Пропускаем если уже завершён
    if is_completed "$name"; then
        echo "$(date): SKIP $name (уже завершён)" >> $LOG_DIR/progress.log
        return 0
    fi

    # Считаем сколько было ДО
    local count_before=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')

    echo "$(date): START $name (в базе: $count_before)" >> $LOG_DIR/progress.log
    CIAN_FORCE_RUN=1 python -m etl.collector_cian.cli to-db --payload "$payload" --pages $PAGES --parse-details > $log 2>&1
    local result=$?

    # Считаем сколько стало ПОСЛЕ
    local count_after=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
    local new_count=$((count_after - count_before))

    # Считаем сколько объявлений было обработано (из лога)
    local processed=$(grep -c "Parsing details\|offers extracted" "$log" 2>/dev/null || echo 0)

    # Если обработано > 100 и новых < 5% - помечаем как завершённый
    if [ "$processed" -gt 100 ] && [ "$new_count" -lt $((processed * MIN_NEW_PCT / 100)) ]; then
        mark_completed "$name"
    fi

    echo "$(date): DONE $name (код $result, новых: $new_count, обработано: ~$processed, всего: $count_after)" >> $LOG_DIR/progress.log
}

export -f run_payload get_count is_completed mark_completed
export LOG_DIR PAGES POSTGRES_PASSWORD POSTGRES_USER POSTGRES_DB COMPLETED_FILE MIN_NEW_PCT

# Запуск с ограничением параллелизма
echo "$(date): Запуск $PARALLEL параллельных воркеров..." | tee -a $LOG_DIR/main.log

for payload in "${PAYLOADS[@]}"; do
    name=$(basename $payload .yaml)

    # Пропускаем если уже завершён (до запуска воркера)
    if is_completed "$name"; then
        continue
    fi

    # Ждём если уже запущено максимум воркеров
    while [ $(jobs -r | wc -l) -ge $PARALLEL ]; do
        sleep 1
    done

    run_payload "$payload" &
    sleep $PAUSE  # Небольшая пауза между стартами
done

# Ждём завершения всех
wait

COUNT_END=$(get_count)
ADDED=$((COUNT_END - COUNT_START))
COMPLETED_NOW=$(wc -l < "$COMPLETED_FILE" 2>/dev/null || echo 0)

echo "" | tee -a $LOG_DIR/main.log
echo "$(date): === ЦИКЛ ЗАВЕРШЁН ===" | tee -a $LOG_DIR/main.log
echo "Было: $COUNT_START" | tee -a $LOG_DIR/main.log
echo "Стало: $COUNT_END" | tee -a $LOG_DIR/main.log
echo "Добавлено: $ADDED" | tee -a $LOG_DIR/main.log
echo "Завершённых сегментов: $COMPLETED_NOW / $TOTAL" | tee -a $LOG_DIR/main.log

# Если все сегменты завершены - большая пауза
if [ "$COMPLETED_NOW" -ge "$TOTAL" ]; then
    echo "$(date): ВСЕ СЕГМЕНТЫ ЗАВЕРШЕНЫ! Пауза 1 час..." | tee -a $LOG_DIR/main.log
    sleep 3600
    # Сбрасываем список завершённых для нового цикла
    > "$COMPLETED_FILE"
else
    # Пауза 1 минута и перезапуск
    echo "$(date): Пауза 1 минута перед следующим циклом..." | tee -a $LOG_DIR/main.log
    sleep 60
fi

# Перезапуск скрипта
exec "$0"
