#!/bin/bash
# Автоматический запуск полного сканирования после завершения текущего парсинга
# Запущено: $(date)

LOG="/tmp/auto_full_scan.log"
LOCK="/tmp/cian_parser.lock"

echo "$(date): 🕐 Ожидание завершения текущего парсинга..." >> $LOG

# Ждём пока завершится текущий парсинг (проверяем каждые 60 сек)
while [ -f "$LOCK" ] || pgrep -f "etl.collector_cian.cli" > /dev/null 2>&1; do
    echo "$(date): ⏳ Парсинг ещё работает, ждём 60 сек..." >> $LOG
    sleep 60
done

echo "$(date): ✅ Текущий парсинг завершён!" >> $LOG

# Пауза перед запуском
sleep 10

# Проверяем сколько объявлений в базе
cd /home/ubuntu/realestate
source .env
COUNT=$(PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | tr -d ' ')
echo "$(date): 📊 В базе сейчас: $COUNT объявлений" >> $LOG

# Запуск полного боевого режима: 2000 страниц = ~50000 объявлений
echo "$(date): 🚀 ЗАПУСК ПОЛНОГО БОЕВОГО РЕЖИМА: 2000 страниц" >> $LOG

source venv/bin/activate
nohup python -m etl.collector_cian.cli to-db --pages 2000 > /tmp/cian_full_battle.log 2>&1 &
PID=$!

echo "$(date): 🎯 Запущен процесс PID=$PID" >> $LOG
echo "$(date): 📝 Лог парсинга: /tmp/cian_full_battle.log" >> $LOG

# Записать PID для мониторинга
echo $PID > /tmp/cian_full_battle.pid

echo "$(date): ✅ Боевой режим активирован! Спокойной ночи! 🌙" >> $LOG
