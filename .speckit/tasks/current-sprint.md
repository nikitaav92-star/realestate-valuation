# Current Sprint Tasks

**Sprint:** November 2025 - Week 1  
**Focus:** Data Quality & Automation

## In Progress

### TASK-001: Fix OfferSubtitle Parsing
**Priority:** P0 (Critical)  
**Assignee:** AI Assistant  
**Status:** 🟡 In Progress  
**Effort:** 2 hours

**Objective:**
Update HTML parser to extract rooms/area from OfferSubtitle when OfferTitle has promotional text.

**Acceptance Criteria:**
- [ ] Parser checks both OfferTitle and OfferSubtitle
- [ ] Prefers OfferSubtitle if it contains property details (regex: `/\d+-комн|м²|этаж/`)
- [ ] Test coverage: 3 new test cases in `tests/test_mapper.py`
- [ ] Re-run parser on existing data, verify >90% completeness

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

**Description:**
Current address extraction misses some listings. Add fallback selectors and validation.

**Steps:**
- Try multiple selectors: `[data-name='GeoLabel']`, `[data-name='SpecialGeo']`
- Validate: address must contain "Москва" or metro station name
- Log warnings for missing addresses

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

**Description:**
Configure systemd timer to run scraper daily at 3 AM Moscow time.

**Steps:**
- Create systemd service file (see ideas/improvements-backlog.md)
- Create timer file
- Test manual trigger: `sudo systemctl start cian-scraper.service`
- Enable: `sudo systemctl enable cian-scraper.timer`
- Monitor logs: `journalctl -u cian-scraper.service -f`

---

### TASK-005: Add Data Quality Metrics
**Priority:** P2 (Medium)  
**Effort:** 3 hours

**Description:**
Create SQL view and logging for data completeness tracking.

**SQL View:**
```sql
CREATE OR REPLACE VIEW data_quality_metrics AS
SELECT 
  COUNT(*) as total_listings,
  COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / COUNT(*) as pct_has_rooms,
  COUNT(*) FILTER (WHERE area_total IS NOT NULL) * 100.0 / COUNT(*) as pct_has_area,
  COUNT(*) FILTER (WHERE address IS NOT NULL AND address != '') * 100.0 / COUNT(*) as pct_has_address,
  COUNT(*) FILTER (WHERE description IS NOT NULL) * 100.0 / COUNT(*) as pct_has_description
FROM listings;
```

**Logging:**
Add to `cli.py` after upsert: log data quality percentages.

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
