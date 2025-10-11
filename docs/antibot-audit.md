## Anti-bot Audit & Reusable Components (WS1)

**Date:** 2025-10-11  
**Status:** ✅ Completed

### Executive Summary

This document catalogs reusable anti-bot components extracted from `etl/collector_cian/*` and identifies patterns applicable to mass product scraping.

---

### Audit Findings

#### Current CIAN Anti-bot Stack

| Component | Location | Purpose | Reusability |
|-----------|----------|---------|-------------|
| **HTTP Fetcher** | `fetcher.py` | Fast async HTTP client with tenacity retry | ✅ High - Generic HTTP logic |
| **Browser Fetcher** | `browser_fetcher.py` | Playwright fallback with stealth flags | ✅ High - Reusable for any site |
| **Captcha Solver** | `captcha_solver.py` | AntiCaptcha API integration | ✅ High - Generic captcha solving |
| **Storage State** | `browser_fetcher.py:_storage_state_path()` | Cookie/localStorage management | ⚠️ Medium - Needs rotation logic |
| **Proxy Support** | `browser_fetcher.py` (commented) | Basic proxy config | ⚠️ Medium - Needs rotation |
| **User-Agent** | Hardcoded in fetchers | Static UA strings | ❌ Low - Needs pooling |
| **Rate Limiting** | `asyncio.sleep(0.6)` | Fixed delay between requests | ⚠️ Medium - Needs per-site config |

#### Extracted Components (Now in `etl/antibot/`)

1. **`captcha.py`** - Enhanced captcha solver with telemetry
   - Tracks solve time, cost, success rate
   - Supports multiple captcha types (Yandex, reCAPTCHA)
   - Monitoring-ready metrics

2. **`fingerprint.py`** - Device fingerprint painter
   - Pool of realistic desktop/mobile configs
   - Playwright context overrides (UA, viewport, WebGL, navigator)
   - Random rotation for each session

3. **`proxy.py`** - Proxy rotation manager
   - Support for BrightData, NodeMaven, SmartProxy
   - Round-robin and weighted-random rotation
   - Failure tracking and circuit breaking

4. **`retry.py`** - Circuit breaker & escalation matrix
   - Protects against cascading failures
   - Automatic escalation: HTTP → Proxy → Playwright
   - Configurable retry budgets

5. **`storage.py`** - Storage state manager
   - Multi-file rotation with freshness tracking
   - Automatic cleanup of old states
   - Verification and invalidation logic

6. **`user_agent.py`** - User-agent pool
   - Desktop and mobile UA strings
   - Random selection with browser-specific filtering

---

### Product Domain Differences

#### E-commerce vs Real Estate

| Aspect | Real Estate (CIAN) | E-commerce (General) |
|--------|-------------------|----------------------|
| **Request Pattern** | Search queries → paginated results | Category browse + product detail pages |
| **Auth Requirements** | Optional (prices visible without login) | Often required for pricing/availability |
| **Captcha Frequency** | Medium (on search abuse) | High (on bots, scrapers) |
| **Rate Limits** | ~2 RPS per session | Varies (0.5-5 RPS typical) |
| **JS Rendering** | Minimal (API-first) | Heavy (SPAs, dynamic pricing) |
| **Proxy Necessity** | High (datacenter IPs blocked) | Very High (aggressive bot detection) |
| **Cookie Complexity** | Low (session tracking) | High (cart, personalization) |

#### Key Insights for Product Scraping

1. **Higher JS Dependency** → Must use Playwright more frequently
2. **Stricter Bot Detection** → Need better fingerprinting & proxies
3. **Session Management** → Storage state rotation critical
4. **Per-Site Tuning** → Each site needs custom strategy card

---

### Per-Site Strategy Cards

#### Template Structure

```yaml
site: example.com
strategy:
  primary_method: http  # http | smart_proxy | playwright
  fallback_chain: [smart_proxy, playwright_headless, playwright_headed]
  rate_limit_rps: 1.5
  requires_auth: true
  auth_method: manual  # manual | auto | oauth
  
anti_bot:
  captcha_type: recaptcha_v2  # none | recaptcha_v2 | recaptcha_v3 | hcaptcha | yandex
  fingerprint_level: high  # low | medium | high
  proxy_requirement: residential  # none | datacenter | residential
  user_agent_rotation: true
  
storage:
  cookies_required: [session_id, csrf_token]
  max_age_hours: 24
  verification_interval_hours: 6
  
monitoring:
  success_threshold: 0.95
  alert_on_captcha_rate: 0.3
  circuit_breaker_enabled: true
```

#### Example: CIAN

```yaml
site: cian.ru
strategy:
  primary_method: http
  fallback_chain: [smart_proxy, playwright_headless]
  rate_limit_rps: 1.6
  requires_auth: false
  auth_method: none
  
anti_bot:
  captcha_type: yandex
  fingerprint_level: medium
  proxy_requirement: residential
  user_agent_rotation: true
  
storage:
  cookies_required: []
  max_age_hours: 168  # 7 days
  verification_interval_hours: 24
  
monitoring:
  success_threshold: 0.95
  alert_on_captcha_rate: 0.2
  circuit_breaker_enabled: true
```

---

### Integration Plan

#### Phase 1: Retrofit CIAN Collector (✅ In Progress)

1. Update `browser_fetcher.py` to use `etl.antibot.fingerprint.create_stealth_context()`
2. Replace hardcoded captcha logic with `etl.antibot.captcha.CaptchaSolver`
3. Add `etl.antibot.storage.StorageStateManager` for multi-state rotation
4. Instrument with `etl.antibot.retry.CircuitBreaker`

#### Phase 2: Product Scraper Foundation (WS3)

1. Create `etl/product_scraper/` package
2. Implement per-site fetchers inheriting from base class
3. Load strategy cards from `etl/product_scraper/strategies/*.yaml`
4. CLI for worker execution with antibot helpers

#### Phase 3: Monitoring & Ops (WS5)

1. Expose captcha telemetry via API
2. Dashboard for proxy health, storage state freshness
3. Alerts for circuit breaker trips, high captcha rates

---

### Recommendations

1. **Proxy Strategy:** Use residential proxies (NodeMaven/BrightData) as default for product sites
2. **Fingerprinting:** Apply fingerprint painting to all Playwright contexts
3. **Storage Rotation:** Maintain 3-5 fresh storage states per site, verify every 6 hours
4. **Circuit Breakers:** Enable for all HTTP collectors with 5-failure threshold
5. **Rate Limiting:** Per-site tuning via strategy cards (0.5-2 RPS typical)
6. **Captcha Budget:** Monitor spend, alert if >$5/day per site

---

### Next Steps

- [ ] Update CIAN collector to use antibot helpers (WS2 continuation)
- [ ] Create product scraper base classes (WS3)
- [ ] Define 3-5 initial product site strategy cards (WS3)
- [ ] Implement monitoring dashboard (WS5)

**Document owner:** Cursor AI  
**Last updated:** 2025-10-11

