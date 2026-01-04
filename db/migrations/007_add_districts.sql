-- Migration: Add districts and district aggregates
-- Date: 2025-11-25
-- Purpose: Support interactive map with district-level aggregations

-- Create districts table
CREATE TABLE IF NOT EXISTS districts (
    district_id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    full_name TEXT,
    region_code VARCHAR(2),      -- КЛАДР регион (77 = Москва)
    district_code VARCHAR(3),    -- КЛАДР район
    fias_area_id UUID,           -- ФИАС ID района
    kladr_code VARCHAR(13),      -- Полный код КЛАДР
    geometry GEOMETRY(MULTIPOLYGON, 4326),  -- Границы района (WGS84)
    center_lat DOUBLE PRECISION,
    center_lon DOUBLE PRECISION,
    parent_district_id INTEGER REFERENCES districts(district_id),
    level INTEGER,               -- 1=округ, 2=район, 3=микрорайон
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for districts
CREATE INDEX IF NOT EXISTS idx_districts_geometry ON districts USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_districts_fias ON districts(fias_area_id);
CREATE INDEX IF NOT EXISTS idx_districts_kladr ON districts(kladr_code);
CREATE INDEX IF NOT EXISTS idx_districts_name ON districts(name);

-- Add comments for documentation
COMMENT ON TABLE districts IS 'Administrative districts for map aggregation';
COMMENT ON COLUMN districts.region_code IS 'KLADR region code (e.g. 77 for Moscow)';
COMMENT ON COLUMN districts.district_code IS 'KLADR district code';
COMMENT ON COLUMN districts.geometry IS 'District boundaries in WGS84 (EPSG:4326)';
COMMENT ON COLUMN districts.level IS '1=okrug (округ), 2=rayon (район), 3=microrayon';

-- Create district aggregates table
CREATE TABLE IF NOT EXISTS district_aggregates (
    district_id INTEGER REFERENCES districts(district_id),
    date DATE NOT NULL,
    avg_price_per_sqm NUMERIC(12, 2),
    median_price_per_sqm NUMERIC(12, 2),
    min_price NUMERIC(12, 2),
    max_price NUMERIC(12, 2),
    total_listings INTEGER,
    avg_area NUMERIC(6, 2),
    avg_rooms NUMERIC(4, 2),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (district_id, date)
);

-- Create indexes for aggregates
CREATE INDEX IF NOT EXISTS idx_aggregates_date ON district_aggregates(date DESC);
CREATE INDEX IF NOT EXISTS idx_aggregates_district ON district_aggregates(district_id);

-- Add comments
COMMENT ON TABLE district_aggregates IS 'Daily aggregated statistics per district';
COMMENT ON COLUMN district_aggregates.avg_price_per_sqm IS 'Average price per square meter';
COMMENT ON COLUMN district_aggregates.median_price_per_sqm IS 'Median price per square meter';

-- Add district_id field to listings table
ALTER TABLE listings ADD COLUMN IF NOT EXISTS district_id INTEGER REFERENCES districts(district_id);

-- Create index for lookups
CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district_id);

-- Add comment
COMMENT ON COLUMN listings.district_id IS 'Reference to district (for map aggregation)';

-- Create view for district statistics (real-time)
CREATE OR REPLACE VIEW district_stats_realtime AS
SELECT
    d.district_id,
    d.name,
    d.full_name,
    COUNT(l.id) as total_listings,
    ROUND(AVG(l.price_current / NULLIF(l.area_total, 0))::numeric, 2) as avg_price_per_sqm,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY l.price_current / NULLIF(l.area_total, 0)
    )::numeric, 2) as median_price_per_sqm,
    MIN(l.price_current) as min_price,
    MAX(l.price_current) as max_price,
    ROUND(AVG(l.area_total)::numeric, 2) as avg_area,
    ROUND(AVG(l.rooms::numeric), 2) as avg_rooms
FROM districts d
LEFT JOIN listings l ON l.district_id = d.district_id
    AND l.is_active = TRUE
    AND l.price_current > 0
    AND l.area_total > 0
GROUP BY d.district_id, d.name, d.full_name;

COMMENT ON VIEW district_stats_realtime IS 'Real-time statistics per district (not cached)';

SELECT '✅ Migration 007 completed - Districts and aggregates tables created';
