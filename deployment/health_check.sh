#!/bin/bash
# 🏥 Health check script

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🏥 System Health Check"
echo "======================"
echo ""

DOMAIN=$(grep server_name /etc/nginx/sites-enabled/valuation 2>/dev/null | head -1 | awk '{print $2}' | tr -d ';')

# Check API via nginx
echo -n "🌐 API (Nginx): "
if [ -n "$DOMAIN" ]; then
    if curl -f -s -k https://$DOMAIN/ > /dev/null 2>&1 || curl -f -s http://$DOMAIN/ > /dev/null 2>&1; then
        echo -e "${GREEN}✅ OK${NC}"
    else
        echo -e "${RED}❌ DOWN${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Domain not configured${NC}"
fi

# Check API directly
echo -n "🔌 API (Direct): "
if curl -f -s http://localhost:8001/ > /dev/null; then
    echo -e "${GREEN}✅ OK${NC}"
else
    echo -e "${RED}❌ DOWN${NC}"
    echo "   Attempting restart..."
    sudo systemctl restart valuation-api
fi

# Check Bot service
echo -n "🤖 Bot: "
if sudo systemctl is-active --quiet valuation-bot 2>/dev/null; then
    echo -e "${GREEN}✅ Running${NC}"
else
    echo -e "${YELLOW}⚠️  Not configured or stopped${NC}"
fi

# Check Nginx
echo -n "🌍 Nginx: "
if sudo systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✅ Running${NC}"
else
    echo -e "${RED}❌ Stopped${NC}"
fi

# Check PostgreSQL
echo -n "🗄️  PostgreSQL: "
if sudo systemctl is-active --quiet postgresql; then
    echo -e "${GREEN}✅ Running${NC}"
    
    # Check DB connection
    if psql -U realuser -d realdb -c "SELECT 1;" > /dev/null 2>&1; then
        echo "   └─ Connection: ${GREEN}OK${NC}"
    else
        echo "   └─ Connection: ${RED}FAILED${NC}"
    fi
else
    echo -e "${RED}❌ Stopped${NC}"
fi

# Check disk space
echo ""
echo "💾 Disk Space:"
df -h / | tail -1 | awk '{printf "   Used: %s / %s (%s)\n", $3, $2, $5}'

DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 90 ]; then
    echo -e "   ${RED}⚠️  Warning: Disk usage above 90%!${NC}"
fi

# Check memory
echo ""
echo "🧠 Memory:"
free -h | grep Mem | awk '{printf "   Used: %s / %s\n", $3, $2}'

# Check API response time
echo ""
echo "⏱️  API Response Time:"
RESPONSE_TIME=$(curl -o /dev/null -s -w '%{time_total}' http://localhost:8001/ 2>/dev/null)
echo "   ${RESPONSE_TIME}s"

# Check recent errors
echo ""
echo "📋 Recent Logs:"
if [ -f "/var/log/valuation/error.log" ]; then
    ERROR_COUNT=$(tail -100 /var/log/valuation/error.log 2>/dev/null | grep -i error | wc -l)
    echo "   API errors (last 100 lines): $ERROR_COUNT"
fi

# Check database stats
echo ""
echo "📊 Database Stats:"
DB_SIZE=$(psql -U realuser -d realdb -t -c "SELECT pg_size_pretty(pg_database_size('realdb'));" 2>/dev/null | xargs)
echo "   Database size: $DB_SIZE"

LISTING_COUNT=$(psql -U realuser -d realdb -t -c "SELECT COUNT(*) FROM listings;" 2>/dev/null | xargs)
echo "   Total listings: $LISTING_COUNT"

GEOCODED=$(psql -U realuser -d realdb -t -c "SELECT COUNT(*) FROM listings WHERE lat IS NOT NULL;" 2>/dev/null | xargs)
echo "   Geocoded: $GEOCODED"

VALUATION_COUNT=$(psql -U realuser -d realdb -t -c "SELECT COUNT(*) FROM valuation_history;" 2>/dev/null | xargs)
echo "   Valuations done: $VALUATION_COUNT"

echo ""
echo "✅ Health check complete"
