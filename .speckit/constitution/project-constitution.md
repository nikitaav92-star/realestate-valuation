# Real Estate Parser - Project Constitution

## Project Mission
Build a robust, scalable real estate data collection platform for CIAN.ru that:
- Collects property listings with high completeness (>90% fields filled)
- Tracks price history using SCD Type 2 model
- Bypasses anti-bot protection using smart proxy rotation and behavior emulation
- Provides analytics-ready data for price analysis and market insights

## Core Principles

### 1. Code Quality
- All code must be type-hinted (Python 3.10+)
- Test coverage >80% for critical paths
- Follow PEP 8 style guide
- Use async/await for I/O operations where applicable

### 2. Anti-Bot Strategy
- Always use residential proxies (NodeMaven, BrightData)
- Implement exponential backoff on failures
- Rotate user agents and browser fingerprints
- Save and reuse browser cookies/storage
- HTML parsing as fallback when API is blocked

### 3. Data Integrity
- Validate all scraped data before DB insert
- Track data quality metrics (completeness %)
- Use PostgreSQL transactions for consistency
- Implement idempotent upsert logic

### 4. Performance
- Target: 20-30 seconds per page (28 listings)
- Use Playwright only when necessary (HTTP first)
- Cache proxy validation results (15 min TTL)
- Batch database operations

### 5. Observability
- Log all HTTP/browser requests with timing
- Track proxy success rates
- Monitor data completeness metrics
- Alert on parsing failures >10%

## Tech Stack

### Core
- Python 3.13
- PostgreSQL 14+ (with PostGIS)
- Playwright for browser automation
- httpx for HTTP requests

### Anti-Bot
- NodeMaven proxies (residential, RU)
- AntiCaptcha for CAPTCHA solving
- Playwright stealth plugins

### Orchestration
- Prefect for workflow scheduling
- systemd timers for cron jobs

### Analytics
- Metabase for dashboards
- SQL views for common queries

## Development Workflow

### Branch Strategy
- `master` - production-ready code
- `fix1` - current development branch
- Feature branches: `feature/description`
- Hotfixes: `hotfix/description`

### Commit Messages
```
<type>(<scope>): <description>

Types: feat, fix, perf, refactor, test, docs
Examples:
  feat(parser): add detailed photo extraction
  fix(antibot): handle proxy timeout correctly
  perf(db): optimize listing upsert query
```

### Testing
- Unit tests for parsers and mappers
- Integration tests for database operations
- End-to-end tests for full pipeline

## File Organization

```
realestate/
├── etl/
│   ├── collector_cian/     # CIAN-specific scraper
│   ├── antibot/            # Generic anti-bot toolkit
│   └── product_scraper/    # Mass product scraping
├── db/                     # Database schemas & migrations
├── tests/                  # Test suite
├── scripts/                # One-off debugging scripts
├── docs/                   # Documentation
└── .speckit/              # SpecKit specifications
    ├── constitution/       # This file
    ├── specifications/     # Feature specs
    ├── plans/             # Implementation plans
    ├── tasks/             # Task tracking
    ├── bugs/              # Bug reports
    └── ideas/             # Future ideas
```

## Production Deployment

### Production Principles
- All services must be containerized or systemd-managed
- Environment variables for all secrets
- Health checks for all services
- Automated backups for database
- HTTPS for all external access
- Monitoring and alerting in place

### Production Stack
- **Web:** FastAPI with Uvicorn (systemd service)
- **API:** FastAPI microservice (Docker container)
- **Database:** PostgreSQL 14+ (Docker container)
- **Reverse Proxy:** Nginx or Cloudflare Tunnel
- **Monitoring:** Health checks, logs, metrics
- **Backup:** Automated daily backups

### Deployment Documentation
- `PRODUCTION_REQUIREMENTS.md` - Complete deployment guide
- `PRODUCTION_QUICKSTART.md` - Quick start guide
- `TEST_REPORT.md` - System test results
- `.speckit/specifications/production-deployment.md` - Full specification

## Non-Goals

- Real-time scraping (batch processing is OK)
- 100% uptime (scheduled downtime for maintenance)
- Scraping non-CIAN sites (separate project)
- Public API (internal use only)

## Success Metrics

### Data Quality
- ✅ >90% listings have address, rooms, area, floor
- ✅ >95% listings have valid price
- ✅ <1% duplicate listings

### Performance
- ✅ 4 pages (112 listings) in <2 minutes
- ✅ Proxy success rate >90%
- ✅ Zero data loss on failures (retry logic)

### Reliability
- ✅ Daily scraping runs without manual intervention
- ✅ Auto-recovery from transient failures
- ✅ Alert notifications on critical errors

---

Last updated: 2025-11-03
