#!/bin/bash
# Парсинг по частям - каждые 50 страниц сохраняются в БД
# Если оборвётся - продолжит с последней порции

cd /home/ubuntu/realestate
source .env
source venv/bin/activate

LOG="/tmp/cian_batch.log"
BATCH_SIZE=50
TOTAL_PAGES=2000
START_PAGE=${1:-1}  # Можно указать стартовую страницу

echo "$(date): Запуск батч-парсинга с страницы $START_PAGE" >> $LOG

for ((page=$START_PAGE; page<=$TOTAL_PAGES; page+=$BATCH_SIZE)); do
    END_PAGE=$((page + BATCH_SIZE - 1))
    if [ $END_PAGE -gt $TOTAL_PAGES ]; then
        END_PAGE=$TOTAL_PAGES
    fi

    echo "$(date): === ПОРЦИЯ: страницы $page - $END_PAGE ===" >> $LOG
    echo "$(date): === ПОРЦИЯ: страницы $page - $END_PAGE ==="

    # Удаляем лок если остался
    rm -f /tmp/cian_parser.lock

    # Парсим порцию
    python -m etl.collector_cian.cli to-db --pages $BATCH_SIZE --start-page $page >> $LOG 2>&1
    EXIT_CODE=$?

    if [ $EXIT_CODE -ne 0 ]; then
        echo "$(date): ОШИБКА на странице $page, код $EXIT_CODE" >> $LOG
        echo "$(date): Пауза 60 сек и повтор..." >> $LOG
        sleep 60
        rm -f /tmp/cian_parser.lock
        python -m etl.collector_cian.cli to-db --pages $BATCH_SIZE --start-page $page >> $LOG 2>&1
    fi

    # Проверяем сколько в базе
    COUNT=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
    echo "$(date): В базе: $COUNT объявлений" >> $LOG
    echo "$(date): В базе: $COUNT объявлений"

    # Сохраняем прогресс
    echo "$END_PAGE" > /tmp/cian_batch_progress.txt

    # Пауза между порциями
    sleep 5
done

echo "$(date): ГОТОВО! Все $TOTAL_PAGES страниц обработаны" >> $LOG
