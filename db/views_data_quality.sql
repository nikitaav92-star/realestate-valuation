-- TASK-005: Data Quality Metrics View
-- Provides metrics for data completeness tracking

CREATE OR REPLACE VIEW data_quality_metrics AS
SELECT 
    COUNT(*) as total_listings,
    COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_rooms,
    COUNT(*) FILTER (WHERE area_total IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_area,
    COUNT(*) FILTER (WHERE address IS NOT NULL AND address != '') * 100.0 / NULLIF(COUNT(*), 0) as pct_has_address,
    COUNT(*) FILTER (WHERE floor IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_floor,
    COUNT(*) FILTER (WHERE lat IS NOT NULL AND lon IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_coordinates,
    -- Average completeness score (0-100)
    (
        CASE WHEN rooms IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN area_total IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN address IS NOT NULL AND address != '' THEN 1 ELSE 0 END +
        CASE WHEN floor IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN 1 ELSE 0 END
    ) * 20.0 as avg_completeness_score
FROM listings
WHERE is_active = TRUE;

-- View for recent listings quality (last 7 days)
CREATE OR REPLACE VIEW data_quality_metrics_recent AS
SELECT 
    COUNT(*) as total_listings,
    COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_rooms,
    COUNT(*) FILTER (WHERE area_total IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_area,
    COUNT(*) FILTER (WHERE address IS NOT NULL AND address != '') * 100.0 / NULLIF(COUNT(*), 0) as pct_has_address,
    COUNT(*) FILTER (WHERE floor IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_has_floor,
    AVG(
        (
            CASE WHEN rooms IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN area_total IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN address IS NOT NULL AND address != '' THEN 1 ELSE 0 END +
            CASE WHEN floor IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN 1 ELSE 0 END
        ) * 20.0
    ) as avg_completeness_score
FROM listings
WHERE is_active = TRUE 
  AND first_seen >= NOW() - INTERVAL '7 days';

-- View for apartment shares detection (BUG-001)
CREATE OR REPLACE VIEW apartment_shares_detected AS
SELECT 
    id,
    url,
    address,
    rooms,
    area_total,
    floor,
    price,
    first_seen
FROM listings l
JOIN listing_prices lp ON l.id = lp.id
WHERE l.is_active = TRUE
  AND l.area_total < 20
ORDER BY l.area_total ASC;

