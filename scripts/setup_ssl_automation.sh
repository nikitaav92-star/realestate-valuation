#!/bin/bash
# SSL/TLS Certificate Automation Setup
# TASK-PROD-019: Automatic certificate renewal

set -euo pipefail

echo "🔒 Setting up SSL/TLS certificate automation..."

# Check if certbot is installed
if ! command -v certbot &> /dev/null; then
    echo "❌ Certbot is not installed. Installing..."
    sudo apt update
    sudo apt install -y certbot python3-certbot-nginx
fi

# Get domain name from user or use default
DOMAIN="${1:-realestate.ourdocs.org}"
EMAIL="${2:-admin@ourdocs.org}"

echo "📋 Configuration:"
echo "   Domain: $DOMAIN"
echo "   Email: $EMAIL"
echo ""

# Check if certificate already exists
if sudo certbot certificates | grep -q "$DOMAIN"; then
    echo "✅ Certificate for $DOMAIN already exists"
    CERT_PATH=$(sudo certbot certificates | grep -A 5 "$DOMAIN" | grep "Certificate Path" | awk '{print $3}')
    echo "   Certificate Path: $CERT_PATH"
else
    echo "📝 Obtaining certificate..."
    echo "   Note: This requires Nginx configuration or Cloudflare Tunnel setup"
    echo "   Run manually: sudo certbot --nginx -d $DOMAIN --email $EMAIL --agree-tos --non-interactive"
fi

# Setup automatic renewal cron job
echo ""
echo "⏰ Setting up automatic renewal..."

# Create renewal script
sudo tee /usr/local/bin/certbot-renew-realestate.sh > /dev/null <<'SCRIPT'
#!/bin/bash
# Automatic certificate renewal for Real Estate Platform

LOG_FILE="/var/log/certbot-renewal.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting certificate renewal check..." >> "$LOG_FILE"

# Run certbot renewal
if certbot renew --quiet --nginx; then
    echo "[$DATE] Certificate renewal successful" >> "$LOG_FILE"
    # Reload nginx if renewal was successful
    if systemctl is-active --quiet nginx; then
        systemctl reload nginx
        echo "[$DATE] Nginx reloaded" >> "$LOG_FILE"
    fi
    exit 0
else
    echo "[$DATE] Certificate renewal failed or no renewal needed" >> "$LOG_FILE"
    exit 1
fi
SCRIPT

# Make script executable
sudo chmod +x /usr/local/bin/certbot-renew-realestate.sh

# Add cron job (runs twice daily at 3 AM and 3 PM)
CRON_JOB="0 3,15 * * * /usr/local/bin/certbot-renew-realestate.sh >> /var/log/certbot-renewal.log 2>&1"

# Check if cron job already exists
if sudo crontab -l 2>/dev/null | grep -q "certbot-renew-realestate"; then
    echo "✅ Cron job already exists"
else
    echo "📅 Adding cron job..."
    (sudo crontab -l 2>/dev/null; echo "$CRON_JOB") | sudo crontab -
    echo "✅ Cron job added"
fi

# Test renewal (dry-run)
echo ""
echo "🧪 Testing certificate renewal (dry-run)..."
if sudo certbot renew --dry-run --nginx &>/dev/null; then
    echo "✅ Dry-run successful - automation is working"
else
    echo "⚠️  Dry-run failed - check configuration"
fi

echo ""
echo "✅ SSL/TLS automation setup complete!"
echo ""
echo "📋 Summary:"
echo "   - Renewal script: /usr/local/bin/certbot-renew-realestate.sh"
echo "   - Cron schedule: Twice daily at 3 AM and 3 PM"
echo "   - Log file: /var/log/certbot-renewal.log"
echo ""
echo "🔍 To check renewal status:"
echo "   sudo tail -f /var/log/certbot-renewal.log"
echo ""
echo "🔍 To view certificates:"
echo "   sudo certbot certificates"
echo ""
echo "🔍 To manually renew:"
echo "   sudo certbot renew --nginx"

