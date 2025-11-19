#!/bin/bash
# Basic Alert Configuration
# TASK-PROD-018: Configure alerts for critical issues

set -euo pipefail

echo "🚨 Setting up basic alerting system..."

# Create alert script directory
ALERT_DIR="/opt/realestate/alerts"
sudo mkdir -p "$ALERT_DIR"
sudo chown $USER:$USER "$ALERT_DIR"

# Alert script template
cat > "$ALERT_DIR/alert.sh" <<'ALERTSCRIPT'
#!/bin/bash
# Generic alert script
# Usage: ./alert.sh <level> <subject> <message>

LEVEL="${1:-INFO}"
SUBJECT="${2:-Alert}"
MESSAGE="${3:-No message provided}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

LOG_FILE="/var/log/realestate/alerts.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Log alert
echo "[$TIMESTAMP] [$LEVEL] $SUBJECT: $MESSAGE" >> "$LOG_FILE"

# Send email if configured
if [ -n "${ALERT_EMAIL:-}" ]; then
    echo "$MESSAGE" | mail -s "[$LEVEL] $SUBJECT" "$ALERT_EMAIL" 2>/dev/null || true
fi

# Send to syslog
logger -t realestate-alert "[$LEVEL] $SUBJECT: $MESSAGE"

# Critical alerts can trigger additional actions
if [ "$LEVEL" = "CRITICAL" ]; then
    # Add custom actions here (e.g., SMS, PagerDuty, etc.)
    echo "CRITICAL alert: $SUBJECT" > /tmp/realestate_critical_alert.txt
fi
ALERTSCRIPT

chmod +x "$ALERT_DIR/alert.sh"

# Create monitoring script
cat > "$ALERT_DIR/monitor.sh" <<'MONITORSCRIPT'
#!/bin/bash
# Basic monitoring script - checks critical services

ALERT_SCRIPT="$ALERT_DIR/alert.sh"

# Check PostgreSQL
if ! docker ps | grep -q "realestate-postgres"; then
    "$ALERT_SCRIPT" "CRITICAL" "PostgreSQL Down" "PostgreSQL container is not running"
    exit 1
fi

# Check database connectivity
if ! docker exec realestate-postgres-1 pg_isready -U realuser &>/dev/null; then
    "$ALERT_SCRIPT" "CRITICAL" "Database Unreachable" "PostgreSQL is not responding"
    exit 1
fi

# Check web service
if ! systemctl is-active --quiet realestate-web; then
    "$ALERT_SCRIPT" "CRITICAL" "Web Service Down" "realestate-web service is not running"
    exit 1
fi

# Check disk space
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 90 ]; then
    "$ALERT_SCRIPT" "WARNING" "High Disk Usage" "Disk usage is at ${DISK_USAGE}%"
fi

# Check memory
MEM_USAGE=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ "$MEM_USAGE" -gt 90 ]; then
    "$ALERT_SCRIPT" "WARNING" "High Memory Usage" "Memory usage is at ${MEM_USAGE}%"
fi

# Check if web interface responds
if ! curl -sf http://localhost:8000/health &>/dev/null; then
    "$ALERT_SCRIPT" "WARNING" "Web Interface Unreachable" "Health check endpoint not responding"
fi

# Check if API responds
if ! curl -sf http://localhost:8080/health &>/dev/null; then
    "$ALERT_SCRIPT" "WARNING" "API Unreachable" "API health check endpoint not responding"
fi

echo "All checks passed"
MONITORSCRIPT

chmod +x "$ALERT_DIR/monitor.sh"

# Update PATH in monitor script
sed -i "s|ALERT_DIR=.*|ALERT_DIR=\"$ALERT_DIR\"|" "$ALERT_DIR/monitor.sh"

# Create log directory
sudo mkdir -p /var/log/realestate
sudo chown $USER:$USER /var/log/realestate

# Setup cron job for monitoring (runs every 5 minutes)
CRON_JOB="*/5 * * * * $ALERT_DIR/monitor.sh >> /var/log/realestate/monitor.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "monitor.sh"; then
    echo "✅ Monitoring cron job already exists"
else
    echo "📅 Adding monitoring cron job..."
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Cron job added (runs every 5 minutes)"
fi

# Test alert system
echo ""
echo "🧪 Testing alert system..."
"$ALERT_DIR/alert.sh" "INFO" "Test Alert" "Alerting system is working"

echo ""
echo "✅ Basic alerting setup complete!"
echo ""
echo "📋 Summary:"
echo "   Alert script: $ALERT_DIR/alert.sh"
echo "   Monitor script: $ALERT_DIR/monitor.sh"
echo "   Log file: /var/log/realestate/alerts.log"
echo "   Monitor log: /var/log/realestate/monitor.log"
echo "   Cron schedule: Every 5 minutes"
echo ""
echo "🔍 To view alerts:"
echo "   tail -f /var/log/realestate/alerts.log"
echo ""
echo "🔍 To test monitoring:"
echo "   $ALERT_DIR/monitor.sh"
echo ""
echo "📧 To configure email alerts, set ALERT_EMAIL environment variable:"
echo "   export ALERT_EMAIL=admin@example.com"
echo "   (Add to .env or systemd service file)"

