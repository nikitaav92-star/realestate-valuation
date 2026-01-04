#!/bin/bash
# Умный батч-парсинг со сдвигом страниц
# Каждый батч = 100 страниц начиная с нужной позиции

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG="/tmp/cian_batch_collect.log"
BATCH_SIZE=100
TOTAL_PAGES=2000
START_BATCH=${1:-1}  # Можно указать стартовый батч

echo "$(date): === ЗАПУСК БАТЧ-ПАРСИНГА ===" >> $LOG
echo "$(date): Всего страниц: $TOTAL_PAGES, размер батча: $BATCH_SIZE" >> $LOG
echo "$(date): Начинаем с батча: $START_BATCH" >> $LOG

BATCH_NUM=$START_BATCH
while [ $BATCH_NUM -le $((TOTAL_PAGES / BATCH_SIZE)) ]; do
    START_PAGE=$(( (BATCH_NUM - 1) * BATCH_SIZE + 1 ))
    END_PAGE=$(( BATCH_NUM * BATCH_SIZE ))

    echo "" >> $LOG
    echo "$(date): ========================================" >> $LOG
    echo "$(date): БАТЧ $BATCH_NUM: страницы $START_PAGE - $END_PAGE" >> $LOG
    echo "$(date): ========================================" >> $LOG

    # Удаляем лок
    rm -f /tmp/cian_parser.lock

    # Проверяем сколько в базе до
    COUNT_BEFORE=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
    echo "$(date): В базе до батча: $COUNT_BEFORE" >> $LOG

    # Запускаем парсинг батча с указанием начальной страницы
    python -m etl.collector_cian.cli to-db --pages $BATCH_SIZE --start-page $START_PAGE >> $LOG 2>&1
    EXIT_CODE=$?

    if [ $EXIT_CODE -ne 0 ]; then
        echo "$(date): ОШИБКА! Код: $EXIT_CODE. Пауза 60 сек и повтор..." >> $LOG
        sleep 60
        rm -f /tmp/cian_parser.lock
        python -m etl.collector_cian.cli to-db --pages $BATCH_SIZE --start-page $START_PAGE >> $LOG 2>&1
    fi

    # Проверяем сколько в базе после
    COUNT_AFTER=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
    ADDED=$((COUNT_AFTER - COUNT_BEFORE))

    echo "$(date): В базе после: $COUNT_AFTER (+$ADDED новых)" >> $LOG
    echo "$(date): Батч $BATCH_NUM завершён" >> $LOG

    # Сохраняем прогресс
    echo "$BATCH_NUM" > /tmp/cian_batch_progress.txt

    # Если уже достаточно - выходим
    if [ $COUNT_AFTER -ge 50000 ]; then
        echo "$(date): Достигнуто 50000+ объявлений!" >> $LOG
        break
    fi

    # Переходим к следующему батчу
    BATCH_NUM=$((BATCH_NUM + 1))

    # Пауза между батчами
    echo "$(date): Пауза 30 сек..." >> $LOG
    sleep 30
done

echo "" >> $LOG
echo "$(date): === ПАРСИНГ ЗАВЕРШЁН ===" >> $LOG
FINAL_COUNT=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
echo "$(date): Итого в базе: $FINAL_COUNT объявлений" >> $LOG
