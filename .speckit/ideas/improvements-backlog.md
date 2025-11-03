# Real Estate Parser - Improvements Backlog

## High Priority

### 1. Fix Data Completeness Issues
**Status:** Needs Implementation  
**Effort:** Medium (2-3 days)  
**Impact:** High

**Description:**
Improve parser to extract rooms, area, and address from OfferSubtitle when OfferTitle contains promotional text.

**Related:** `.speckit/bugs/incomplete-data.md`

---

### 2. Enable Detailed Parsing by Default
**Status:** Partially Implemented  
**Effort:** Small (1 day)  
**Impact:** High

**Description:**
- Change CLI default to use `--parse-details` flag
- Extract full descriptions, photos, publication dates
- Add building type and coordinates to database

**Benefits:**
- Complete property information for analysis
- Photo dataset for AI training (renovation detection)
- Better filtering capabilities

**Code Changes:**
- `etl/collector_cian/cli.py:243` - change default value
- Test with sample payload to ensure performance is acceptable

---

### 3. Automated Daily Scraping
**Status:** Not Started  
**Effort:** Small (1 day)  
**Impact:** High

**Description:**
Set up systemd timer or cron job to run scraper daily at 3 AM.

**Implementation:**
```bash
# Create systemd service
sudo nano /etc/systemd/system/cian-scraper.service

[Unit]
Description=CIAN Real Estate Scraper
After=network.target postgresql.service

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/realestate
Environment="PATH=/home/ubuntu/realestate/venv/bin:/usr/bin"
ExecStart=/home/ubuntu/realestate/venv/bin/python -m etl.collector_cian.cli to-db --payload etl/collector_cian/payloads/cheap_first.yaml --pages 10 --parse-details

[Install]
WantedBy=multi-user.target

# Create timer
sudo nano /etc/systemd/system/cian-scraper.timer

[Unit]
Description=Run CIAN scraper daily at 3 AM

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

---

## Medium Priority

### 4. Price Drop Alerts
**Status:** Idea  
**Effort:** Medium (2-3 days)  
**Impact:** Medium

**Description:**
Implement email/Telegram notifications when:
- Price drops by >5% on tracked listings
- New listings appear below threshold (e.g., <10M RUB)
- Listings match saved search criteria

**Technical Approach:**
- SQL view to detect price changes
- Python script using Telegram Bot API
- Configurable alert rules in YAML

---

### 5. Metabase Analytics Dashboard
**Status:** Not Started  
**Effort:** Medium (2-3 days)  
**Impact:** Medium

**Features:**
- Price distribution by district
- Price per m² trends over time
- Inventory turnover (new vs. delisted)
- Cheapest listings table
- Average days on market

---

### 6. Multi-Region Support
**Status:** Idea  
**Effort:** Large (1-2 weeks)  
**Impact:** Medium

**Description:**
Extend parser to support regions beyond Moscow:
- Saint Petersburg (region=2)
- Kazan (region=4621)
- Configure via payload files

**Challenges:**
- Different proxy requirements per region
- Metro/district mapping varies by city
- Need separate databases or partitioning

---

## Low Priority (Future)

### 7. Machine Learning Price Prediction
**Status:** Research  
**Effort:** Large (3-4 weeks)  
**Impact:** Low (experimental)

**Description:**
Train ML model to predict:
- Fair market price based on features
- Probability of price drop in next 30 days
- Renovation quality from photos (using AI photo analyzer)

**Requirements:**
- Collect 6+ months of historical data
- Label dataset for renovation quality
- Research: XGBoost, LightGBM, or neural nets

---

### 8. API for External Access
**Status:** Idea  
**Effort:** Medium (3-5 days)  
**Impact:** Low

**Description:**
FastAPI endpoint for querying listings:
- GET /listings?min_price=X&max_price=Y&rooms=Z
- GET /listings/{id}/price-history
- Authentication via API keys

**Use Cases:**
- Mobile app integration
- Webhook notifications for external systems

---

### 9. Competitor Analysis (Avito, Yandex.Realty)
**Status:** Idea  
**Effort:** Large (per site)  
**Impact:** Low

**Description:**
Extend platform to scrape Avito and Yandex.Realty for price comparison.

**Challenges:**
- Different anti-bot strategies per site
- Schema mapping complexity
- Deduplication across platforms

---

### 10. Browser Extension for Manual Tracking
**Status:** Idea  
**Effort:** Medium (1-2 weeks)  
**Impact:** Low

**Description:**
Chrome/Firefox extension to:
- One-click add listing to tracking
- Show price history overlay on CIAN pages
- Highlight price drops in search results

---

## Completed

✅ **HTML Parser with Playwright** (2025-10-21)  
✅ **Smart Proxy Rotation** (2025-10-21)  
✅ **SCD Type 2 Price History** (2025-10-20)  
✅ **Photo URLs Collection** (2025-10-22)

---

**Last updated:** 2025-11-03
