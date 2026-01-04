#!/bin/bash
# 🚀 Quick Production Deployment Script
# Usage: ./quick_deploy.sh yourdomain.com your_bot_token

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Real Estate Valuation - Production Deployment${NC}"
echo "========================================"
echo ""

# Check arguments
if [ "$#" -lt 1 ]; then
    echo -e "${RED}❌ Error: Domain name required${NC}"
    echo ""
    echo "Usage: $0 <domain> [bot_token]"
    echo "Example: $0 valuation.yourdomain.com 123456:ABC-DEF..."
    exit 1
fi

DOMAIN=$1
BOT_TOKEN=${2:-""}
PROJECT_DIR="/home/ubuntu/realestate"

echo "📋 Configuration:"
echo "  Domain: $DOMAIN"
echo "  Project Dir: $PROJECT_DIR"
echo ""

# Check if running as non-root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}❌ Don't run this script as root${NC}"
   exit 1
fi

# Step 1: Install Nginx
echo -e "${YELLOW}📦 Step 1/8: Installing Nginx...${NC}"
if ! command -v nginx &> /dev/null; then
    sudo apt update
    sudo apt install -y nginx
    sudo systemctl enable nginx
    sudo systemctl start nginx
    echo -e "${GREEN}✅ Nginx installed${NC}"
else
    echo -e "${GREEN}✅ Nginx already installed${NC}"
fi

# Step 2: Install Certbot
echo -e "${YELLOW}🔒 Step 2/8: Installing Certbot...${NC}"
if ! command -v certbot &> /dev/null; then
    sudo apt install -y certbot python3-certbot-nginx
    echo -e "${GREEN}✅ Certbot installed${NC}"
else
    echo -e "${GREEN}✅ Certbot already installed${NC}"
fi

# Step 3: Create Nginx config
echo -e "${YELLOW}⚙️  Step 3/8: Configuring Nginx...${NC}"

# First, create simple HTTP-only config for SSL certificate
sudo tee /etc/nginx/sites-available/valuation > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/valuation /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # Remove default site
sudo nginx -t && sudo systemctl reload nginx
echo -e "${GREEN}✅ Nginx configured (HTTP only)${NC}"

# Step 4: Get SSL certificate
echo -e "${YELLOW}🔒 Step 4/8: Obtaining SSL certificate...${NC}"
echo "Note: Make sure DNS A record for $DOMAIN points to this server!"
read -p "Press Enter to continue or Ctrl+C to cancel..."

if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    sudo certbot certonly --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || {
        echo -e "${YELLOW}⚠️  SSL certificate not obtained. Continuing with HTTP only...${NC}"
    }
else
    echo -e "${GREEN}✅ SSL certificate already exists${NC}"
fi

# Step 5: Update Nginx config with HTTPS
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo -e "${YELLOW}🔒 Step 5/8: Configuring HTTPS...${NC}"
    
    sudo tee /etc/nginx/sites-available/valuation > /dev/null <<EOF
# HTTP - redirect to HTTPS
server {
    listen 80;
    server_name $DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name $DOMAIN;
    
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    access_log /var/log/nginx/valuation_access.log;
    error_log /var/log/nginx/valuation_error.log;
    
    location /static/ {
        alias $PROJECT_DIR/static/;
        expires 30d;
    }
    
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    client_max_body_size 10M;
}
EOF
    
    sudo nginx -t && sudo systemctl reload nginx
    echo -e "${GREEN}✅ HTTPS configured${NC}"
else
    echo -e "${YELLOW}⚠️  Skipping HTTPS configuration (no SSL cert)${NC}"
fi

# Step 6: Install Gunicorn
echo -e "${YELLOW}📦 Step 6/8: Installing Gunicorn...${NC}"
cd $PROJECT_DIR
source venv/bin/activate
pip install gunicorn > /dev/null 2>&1
echo -e "${GREEN}✅ Gunicorn installed${NC}"

# Step 7: Create systemd services
echo -e "${YELLOW}⚙️  Step 7/8: Creating systemd services...${NC}"

# Create log directory
sudo mkdir -p /var/log/valuation
sudo chown ubuntu:ubuntu /var/log/valuation

# API service
sudo tee /etc/systemd/system/valuation-api.service > /dev/null <<EOF
[Unit]
Description=Real Estate Valuation API
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
Environment="PG_DSN=postgresql://realuser:strongpass123@localhost:5432/realdb"
ExecStart=$PROJECT_DIR/venv/bin/gunicorn api.v1.valuation:app \\
    --workers 4 \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 127.0.0.1:8001 \\
    --timeout 120 \\
    --access-logfile /var/log/valuation/access.log \\
    --error-logfile /var/log/valuation/error.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Bot service (if token provided)
if [ -n "$BOT_TOKEN" ]; then
    sudo tee /etc/systemd/system/valuation-bot.service > /dev/null <<EOF
[Unit]
Description=Valuation Telegram Bot
After=network.target valuation-api.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$PROJECT_DIR/telegram_bot
Environment="PATH=$PROJECT_DIR/venv/bin"
Environment="TELEGRAM_BOT_TOKEN=$BOT_TOKEN"
Environment="VALUATION_API_URL=http://localhost:8001"
Environment="PG_DSN=postgresql://realuser:strongpass123@localhost:5432/realdb"
ExecStart=$PROJECT_DIR/venv/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
fi

# Reload systemd
sudo systemctl daemon-reload
echo -e "${GREEN}✅ Systemd services created${NC}"

# Step 8: Start services
echo -e "${YELLOW}🚀 Step 8/8: Starting services...${NC}"

sudo systemctl enable valuation-api
sudo systemctl restart valuation-api

if [ -n "$BOT_TOKEN" ]; then
    sudo systemctl enable valuation-bot
    sudo systemctl restart valuation-bot
fi

sleep 3

# Check status
echo ""
echo -e "${GREEN}========================================"
echo "✅ Deployment Complete!"
echo "========================================${NC}"
echo ""

# Show status
echo "📊 Service Status:"
echo ""
sudo systemctl status valuation-api --no-pager | head -5
if [ -n "$BOT_TOKEN" ]; then
    sudo systemctl status valuation-bot --no-pager | head -5
fi

echo ""
echo -e "${GREEN}🌐 Your site is available at:${NC}"
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "   https://$DOMAIN"
else
    echo "   http://$DOMAIN"
fi

echo ""
echo -e "${YELLOW}📋 Useful commands:${NC}"
echo "   View API logs:  sudo journalctl -u valuation-api -f"
echo "   View bot logs:  sudo journalctl -u valuation-bot -f"
echo "   Restart API:    sudo systemctl restart valuation-api"
echo "   Check status:   sudo systemctl status valuation-api"
echo ""
echo -e "${GREEN}✨ Done! Your valuation system is now running in production!${NC}"
