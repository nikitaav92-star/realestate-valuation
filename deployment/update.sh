#!/bin/bash
# 🔄 Update script for production

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🔄 Updating Real Estate Valuation System${NC}"
echo "========================================"
echo ""

cd /home/ubuntu/realestate

# Activate venv
source venv/bin/activate

# Pull latest code (if using git)
if [ -d ".git" ]; then
    echo -e "${YELLOW}📥 Pulling latest code...${NC}"
    git pull origin main || git pull origin master
fi

# Install dependencies
echo -e "${YELLOW}📦 Installing dependencies...${NC}"
pip install -r requirements.txt -q
pip install -r telegram_bot/requirements.txt -q

# Run migrations if any
if [ -d "db/migrations" ]; then
    echo -e "${YELLOW}🗄️  Running database migrations...${NC}"
    for migration in db/migrations/*.sql; do
        if [ -f "$migration" ]; then
            psql postgresql://realuser:strongpass123@localhost:5432/realdb -f "$migration" 2>&1 | grep -v "already exists" || true
        fi
    done
fi

# Restart services
echo -e "${YELLOW}♻️  Restarting services...${NC}"
sudo systemctl restart valuation-api
sudo systemctl restart valuation-bot 2>/dev/null || true
sleep 2

# Check status
echo ""
echo -e "${GREEN}✅ Update complete!${NC}"
echo ""
echo "Service status:"
sudo systemctl status valuation-api --no-pager | head -5
sudo systemctl status valuation-bot --no-pager | head -5 2>/dev/null || true
