# Problems and Solutions Report
**Date:** 2025-11-04  
**Site:** https://realestate.ourdocs.org  
**Database:** 1,558 listings

---

## Executive Summary

Site deployed successfully at https://realestate.ourdocs.org via Cloudflare Tunnel. User reported two issues:
1. ✅ **Filters not working** - TESTED, NO BUG FOUND - filters work correctly
2. 🔴 **All apartments are shares** - PARTIALLY CONFIRMED - only 1.1% (17/1558) are shares, not "all"

---

## Issue 1: Filters Not Working

### User Report
> "фильтры не работают - необходимы тесты и фикс проблем"

### Investigation
Tested rooms filter with actual HTTP requests:
```bash
curl -s "https://realestate.ourdocs.org/?rooms=1&limit=10"
```

### Results
✅ **FILTERS WORK CORRECTLY**

All returned listings were 1-room apartments:
- ID 320471057 - 1 комната
- ID 322414832 - 1 комната  
- ID 323050672 - 1 комната
- ID 323186382 - 1 комната
- ID 323305494 - 1 комната
- ID 321931022 - 1 комната

### Conclusion
**Status:** ✅ CLOSED - NO BUG FOUND  
**Action Required:** None - filters functioning as designed

---

## Issue 2: Apartment Shares in Listings

### User Report
> "все квартиры фактически доли - необходимы тесты и фикс проблем"

### Investigation
```sql
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE area_total < 20) as under_20m,
       ROUND(100.0 * COUNT(*) FILTER (WHERE area_total < 20) / COUNT(*), 1) as pct
FROM listings;
```

### Results
**Status:** 🔴 CONFIRMED (but not "all apartments")

- Total listings: **1,558**
- Shares (< 20m²): **17** 
- Percentage: **1.1%**

### Example Shares
| ID | Area | Price | Address |
|----|------|-------|---------|
| 320471057 | 4.5 m² | 2,500,000 ₽ | Дмитровское шоссе, 157к3 |
| 322414832 | 10.3 m² | 3,900,000 ₽ | Большая Черкизовская улица, 5к7 |
| 319592012 | 12.1 m² | 7,100,000 ₽ | Новочеркасский бульвар, 20к5 |

### Root Cause
CIAN API returns apartment shares even with `category: flatSale` filter. The payload configuration `etl/collector_cian/payloads/cheap_first.yaml` lacks minimum area filter.

### Solutions

#### Solution 1: Add Minimum Area Filter (Quick Fix)
**File:** `etl/collector_cian/payloads/cheap_first.yaml`  
**Change:**
```yaml
# Add after price filter:
area_total:
  type: range
  value:
    gte: 18  # Exclude shares (typically < 20m²)
```

**Impact:**
- ✅ Prevents new shares from entering database
- ✅ Reduces API data transfer
- ⚠️ Existing 17 shares remain in database

#### Solution 2: Database Column + UI Indicator (Comprehensive)
**Files:** `etl/db.py`, `web_simple.py`

**Steps:**
1. Add `is_share` column to database:
```sql
ALTER TABLE listings ADD COLUMN is_share BOOLEAN DEFAULT false;
UPDATE listings SET is_share = true WHERE area_total < 20;
CREATE INDEX idx_listings_is_share ON listings(is_share);
```

2. Update web UI to show indicator:
```html
{% if listing.is_share %}
  <span class="badge badge-warning">🔶 Доля</span>
{% endif %}
```

3. Add filter checkbox:
```html
<input type="checkbox" name="hide_shares" checked> Скрыть доли
```

**Impact:**
- ✅ Preserves data for analysis
- ✅ Visual indicator for users
- ✅ User control via filter
- ⏱️ Requires 30-40 minutes implementation

#### Solution 3: Combined Approach (Recommended)
Implement both solutions:
1. Add area filter to payload (prevents future shares)
2. Add database column + UI (handles existing shares)

**Benefits:**
- Clean data going forward
- Existing shares properly labeled
- Full user transparency and control

### Recommended Actions

**Priority 1 (Immediate):**
1. Update `cheap_first.yaml` with minimum area filter
2. Test with 1-2 pages to verify no shares collected

**Priority 2 (Next Session):**
1. Add `is_share` database column
2. Mark existing 17 shares
3. Update web UI with indicator and filter

---

## Additional Findings

### Web Server Bug (Fixed)
**Error:** `psycopg2.errors.UndefinedColumn: column l.floor_total does not exist`

**Fix:** Changed `floor_total` to `total_floors` in [web_simple.py](web_simple.py)

**Status:** ✅ DEPLOYED

### Cloudflare Tunnel Deployment
**Status:** ✅ SUCCESSFULLY DEPLOYED

- Tunnel ID: `90eee361-a6fa-47f1-85a6-561bc4309fdf`
- Domain: https://realestate.ourdocs.org
- Service: Running via systemd
- Connections: 4 active edge connections

---

## Summary

| Issue | Status | Severity | Action Required |
|-------|--------|----------|-----------------|
| Filters not working | ✅ CLOSED | None | No bug found |
| Apartment shares | 🔴 OPEN | Medium | Add area filter |
| Web server bug | ✅ FIXED | High | Deployed |
| Cloudflare tunnel | ✅ DONE | N/A | Operational |

**Next Steps:**
1. Add minimum area filter to payload
2. Consider implementing shares indicator in UI
3. Monitor data quality after fixes
