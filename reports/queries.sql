-- Median price per square meter by region / rooms / deal type
SELECT
    l.region,
    l.rooms,
    l.deal_type,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.price / NULLIF(l.area_total, 0)) AS median_price_per_sqm
FROM listings AS l
JOIN listing_prices AS p ON p.id = l.id
GROUP BY l.region, l.rooms, l.deal_type;

-- Days on market (DOM) for inactive listings
SELECT
    id,
    DATE_TRUNC('day', last_seen) - DATE_TRUNC('day', first_seen) AS dom_days
FROM listings
WHERE is_active = FALSE;

-- Price drops >= 5%
WITH history AS (
    SELECT
        id,
        seen_at,
        price,
        LAG(price) OVER (PARTITION BY id ORDER BY seen_at) AS prev_price
    FROM listing_prices
)
SELECT id, seen_at, price
FROM history
WHERE prev_price IS NOT NULL AND price <= 0.95 * prev_price;
