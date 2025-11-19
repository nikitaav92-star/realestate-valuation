#!/bin/bash
# TASK-004: Setup Automated Daily Scraping
# Configure systemd timer to run scraper daily at 3 AM Moscow time

set -euo pipefail

echo "⏰ Setting up automated daily scraping..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "❌ This script must be run with sudo"
    echo "   Usage: sudo $0"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_FILE="/etc/systemd/system/cian-scraper.service"
TIMER_FILE="/etc/systemd/system/cian-scraper.timer"

# Copy service file
echo "📋 Installing systemd service..."
cp "$PROJECT_DIR/infra/systemd/cian-scraper.service" "$SERVICE_FILE"
chmod 644 "$SERVICE_FILE"

# Copy timer file
echo "📋 Installing systemd timer..."
cp "$PROJECT_DIR/infra/systemd/cian-scraper.timer" "$TIMER_FILE"
chmod 644 "$TIMER_FILE"

# Reload systemd
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

# Enable timer (not service - timer will trigger service)
echo "✅ Enabling timer..."
systemctl enable cian-scraper.timer

# Start timer
echo "🚀 Starting timer..."
systemctl start cian-scraper.timer

# Show status
echo ""
echo "📊 Timer status:"
systemctl status cian-scraper.timer --no-pager -l || true

echo ""
echo "✅ Automated daily scraping setup complete!"
echo ""
echo "📋 Useful commands:"
echo "   Status:  sudo systemctl status cian-scraper.timer"
echo "   Logs:    sudo journalctl -u cian-scraper.service -f"
echo "   Manual:  sudo systemctl start cian-scraper.service"
echo "   List:    sudo systemctl list-timers cian-scraper.timer"
echo ""
echo "⏰ Next run scheduled:"
systemctl list-timers cian-scraper.timer --no-pager | tail -n +2 || echo "   (check with: sudo systemctl list-timers)"

