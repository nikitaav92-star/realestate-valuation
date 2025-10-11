#!/bin/bash
# Production script for scraping 100k CIAN offers
# Uses proxy-first strategy with 10 sessions

set -e

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                            ║"
echo "║   🚀 CIAN MASS SCRAPING - 100K OFFERS                                     ║"
echo "║                                                                            ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Activate environment
source .venv/bin/activate
source .env

# Load proxy pool
PROXIES=($(cat config/proxy_pool.txt | grep "^http"))
echo "📡 Loaded ${#PROXIES[@]} proxies from pool"
echo ""

# Track totals
TOTAL_OFFERS=0
TOTAL_PAGES=0
START_TIME=$(date +%s)

# Run 10 sessions
for session in {1..10}; do
    echo "════════════════════════════════════════════════════════════════════════════"
    echo "  SESSION $session/10"
    echo "════════════════════════════════════════════════════════════════════════════"
    
    # Select proxy for this session (round-robin)
    proxy_index=$(( ($session - 1) % ${#PROXIES[@]} ))
    export NODEMAVEN_PROXY_URL="${PROXIES[$proxy_index]}"
    
    echo "Using proxy: ${NODEMAVEN_PROXY_URL:0:60}..."
    echo ""
    
    # Run scraper
    python scripts/test_captcha_strategy.py \
        --pages 357 \
        --proxy-first-only
    
    # Parse metrics
    if [ -f logs/captcha_strategy_metrics.json ]; then
        SESSION_OFFERS=$(cat logs/captcha_strategy_metrics.json | jq -r '.offers_collected')
        SESSION_PAGES=$(cat logs/captcha_strategy_metrics.json | jq -r '.pages_scraped')
        
        TOTAL_OFFERS=$((TOTAL_OFFERS + SESSION_OFFERS))
        TOTAL_PAGES=$((TOTAL_PAGES + SESSION_PAGES))
        
        echo ""
        echo "✅ Session $session complete!"
        echo "   Offers: $SESSION_OFFERS"
        echo "   Pages: $SESSION_PAGES"
        echo "   Total so far: $TOTAL_OFFERS offers"
        echo ""
    fi
    
    # Wait between sessions (except last)
    if [ $session -lt 10 ]; then
        echo "⏳ Waiting 60 seconds before next session..."
        sleep 60
    fi
done

# Calculate final stats
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                            ║"
echo "║   🎉 SCRAPING COMPLETE!                                                   ║"
echo "║                                                                            ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 FINAL STATISTICS:"
echo "════════════════════════════════════════════════════════════════════════════"
echo "  Total Offers:  $TOTAL_OFFERS"
echo "  Total Pages:   $TOTAL_PAGES"
echo "  Duration:      $DURATION_MIN minutes"
echo "  Sessions:      10"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""
echo "✅ Data saved to PostgreSQL database: realdb"
echo "📊 View in Metabase: https://realestate.ourdocs.org/"
echo ""

