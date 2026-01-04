## Mass Product Scraping System — Requirements & Cursor Backlog

### 1. Context
- **Repository:** `realestate` (`https://github.com/nikitaav92-star/realestate.git`)
- **Current scope:** Real-estate (CIAN) collector with multi-stage anti-bot bypass (HTTP → smart proxy → Playwright + AntiCaptcha).
- **New goal:** Extend anti-bot toolkit and data platform to support **mass scraping of e-commerce products** (multiple sources, large SKU volumes).
- **Branch:** `fix1` (all changes for this initiative live here until review/merge).

### 2. Objectives
1. **Anti-bot resilience:** Generalise existing fallback pipeline to handle product sites (rotating proxies, device fingerprints, storage-state rotation, captcha solving, request pacing).
2. **Scalable ingestion:** Design ingestion orchestration that can enqueue product URLs / queries, execute parallel workers with backpressure, and persist results safely.
3. **Analytics-ready schema:** Define relational model for product snapshots (pricing, availability, attributes) with historisation for price/stock changes.
4. **Operational tooling:** Provide diagnostics, manual overrides, and documentation so operators can monitor anti-bot health and refresh credentials quickly.

### 3. Success Criteria
- Playbook for bypass strategies (smart proxy, cookies, captcha solver) works for product domains.
- Queue-based ingestion handles batches ≥ 10k product pages / day with configurable concurrency.
- Data stored in PostgreSQL with temporal tables enabling price history & availability analytics.
- Monitoring hooks (logs, counters) expose anti-bot failures, captcha spend, proxy errors.
- Documentation & scripts allow Cursor operators to reproduce setup end-to-end.

### 4. Constraints & Assumptions
- Prefer Python 3.11+ (consistent with existing venv). Keep Playwright for headless flows.
- AntiCaptcha API key already provisioned; SMART/NodeMaven/BrightData proxies available.
- Network limits: follow existing 1.5–2 RPS per session; design throttling to be site-specific.
- Database: Postgres (existing `realdb`). Storage should reuse current infrastructure (Docker compose).
- Authentication artifacts (cookies/state) remain outside git; scripts must respect `.gitignore`.

### 5. Workstream Breakdown (Cursor-ready prompts)

#### WS1 — Discovery & Planning
1. Audit current anti-bot modules (`etl/collector_cian/*`) and identify reusable components.
2. Document product-domain differences: request patterns, page structure, anti-bot signals.
3. Produce **per-site strategy cards** outlining required cookies, headers, captcha types.

#### WS2 — Anti-bot Platform Upgrade
4. Extract generic anti-bot helpers (proxy rotation, user-agent/device pool, retry budget) into `etl/antibot/`.
5. Implement storage-state manager: rotate multiple auth files, verify freshness, auto-download from S3.
6. Add fingerprint painter (Playwright context overrides: UA, viewport, locale, navigator flags).
7. Plug AntiCaptcha solver into Playwright flows with telemetry (solve time, cost estimate).
8. Instrument HTTP collector with circuit breaker + automatic fallback escalation matrix.

#### WS3 — Mass Product Collector Core
9. Define queue interface (e.g., Redis, Postgres advisory locks) to hold product tasks.
10. Implement worker CLI `python -m etl.product_sourcing.cli run --site X`.
11. Build fetchers per site using shared anti-bot helpers (HTTP-first, Playwright fallback).
12. Normalise responses into unified product schema (catalog, offers, price history, stock).

#### WS4 — Persistence & Analytics
13. Extend DB schema (see Section 6) & generate migrations.
14. Implement upsert layer for products (handle new SKUs, update attributes, append price history).
15. Add reporting views (daily price delta, stock-out events, competitor price comparisons).

#### WS5 — Operations & Monitoring
16. CLI / web UI panels for queue depth, success rate, captcha consumption.
17. Logging & alerting hooks (structured logs, optional Prometheus metrics).
18. Runbooks for refreshing cookies, rotating proxies, handling bans.

### 6. Proposed Database Schema (initial draft)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `product_sources` | Master data for target sites | `id`, `slug`, `name`, `base_url`, `timezone`, `default_currency` |
| `products` | Canonical SKU info (per site or normalised) | `id`, `source_id`, `external_id`, `name`, `brand`, `category_path`, `url`, `image_url`, `metadata JSONB`, `first_seen`, `last_seen`, `is_active` |
| `product_offers` | Stock & price snapshot per scrape run | `id`, `product_id`, `collected_at`, `price_minor`, `currency`, `in_stock`, `stock_level`, `delivery_text`, `seller`, `raw_payload JSONB` |
| `product_price_history` | Denormalised price timeline (optional view) | `product_id`, `collected_at`, `price_minor` |
| `scrape_runs` | Execution metadata for workers | `id`, `source_id`, `started_at`, `finished_at`, `status`, `success_count`, `fail_count`, `captcha_solved`, `proxy_provider`, `notes` |
| `scrape_failures` | Error diagnostics | `run_id`, `product_id`, `error_type`, `http_status`, `message`, `resolved_at` |

> See `db/schema_products.sql` for the executable DDL matching this proposal (indexes + FK policy).

**Integration approach**
- Upsert layer mirrors the existing `etl/upsert.py` pattern: open a single transaction per batch, `INSERT ... ON CONFLICT` on `(source_id, external_id)` for `products`, append immutable rows to `product_offers`.
- Views or materialised views can expose `product_price_history` and latest offer snapshot without duplicating data.
- `scrape_runs` acts as parent entity for observability; workers log metrics there and attach detailed rows into `scrape_failures` on retries/exhaustion.

> All monetary values stored as integer (minor units). Use timezone-aware timestamps. Index heavily on `(source_id, external_id)` and `(product_id, collected_at DESC)`.

### 7. Implementation Progress ✅

**Completed (2025-10-11):**

#### WS1 - Discovery & Planning ✅
1. ✅ Audited `etl/collector_cian/*` modules
2. ✅ Documented product-domain differences
3. ✅ Created per-site strategy card template
4. 📄 See `docs/antibot-audit.md`

#### WS2 - Anti-bot Platform Upgrade ✅
4. ✅ Extracted helpers to `etl/antibot/`:
   - `captcha.py` - Solver with telemetry
   - `fingerprint.py` - Device fingerprint painter
   - `proxy.py` - Proxy rotation manager
   - `retry.py` - Circuit breaker & escalation
   - `storage.py` - Storage state manager
   - `user_agent.py` - UA pool
5. ✅ Storage state manager with rotation
6. ✅ Fingerprint painter for Playwright
7. ✅ AntiCaptcha solver with telemetry
8. ✅ Circuit breaker & escalation matrix

#### WS3 - Mass Product Collector Core ✅
9. ✅ Queue interface (`etl/product_scraper/queue.py`)
   - Postgres advisory locks
   - Task enqueue/dequeue
   - Retry logic
10. ✅ Worker CLI (`etl/product_scraper/cli.py`)
    - enqueue / enqueue-batch
    - run / stats / purge
11. ✅ Base fetcher with anti-bot helpers
12. ✅ Product schema ready for persistence

#### WS4 - Persistence & Analytics ✅
13. ✅ DB schema (`db/schema_products.sql`)
    - Tables: products, product_offers, scrape_runs
    - Views: latest offers, price history, health
    - Indexes & FK constraints
14. ⏳ Upsert layer (pending fetcher implementation)
15. ✅ Reporting views (price drops, health dashboard)

#### WS5 - Operations & Monitoring ⏳
16. ⏳ CLI panels (stats implemented, web UI pending)
17. ✅ Structured logging
18. 📝 Runbooks (see quickstart guide)

### 7. Immediate Next Steps (for branch `fix1`)
1. ✅ ~~Finalise schema DDL~~ → DONE
2. ✅ ~~Create anti-bot helper module~~ → DONE
3. ✅ ~~Scaffold product collector package~~ → DONE
4. ⏳ Implement site-specific fetchers (Ozon, Wildberries)
5. ⏳ Add persistence layer to worker
6. ⏳ Update documentation (`README.md`, `docs/blueprint.md`) to reference new initiative.

### 8. Open Questions
- Which e-commerce domains are in scope initially? (Need domain list to tailor anti-bot tactics.)
- Do we need distributed queue (Redis) or will Postgres suffice for MVP?
- SLA for data freshness (hourly vs daily) informs concurrency & scheduling strategy.
- Budget for captcha/proxy usage — define alert thresholds.

### 9. Review & Acceptance
- Share this roadmap with stakeholders for approval.
- Iterate backlog items into Cursor prompts/tasks (keep ≤15 min chunks).
- Once approved, proceed with WS2/WS3 implementation on branch `fix1`.

---

**Document owner:** Codex (Cursor automation)  
**Last updated:** 2025-10-11
