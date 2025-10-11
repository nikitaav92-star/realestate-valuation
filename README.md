# Real Estate Data Platform

Multi-source data collection platform for real estate and e-commerce with anti-bot resilience.

---

## Quick Start

### 1. CIAN Data Collection

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Setup database
docker-compose up -d
psql -h localhost -U realuser -d realdb -f db/schema.sql

# Run collection
python -m etl.collector_cian.cli pull --pages 1
```

**Features:**
- HTTP-first with automatic Playwright fallback
- Anti-captcha integration (Yandex SmartCaptcha)
- Residential proxy support (NodeMaven, BrightData)
- SCD Type 2 data model for price history

---

### 2. Mass Product Scraping (NEW! 🚀)

```bash
# Apply product schema
psql -h localhost -U realuser -d realdb -f db/schema_products.sql

# Enqueue tasks
python -m etl.product_scraper.cli enqueue \
    --source ozon \
    --url "https://www.ozon.ru/product/12345/" \
    --external-id "12345"

# Run worker
python -m etl.product_scraper.cli run --source ozon

# Monitor queue
python -m etl.product_scraper.cli stats
```

**Features (MVP Ready):**
- ✅ Queue-based orchestration (Postgres advisory locks)
- ✅ Worker CLI for parallel execution
- ✅ Generic anti-bot toolkit (`etl/antibot/`)
  - Circuit breakers & escalation matrix
  - Proxy rotation (BrightData, NodeMaven, SmartProxy)
  - Device fingerprint painting
  - Captcha solving with telemetry
  - Storage state rotation
- ✅ Analytics-ready schema (products, offers, price history)
- ✅ Monitoring views (price drops, scraping health)

**Documentation:**
- [`docs/product-scraping-quickstart.md`](docs/product-scraping-quickstart.md) - Quick start guide
- [`docs/product-scraping-roadmap.md`](docs/product-scraping-roadmap.md) - Full roadmap & requirements
- [`docs/antibot-audit.md`](docs/antibot-audit.md) - Anti-bot strategy details

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Data Sources                                               │
├─────────────────────────────────────────────────────────────┤
│  CIAN  │  Ozon  │  Wildberries  │  [Your Site]            │
└────┬────────┬─────────┬──────────────┬────────────────────┘
     │        │         │              │
     │        └─────────┴──────────────┘
     │                  │
     │            ┌─────▼──────┐
     │            │ Task Queue │  ← Postgres
     │            └─────┬──────┘
     │                  │
     │            ┌─────▼──────────────────┐
     │            │  Workers (parallel)    │
     │            └─────┬──────────────────┘
     │                  │
     └──────────────────┼───────────────────┐
                        │                   │
                   ┌────▼────────┐   ┌──────▼──────┐
                   │ Anti-bot    │   │  Fetchers   │
                   │ Helpers     │   │  (HTTP/PW)  │
                   └─────────────┘   └──────┬──────┘
                                            │
                                      ┌─────▼──────┐
                                      │ PostgreSQL │
                                      │ + PostGIS  │
                                      └────────────┘
```

---

## Project Structure

```
realestate/
├── db/
│   ├── schema.sql              # CIAN real estate schema
│   └── schema_products.sql     # Product scraping schema (NEW!)
├── etl/
│   ├── antibot/                # Generic anti-bot toolkit (NEW!)
│   │   ├── captcha.py          # Captcha solver with telemetry
│   │   ├── fingerprint.py      # Device fingerprint painter
│   │   ├── proxy.py            # Proxy rotation manager
│   │   ├── retry.py            # Circuit breaker & escalation
│   │   ├── storage.py          # Storage state manager
│   │   └── user_agent.py       # User-agent pool
│   ├── collector_cian/         # CIAN-specific collector
│   │   ├── cli.py              # CLI commands
│   │   ├── fetcher.py          # HTTP fetcher
│   │   ├── browser_fetcher.py  # Playwright fallback
│   │   └── mapper.py           # Data transformation
│   ├── product_scraper/        # Mass product scraping (NEW!)
│   │   ├── cli.py              # Worker CLI
│   │   ├── queue.py            # Task queue (Postgres)
│   │   ├── worker.py           # Worker implementation
│   │   ├── fetcher.py          # Base fetcher class
│   │   └── fetchers/           # Per-site implementations
│   ├── flows.py                # Prefect orchestration
│   ├── models.py               # Data models
│   └── upsert.py               # Database persistence
├── docs/
│   ├── product-scraping-roadmap.md      # Full roadmap (NEW!)
│   ├── product-scraping-quickstart.md   # Quick start (NEW!)
│   ├── antibot-audit.md                 # Anti-bot audit (NEW!)
│   └── blueprint.md                     # Original plan
└── web/                        # Web interface (experimental)
    ├── app.py                  # Flask app
    └── templates/              # UI templates
```

---

## Environment Variables

```bash
# Database
export DATABASE_URL="postgresql://realuser:strongpass@localhost:5432/realdb"

# Or use components
export PG_HOST=localhost
export PG_PORT=5432
export PG_USER=realuser
export PG_PASS=strongpass
export PG_DB=realdb

# Anti-bot
export ANTICAPTCHA_KEY=your_key_here
export NODEMAVEN_PROXY_URL=http://username:password@gate.nodemaven.com:8080
export BRIGHTDATA_PROXY_URL=http://username:password@brd.superproxy.io:33335
```

---

## Deployment

See `infra/README.md` for production setup.

**Live Instances:**
- Metabase: https://realestate.ourdocs.org/
- Prefect: https://realestate.ourdocs.org/prefect/

---

## Development Status

### ✅ Completed
- CIAN data collection pipeline
- Anti-bot toolkit (`etl/antibot/`)
- Product scraping MVP (queue, worker, schema)
- Documentation & quick start guides

### ⏳ In Progress
- Site-specific fetchers (Ozon, Wildberries)
- Persistence layer integration
- Monitoring dashboard

### 📋 Planned
- Prefect flows for product scraping
- API for queue management
- Price alert system

---

## Contributing

This project uses Cursor AI for development. See [`docs/product-scraping-roadmap.md`](docs/product-scraping-roadmap.md) for task breakdown.

**Branch:** `git-push-origin-master` (main development)

---

## License

Internal project. All rights reserved.
