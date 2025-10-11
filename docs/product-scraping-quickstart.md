## Product Scraping System - Quick Start Guide

**Date:** 2025-10-11  
**Status:** ✅ MVP Ready (WS1-WS3 Completed)

---

### Overview

Mass product scraping system with queue-based orchestration, anti-bot resilience, and analytics-ready storage.

**Key Features:**
- ✅ Generic anti-bot toolkit (`etl/antibot/`)
- ✅ Postgres-backed task queue with advisory locks
- ✅ Worker CLI for parallel execution
- ✅ Product schema with price history tracking
- ✅ Circuit breakers, proxy rotation, fingerprint painting
- ✅ Captcha solving with telemetry

---

### Architecture

```
┌─────────────────┐
│  Task Queue     │  ← Postgres (product_tasks table)
│  (Postgres)     │
└────────┬────────┘
         │
         ├──────────────────┐
         │                  │
    ┌────▼─────┐      ┌────▼─────┐
    │ Worker 1 │      │ Worker 2 │
    └────┬─────┘      └────┬─────┘
         │                  │
    ┌────▼──────────────────▼────┐
    │   Anti-bot Helpers         │
    │  - Proxies                 │
    │  - Fingerprints            │
    │  - Captcha Solver          │
    │  - Circuit Breakers        │
    │  - Storage State Manager   │
    └────────────┬───────────────┘
                 │
            ┌────▼─────┐
            │ Fetchers │  ← Per-site implementations
            └────┬─────┘
                 │
          ┌──────▼──────┐
          │  Database   │  ← products, product_offers
          └─────────────┘
```

---

### Installation

#### 1. Database Setup

```bash
# Apply product schema
psql -h localhost -U realuser -d realdb -f db/schema_products.sql

# Verify tables created
psql -h localhost -U realuser -d realdb -c "\dt product*"
```

#### 2. Install Dependencies

```bash
# Activate venv
source .venv/bin/activate

# Install additional dependencies (if needed)
pip install click psycopg2-binary playwright
playwright install chromium
```

#### 3. Environment Variables

```bash
# Database connection
export DATABASE_URL="postgresql://realuser:strongpass@localhost:5432/realdb"

# Or use components
export PG_HOST=localhost
export PG_PORT=5432
export PG_USER=realuser
export PG_PASS=strongpass
export PG_DB=realdb

# Anti-bot configuration
export ANTICAPTCHA_KEY=your_key_here
export NODEMAVEN_PROXY_URL=http://username:password@gate.nodemaven.com:8080
```

---

### Usage

#### Enqueue Tasks

```bash
# Single task
python -m etl.product_scraper.cli enqueue \
    --source ozon \
    --url "https://www.ozon.ru/product/12345/" \
    --external-id "12345" \
    --priority 10

# Batch from file
echo "https://www.ozon.ru/product/12345/,12345" > products.txt
echo "https://www.ozon.ru/product/67890/,67890" >> products.txt

python -m etl.product_scraper.cli enqueue-batch \
    --source ozon \
    --input-file products.txt
```

#### Run Worker

```bash
# Start worker (currently requires fetcher implementation)
python -m etl.product_scraper.cli run \
    --source ozon \
    --batch-size 5 \
    --poll-interval 5.0

# Multiple workers in parallel
python -m etl.product_scraper.cli run --source ozon --worker-id worker-1 &
python -m etl.product_scraper.cli run --source ozon --worker-id worker-2 &
```

#### Monitor Queue

```bash
# Queue statistics
python -m etl.product_scraper.cli stats

# Output:
# 📊 Queue Statistics
# ========================================
# Total tasks: 150
#   pending      :     100
#   in_progress  :      10
#   completed    :      35
#   failed       :       5

# Purge old completed tasks
python -m etl.product_scraper.cli purge --days 7
```

---

### Implementing a Fetcher

Create per-site fetcher by subclassing `BaseFetcher`:

```python
# etl/product_scraper/fetchers/ozon.py
from ..fetcher import BaseFetcher, FetchResult
import httpx

class OzonFetcher(BaseFetcher):
    def _fetch_http(self, url, external_id, use_proxy=False):
        headers = {"User-Agent": self.user_agent_pool.get_random()}
        
        proxies = None
        if use_proxy and self.proxy_config:
            proxies = {"https": self.proxy_config.to_httpx_url()}
        
        resp = httpx.get(url, headers=headers, proxies=proxies, timeout=20)
        resp.raise_for_status()
        
        product_data = self._parse_response(resp.text, url)
        
        return FetchResult(
            success=True,
            product_data=product_data,
            escalation_level="http_with_proxy" if use_proxy else "http_direct",
            proxy_used=self.proxy_config.server if use_proxy else None,
        )
    
    def _parse_response(self, html, url):
        # Parse HTML with BeautifulSoup/lxml
        # Extract: name, price, availability, etc.
        return {
            "name": "Product Name",
            "price_minor": 12345,  # 123.45 RUB
            "in_stock": True,
        }
```

---

### Anti-bot Helpers

#### Captcha Solving

```python
from etl.antibot import CaptchaSolver

solver = CaptchaSolver()
token, telemetry = solver.solve(site_key="ABC123", page_url="https://example.com")

print(f"Solved in {telemetry.solve_time_sec:.2f}s")
print(f"Cost estimate: ${telemetry.cost_estimate_usd:.4f}")
```

#### Proxy Rotation

```python
from etl.antibot import ProxyConfig, ProxyRotator

proxies = [
    ProxyConfig.from_url("http://user:pass@proxy1.com:8080"),
    ProxyConfig.from_url("http://user:pass@proxy2.com:8080"),
]

rotator = ProxyRotator(proxies)
proxy = rotator.get_random()

print(f"Using proxy: {proxy.server}")
```

#### Fingerprint Painting

```python
from etl.antibot import create_stealth_context
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    
    # Create context with random fingerprint
    context = create_stealth_context(browser, prefer_mobile=False)
    
    page = context.new_page()
    page.goto("https://example.com")
```

#### Circuit Breaker

```python
from etl.antibot import CircuitBreaker

breaker = CircuitBreaker()

try:
    result = breaker.call(risky_function, arg1, arg2)
except RuntimeError as e:
    print(f"Circuit open: {e}")
```

---

### Database Queries

#### Latest Prices

```sql
SELECT * FROM v_products_latest_offers
WHERE source_id = 1
ORDER BY collected_at DESC
LIMIT 10;
```

#### Price Drops Today

```sql
SELECT 
    name,
    brand,
    prev_price_minor / 100.0 AS old_price,
    price_minor / 100.0 AS new_price,
    price_change_percent
FROM v_daily_price_drops
ORDER BY price_change_percent ASC;
```

#### Scraping Health

```sql
SELECT * FROM v_scraping_health
WHERE run_date >= CURRENT_DATE - INTERVAL '7 days';
```

---

### Next Steps

1. **Implement Site Fetchers:**
   - Create `etl/product_scraper/fetchers/ozon.py`
   - Create `etl/product_scraper/fetchers/wildberries.py`
   - Implement HTTP and Playwright fetch methods

2. **Persistence Layer:**
   - Add `persist_product()` function in worker
   - Use upsert pattern from `etl/upsert.py`

3. **Monitoring:**
   - Expose queue stats via API
   - Dashboard for captcha spend, success rates
   - Alerts on circuit breaker trips

4. **Automation:**
   - Cron jobs for periodic scraping
   - Prefect flows for orchestration

---

### Troubleshooting

**Worker shows "No fetcher configured":**
```bash
# Implement fetcher first, then update cli.py:
# fetchers[source] = OzonFetcher()
```

**Queue statistics show all "pending":**
```bash
# No workers running, start one:
python -m etl.product_scraper.cli run --source ozon
```

**High failure rate:**
```bash
# Check anti-bot config:
# - Proxies configured?
# - Captcha API key set?
# - Rate limits appropriate?
```

---

**Questions?** See `docs/antibot-audit.md` for anti-bot strategy details.

**Document owner:** Cursor AI  
**Last updated:** 2025-10-11

