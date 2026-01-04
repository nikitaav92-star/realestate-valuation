#!/bin/bash
# Мониторинг трафика через прокси
# Проверяет что НЕТ соединений к прокси серверам

cd /home/ubuntu/realestate

# NodeMaven proxy hosts (примерные адреса)
PROXY_PATTERNS="gate\.nodemaven\|proxy\.nodemaven\|rotating\|residential"

echo "=== МОНИТОРИНГ ПРОКСИ ТРАФИКА ==="
echo "Время: $(date)"
echo ""

# Проверка активных соединений
echo "--- Соединения к прокси (должно быть ПУСТО!) ---"
ss -tnp 2>/dev/null | grep -iE "$PROXY_PATTERNS" && echo "!!! ОБНАРУЖЕН ТРАФИК ЧЕРЕЗ ПРОКСИ !!!" || echo "OK: Нет соединений к прокси"
echo ""

# Проверка процессов с прокси в аргументах
echo "--- Процессы с proxy в аргументах (должно быть ПУСТО!) ---"
ps aux | grep -iE "proxy" | grep -v "grep\|monitor_proxy" | grep -v "WITHOUT proxy" | grep -v "get_cookies_with_proxy" && echo "!!! НАЙДЕНЫ ПРОЦЕССЫ С ПРОКСИ !!!" || echo "OK: Нет процессов с прокси"
echo ""

# Статистика сети
echo "--- Статистика сетевых соединений ---"
echo "CIAN соединений: $(ss -tnp 2>/dev/null | grep -E "cian|89\.108\.|51\.250\." | wc -l)"
echo "Всего ESTABLISHED: $(ss -tnp 2>/dev/null | grep ESTAB | wc -l)"
echo ""

# Статус парсеров
echo "--- Активные парсеры ---"
ps aux | grep -E "collector_cian|enrich" | grep -v grep | awk '{print $11, $12, $13}' | head -10
echo ""

echo "=== ПРОВЕРКА ЗАВЕРШЕНА ==="
