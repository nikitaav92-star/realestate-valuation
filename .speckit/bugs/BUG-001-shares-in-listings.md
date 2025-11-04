# BUG-001: Apartment Shares in Listings

**Status:** 🔴 CONFIRMED  
**Priority:** HIGH  
**Severity:** Medium  
**Created:** 2025-11-04  
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

CIAN.ru API returns apartment shares even when filtering by `category: flatSale`. The payload `cheap_first.yaml` doesnt have minimum area filter.
