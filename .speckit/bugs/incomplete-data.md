# Bug: Incomplete Data in Listings

**Status:** Open  
**Priority:** High  
**Created:** 2025-11-03  
**Assigned:** TBD

## Description

Many scraped listings have incomplete data, particularly:
- Missing `address` field (empty strings)
- Missing `rooms` count
- Missing `area_total`

## Impact

- Reduces data quality metrics (currently ~67% completeness for rooms)
- Makes filtering and analysis difficult
- Users cannot search by key criteria

## Root Cause Analysis

From HTML analysis (`logs/debug_cian_offer.html`):

1. **Address issue:** Parser extracts from `[data-name=GeoLabel]` but some listings don't have this element or it's nested differently

2. **Rooms/Area issue:** Parser looks for patterns like "2-комн. квартира, 60,66 м²" in `[data-mark=OfferTitle]` but:
   - Some titles have promotional text instead ("Рассрочка 0% до конца 27 года")
   - Actual property info is in `[data-mark=OfferSubtitle]` instead

## Evidence

```sql
-- Database query results
SELECT 
  COUNT(*) as total,
  COUNT(address) FILTER (WHERE address IS NOT NULL AND address != '') as has_address,
  COUNT(rooms) as has_rooms,
  COUNT(area_total) as has_area
FROM listings;

-- Results: 215 total, ~140 have rooms (~65%), many missing addresses
```

## Proposed Solution

### Short-term (Quick Fix)
1. Update `_parse_offers_from_html()` in `browser_fetcher.py`:
   - Check BOTH `OfferTitle` AND `OfferSubtitle` for property details
   - Prefer `OfferSubtitle` if it contains room/area patterns
   - Fallback to `OfferTitle` if subtitle is empty

2. Improve address extraction:
   - Try multiple selectors in order of preference
   - Validate extracted address (must contain district/metro)

### Long-term (Complete Fix)
1. Enable `--parse-details` by default to visit each listing page
2. Extract all fields from detail page (more reliable selectors)
3. Add data validation layer before DB insert

## Test Cases

```python
# Test cases to add in tests/test_parser.py

def test_parse_offer_with_promo_title():
    """Listing with promotional title should extract data from subtitle."""
    html = '''
    <div data-name="LinkArea">
        <span data-mark="OfferTitle">Рассрочка 0% до конца 27 года</span>
        <span data-mark="OfferSubtitle">2-комн. квартира, 60,66 м², 16/49 этаж</span>
    </div>
    '''
    offer = parse_offer_from_element(html)
    assert offer['rooms'] == 2
    assert offer['totalSquare'] == 60.66
    assert offer['floor'] == 16
    assert offer['floorsCount'] == 49

def test_parse_address_from_geo_labels():
    """Address should be extracted from GeoLabel elements."""
    # ... test implementation
```

## Related Issues

- [#TODO] Add data quality dashboard in Metabase
- [#TODO] Implement automated data completeness alerts

## References

- Code: `etl/collector_cian/browser_fetcher.py:167-278`
- Debug output: `logs/debug_cian_offer.html`
- Database schema: `db/schema.sql`
