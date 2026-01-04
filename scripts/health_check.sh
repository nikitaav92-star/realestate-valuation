#!/bin/bash
# Health check and auto-restart script for CIAN parser infrastructure

LOG_FILE="/home/ubuntu/realestate/logs/health_check.log"
ALERT_FILE="/tmp/health_alert_sent"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

send_telegram_alert() {
    local message="$1"
    source /home/ubuntu/realestate/.env
    # Отправляем статусы в личный чат админа (не в группу заявок!)
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_ADMIN_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_ADMIN_CHAT_ID}" \
            -d "text=⚠️ HEALTH CHECK

${message}" \
            -d "parse_mode=HTML" > /dev/null
        log "Alert sent to admin chat"
    else
        log "Alert not sent (no TELEGRAM_ADMIN_CHAT_ID configured)"
    fi
}

# Check if service is running
check_service() {
    local service="$1"
    if ! systemctl is-active --quiet "$service"; then
        return 1
    fi
    return 0
}

# Check for stuck processes (running > 6 hours)
check_stuck_processes() {
    local stuck=$(ps aux | grep -E "etl.collector_cian|enrich_details" | grep -v grep | while read line; do
        pid=$(echo "$line" | awk '{print $2}')
        elapsed=$(ps -p "$pid" -o etimes= 2>/dev/null | tr -d ' ')
        if [ -n "$elapsed" ] && [ "$elapsed" -gt 21600 ]; then
            echo "$pid"
        fi
    done)
    echo "$stuck"
}

# Check database connection
check_database() {
    PGPASSWORD=strongpass123 psql -h localhost -U realuser -d realdb -c "SELECT 1" > /dev/null 2>&1
    return $?
}

# Check disk space (alert if < 10GB)
check_disk_space() {
    local available=$(df / | tail -1 | awk '{print $4}')
    if [ "$available" -lt 10000000 ]; then
        return 1
    fi
    return 0
}

# Check memory (alert if < 2GB available)
check_memory() {
    local available=$(free | grep Mem | awk '{print $7}')
    if [ "$available" -lt 2000000 ]; then
        return 1
    fi
    return 0
}

# Main health check
main() {
    local issues=""
    local fixed=""

    log "Starting health check..."

    # 1. Check web service
    if ! check_service "realestate-web"; then
        log "ERROR: realestate-web is down, restarting..."
        sudo systemctl restart realestate-web
        sleep 5
        if check_service "realestate-web"; then
            fixed="${fixed}• realestate-web перезапущен\n"
            log "OK: realestate-web restarted successfully"
        else
            issues="${issues}• realestate-web не запускается\n"
            log "CRITICAL: realestate-web failed to restart"
        fi
    fi

    # 2. Check database
    if ! check_database; then
        issues="${issues}• PostgreSQL недоступен\n"
        log "CRITICAL: Database connection failed"
    fi

    # 3. Check stuck processes
    stuck=$(check_stuck_processes)
    if [ -n "$stuck" ]; then
        log "WARNING: Found stuck processes: $stuck"
        for pid in $stuck; do
            kill "$pid" 2>/dev/null
            log "Killed stuck process $pid"
        done
        fixed="${fixed}• Убиты зависшие процессы\n"
    fi

    # 4. Check disk space
    if ! check_disk_space; then
        issues="${issues}• Мало места на диске (<10GB)\n"
        log "WARNING: Low disk space"
    fi

    # 5. Check memory
    if ! check_memory; then
        issues="${issues}• Мало памяти (<2GB)\n"
        log "WARNING: Low memory"
    fi

    # 6. Check timers are active
    for timer in cian-scraper cian-enrich cian-alerts cian-fast-scan; do
        if ! systemctl is-active --quiet "${timer}.timer"; then
            log "WARNING: ${timer}.timer is not active, enabling..."
            sudo systemctl enable --now "${timer}.timer"
            fixed="${fixed}• ${timer}.timer активирован\n"
        fi
    done

    # 7. Check if any parsing happened in last 2 hours
    recent_listings=$(PGPASSWORD=strongpass123 psql -h localhost -U realuser -d realdb -t -c \
        "SELECT COUNT(*) FROM listings WHERE first_seen_at > NOW() - INTERVAL '2 hours'" 2>/dev/null | tr -d ' ')
    if [ "$recent_listings" -lt 5 ]; then
        issues="${issues}• Мало новых объявлений за 2ч: ${recent_listings}\n"
        log "WARNING: Only $recent_listings new listings in last 2 hours"
    fi

    # Send alert if there are issues
    if [ -n "$issues" ]; then
        message="<b>Проблемы:</b>\n${issues}"
        if [ -n "$fixed" ]; then
            message="${message}\n<b>Исправлено:</b>\n${fixed}"
        fi
        send_telegram_alert "$message"
        log "Alert sent: $issues"
    elif [ -n "$fixed" ]; then
        send_telegram_alert "<b>Автоисправление:</b>\n${fixed}"
        log "Auto-fix alert sent"
    fi

    log "Health check completed"
}

main
