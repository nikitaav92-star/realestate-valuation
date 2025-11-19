# Current Sprint Tasks

**Sprint:** November 2025 - Week 1  
**Focus:** Data Quality & Automation

## In Progress

### TASK-001: Fix OfferSubtitle Parsing
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** ✅ Complete  
**Effort:** 2 hours  
**Completed:** 2025-11-19

**Objective:**
Update HTML parser to extract rooms/area from OfferSubtitle when OfferTitle has promotional text.

**Acceptance Criteria:**
- [x] Parser checks both OfferTitle and OfferSubtitle
- [x] Prefers OfferSubtitle if it contains property details (regex: `/\d+-комн|м²|этаж/`)
- [x] Implementation complete in `browser_fetcher.py`
- [x] Logic verified and working

**Implementation Steps:**
1. Read current `browser_fetcher.py:224-254`
2. Refactor to check subtitle first, fallback to title
3. Add regex-based heuristic to detect promotional vs. property text
4. Write unit tests with real HTML samples
5. Run integration test: `python -m etl.collector_cian.cli to-db --pages 1`
6. Verify in DB: `SELECT COUNT(*) FROM listings WHERE rooms IS NOT NULL`

**Files to Modify:**
- `etl/collector_cian/browser_fetcher.py` (line 224-254)
- `tests/test_mapper.py` (new tests)

**Related:**
- Bug: `.speckit/bugs/incomplete-data.md`
- Constitution: Data Integrity principle

---

## Backlog (Prioritized)

### TASK-002: Improve Address Extraction
**Priority:** P1 (High)  
**Effort:** 1 hour  
**Status:** ✅ Complete  
**Completed:** 2025-11-19

**Description:**
Current address extraction misses some listings. Add fallback selectors and validation.

**Steps:**
- [x] Try multiple selectors: `[data-name='GeoLabel']`, `[data-name='SpecialGeo']`
- [x] Validate: address must contain "Москва" or metro station name
- [x] Log warnings for missing addresses
- [x] Fallback to geo-related CSS classes

---

### TASK-003: Enable --parse-details by Default
**Priority:** P1 (High)  
**Effort:** 4 hours

**Description:**
Make detailed parsing (photos, descriptions, dates) the default behavior.

**Steps:**
- Update CLI arg parser default value
- Test performance impact (should be <5 min for 4 pages)
- Update README with new behavior
- Add monitoring for detail parsing failures

---

### TASK-004: Setup Automated Daily Scraping
**Priority:** P2 (Medium)  
**Effort:** 2 hours  
**Status:** ✅ Complete  
**Completed:** 2025-11-19

**Description:**
Configure systemd timer to run scraper daily at 3 AM Moscow time.

**Steps:**
- [x] Create systemd service file
- [x] Create timer file
- [x] Create setup script
- [x] Ready for installation

**Files:**
- `infra/systemd/cian-scraper.service` - systemd service
- `infra/systemd/cian-scraper.timer` - systemd timer
- `scripts/setup_daily_scraper.sh` - installation script

**Usage:**
```bash
sudo ./scripts/setup_daily_scraper.sh
```

---

### TASK-005: Add Data Quality Metrics
**Priority:** P2 (Medium)  
**Effort:** 3 hours  
**Status:** ✅ Complete  
**Completed:** 2025-11-19

**Description:**
Create SQL view and logging for data completeness tracking.

**SQL View:**
- [x] Created `data_quality_metrics` view
- [x] Created `data_quality_metrics_recent` view (last 7 days)
- [x] Created `apartment_shares_detected` view
- [x] Added logging to `cli.py` after upsert
- [x] Created script `apply_data_quality_views.sh`

**Files:**
- `db/views_data_quality.sql` - SQL views
- `etl/collector_cian/cli.py` - logging added
- `scripts/apply_data_quality_views.sh` - setup script

---

### TASK-006: Write Integration Tests
**Priority:** P2 (Medium)  
**Effort:** 4 hours

**Test Cases:**
- End-to-end: Scrape 1 page → Verify DB insert
- Proxy failure → Retry with different proxy
- CAPTCHA encountered → Solve and continue
- Duplicate listing → Update price, don't create new row

---

## Completed ✅

- ✅ TASK-000: Setup SpecKit structure (2025-11-03)

---

**Notes:**
- Use `/speckit.implement TASK-XXX` to auto-implement tasks
- Update status as work progresses
- Link commits to task IDs in commit messages
