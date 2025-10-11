-- CIAN Schema V2 - All fields required (NOT NULL)
-- Updated: 2025-10-11
-- Purpose: Ensure data quality by requiring all 15 fields

-- Drop existing tables if upgrading
-- DROP TABLE IF EXISTS listing_prices CASCADE;
-- DROP TABLE IF EXISTS listings CASCADE;

-- Main listings table with strict validation
CREATE TABLE IF NOT EXISTS listings (
    -- Core identification
    id BIGINT PRIMARY KEY,                          -- CIAN offer ID (REQUIRED)
    url TEXT NOT NULL,                              -- Full CIAN URL (REQUIRED)
    
    -- Location
    region INT NOT NULL,                            -- Region ID (1=Moscow) (REQUIRED)
    address TEXT NOT NULL,                          -- Full address (REQUIRED)
    lat DOUBLE PRECISION NOT NULL,                  -- Latitude (REQUIRED)
    lon DOUBLE PRECISION NOT NULL,                  -- Longitude (REQUIRED)
    
    -- Property details
    deal_type TEXT NOT NULL,                        -- sale/rent (REQUIRED)
    rooms INT NOT NULL,                             -- Number of rooms (REQUIRED)
    area_total NUMERIC NOT NULL CHECK (area_total > 0),  -- Total area m² (REQUIRED)
    floor INT NOT NULL CHECK (floor >= 1),          -- Floor number (REQUIRED)
    
    -- Seller info
    seller_type TEXT NOT NULL,                      -- owner/agent/developer (REQUIRED)
    
    -- Temporal tracking
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- First appearance (REQUIRED)
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- Last update (REQUIRED)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,        -- Active status (REQUIRED)
    
    -- Constraints
    CONSTRAINT chk_url_format CHECK (url LIKE 'https://www.cian.ru/%'),
    CONSTRAINT chk_region_valid CHECK (region > 0),
    CONSTRAINT chk_rooms_valid CHECK (rooms >= 0 AND rooms <= 10),
    CONSTRAINT chk_deal_type_valid CHECK (deal_type IN ('sale', 'rent'))
);

-- Price history table
CREATE TABLE IF NOT EXISTS listing_prices (
    id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price NUMERIC NOT NULL CHECK (price > 0),       -- Price in rubles (REQUIRED)
    
    PRIMARY KEY (id, seen_at)
);

-- Comments
COMMENT ON TABLE listings IS 'CIAN listings with strict validation - all fields required';
COMMENT ON COLUMN listings.url IS 'Full CIAN URL: https://www.cian.ru/sale/flat/{id}/';
COMMENT ON COLUMN listings.rooms IS '0=studio, 1-3=rooms, 4+=large';
COMMENT ON COLUMN listings.area_total IS 'Total area in square meters';
COMMENT ON COLUMN listings.lat IS 'Latitude for map display';
COMMENT ON COLUMN listings.lon IS 'Longitude for map display';

COMMENT ON TABLE listing_prices IS 'Price history - new record only on price change';
COMMENT ON COLUMN listing_prices.price IS 'Price in rubles (not minor units)';

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_listings_region_deal_rooms
    ON listings (region, deal_type, rooms);

CREATE INDEX IF NOT EXISTS idx_listings_is_active
    ON listings (is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_listings_last_seen
    ON listings (last_seen DESC)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_listings_price_range
    ON listings (id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_listing_prices_latest
    ON listing_prices (id, seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_listings_location
    ON listings USING GIST (ll_to_earth(lat, lon))
    WHERE is_active = TRUE;

-- View: Latest prices with all details
CREATE OR REPLACE VIEW v_listings_with_latest_price AS
SELECT 
    l.id,
    l.url,
    l.region,
    l.address,
    l.lat,
    l.lon,
    l.deal_type,
    l.rooms,
    l.area_total,
    l.floor,
    l.seller_type,
    l.first_seen,
    l.last_seen,
    l.is_active,
    lp.price AS current_price,
    lp.seen_at AS price_updated_at,
    ROUND(lp.price / l.area_total, 0) AS price_per_sqm
FROM listings l
JOIN LATERAL (
    SELECT price, seen_at
    FROM listing_prices
    WHERE id = l.id
    ORDER BY seen_at DESC
    LIMIT 1
) lp ON true
WHERE l.is_active = TRUE;

COMMENT ON VIEW v_listings_with_latest_price IS 'Active listings with latest price and calculated price per sqm';

-- View: Price drops (≥5%)
CREATE OR REPLACE VIEW v_price_drops AS
WITH price_changes AS (
    SELECT 
        id,
        price,
        seen_at,
        LAG(price) OVER (PARTITION BY id ORDER BY seen_at) AS prev_price
    FROM listing_prices
)
SELECT 
    l.id,
    l.url,
    l.address,
    l.rooms,
    l.area_total,
    pc.prev_price,
    pc.price AS current_price,
    ROUND(((pc.price - pc.prev_price) / pc.prev_price * 100), 2) AS change_percent,
    pc.seen_at
FROM price_changes pc
JOIN listings l ON pc.id = l.id
WHERE pc.prev_price IS NOT NULL
    AND ((pc.price - pc.prev_price) / pc.prev_price) <= -0.05
    AND l.is_active = TRUE
ORDER BY change_percent ASC;

COMMENT ON VIEW v_price_drops IS 'Listings with price drops ≥5%';

-- View: Statistics by rooms
CREATE OR REPLACE VIEW v_stats_by_rooms AS
SELECT 
    rooms,
    CASE 
        WHEN rooms = 0 THEN 'Студия'
        WHEN rooms = 1 THEN '1-комн'
        WHEN rooms = 2 THEN '2-комн'
        WHEN rooms = 3 THEN '3-комн'
        ELSE rooms || '-комн'
    END AS room_type,
    COUNT(*) AS listings_count,
    ROUND(AVG(area_total), 1) AS avg_area,
    ROUND(AVG(current_price), 0) AS avg_price,
    ROUND(AVG(price_per_sqm), 0) AS avg_price_per_sqm,
    ROUND(MIN(current_price), 0) AS min_price,
    ROUND(MAX(current_price), 0) AS max_price
FROM v_listings_with_latest_price
GROUP BY rooms
ORDER BY rooms;

COMMENT ON VIEW v_stats_by_rooms IS 'Statistics grouped by number of rooms';

