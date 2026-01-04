# BUG-001: Apartment Shares in Listings

**Status:** ✅ FIXED  
**Priority:** HIGH  
**Severity:** Medium  
**Created:** 2025-11-04  
**Fixed:** 2025-11-19  
**Assigned:** Claude Agent

---

## Problem Description

Database contains 17 listings (1.1%) with area < 20m², which are apartment shares (доли), not full apartments. User expects only full apartments.

### Examples:
- ID 320471057: 4.5m², 2.5M ₽ - явно доля
- ID 322414832: 10.3m², 3.9M ₽ - доля
- ID 319592012: 12.1m², 7.1M ₽ - доля в центре

---

## Root Cause

CIAN.ru API returns apartment shares even when filtering by `category: flatSale`. The payload `cheap_first.yaml` didnt have minimum area filter.

## Solution

✅ **Fixed:** 2025-11-19
- Updated payload `cheap_first.yaml`: `minArea: 20` (was 18)
- Added validation in `mapper.py`: filter out area < 20
- Created SQL view `apartment_shares_detected` for monitoring

**Files Changed:**
- `etl/collector_cian/payloads/cheap_first.yaml` - minArea updated to 20
- `etl/collector_cian/mapper.py` - validation added
- `db/views_data_quality.sql` - view for shares detection

**Action Required:**
Deactivate existing shares:
```sql
UPDATE listings SET is_active = FALSE WHERE area_total < 20;
```
