-- Migration 008: Multi-dimensional segmentation
-- Date: 2025-12-10
-- Purpose: Property type segmentation for precise valuation

-- Enable PostGIS if not enabled
CREATE EXTENSION IF NOT EXISTS postgis;

-- Property segments table
CREATE TABLE IF NOT EXISTS property_segments (
    segment_id SERIAL PRIMARY KEY,
    building_type VARCHAR(50) NOT NULL,
    building_height VARCHAR(20) NOT NULL,
    rooms_count INTEGER NOT NULL,
    UNIQUE(building_type, building_height, rooms_count),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_property_segments_type ON property_segments(building_type);
CREATE INDEX IF NOT EXISTS idx_property_segments_rooms ON property_segments(rooms_count);

COMMENT ON TABLE property_segments IS 'Property characteristics segments';

-- Multi-dimensional aggregates
CREATE TABLE IF NOT EXISTS multidim_aggregates (
    district_id INTEGER REFERENCES districts(district_id),
    property_segment_id INTEGER REFERENCES property_segments(segment_id),
    date DATE NOT NULL,
    
    avg_price_per_sqm NUMERIC(12, 2),
    median_price_per_sqm NUMERIC(12, 2),
    min_price NUMERIC(12, 2),
    max_price NUMERIC(12, 2),
    
    total_listings INTEGER,
    avg_area NUMERIC(6, 2),
    price_stddev NUMERIC(12, 2),
    confidence_score INTEGER,
    
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (district_id, property_segment_id, date)
);

CREATE INDEX IF NOT EXISTS idx_multidim_agg_date ON multidim_aggregates(date DESC);
CREATE INDEX IF NOT EXISTS idx_multidim_agg_district ON multidim_aggregates(district_id);
CREATE INDEX IF NOT EXISTS idx_multidim_agg_lookup 
ON multidim_aggregates(district_id, property_segment_id, date DESC);

COMMENT ON TABLE multidim_aggregates IS 'Price aggregates by district × property_segment × date';

-- Add property_segment_id to listings
ALTER TABLE listings 
ADD COLUMN IF NOT EXISTS property_segment_id INTEGER REFERENCES property_segments(segment_id);

CREATE INDEX IF NOT EXISTS idx_listings_property_segment ON listings(property_segment_id);

-- Helper functions
CREATE OR REPLACE FUNCTION classify_building_height(floors INTEGER)
RETURNS VARCHAR(20) AS $$
BEGIN
    IF floors IS NULL THEN RETURN NULL;
    ELSIF floors <= 5 THEN RETURN 'low';
    ELSIF floors <= 10 THEN RETURN 'medium';
    ELSE RETURN 'high';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION normalize_building_type(raw_type TEXT)
RETURNS VARCHAR(50) AS $$
BEGIN
    IF raw_type IS NULL THEN RETURN 'unknown';
    END IF;
    
    CASE LOWER(raw_type)
        WHEN 'panel' THEN RETURN 'panel';
        WHEN 'brick' THEN RETURN 'brick';
        WHEN 'monolithic' THEN RETURN 'monolithic';
        WHEN 'block' THEN RETURN 'block';
        WHEN 'wood' THEN RETURN 'wood';
        ELSE RETURN 'other';
    END CASE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Populate property_segments
INSERT INTO property_segments (building_type, building_height, rooms_count)
SELECT DISTINCT
    normalize_building_type(building_type) as building_type,
    classify_building_height(total_floors) as building_height,
    LEAST(rooms, 5) as rooms_count
FROM listings
WHERE building_type IS NOT NULL
  AND total_floors IS NOT NULL
  AND rooms IS NOT NULL
ON CONFLICT (building_type, building_height, rooms_count) DO NOTHING;

-- Add common combinations
INSERT INTO property_segments (building_type, building_height, rooms_count)
SELECT 
    bt.type,
    bh.height,
    r.rooms
FROM (VALUES ('panel'), ('brick'), ('monolithic'), ('block')) AS bt(type)
CROSS JOIN (VALUES ('low'), ('medium'), ('high')) AS bh(height)
CROSS JOIN (VALUES (1), (2), (3), (4), (5)) AS r(rooms)
ON CONFLICT (building_type, building_height, rooms_count) DO NOTHING;

-- Update listings with property_segment_id
UPDATE listings
SET property_segment_id = (
    SELECT segment_id
    FROM property_segments
    WHERE building_type = normalize_building_type(listings.building_type)
      AND building_height = classify_building_height(listings.total_floors)
      AND rooms_count = LEAST(listings.rooms, 5)
    LIMIT 1
)
WHERE building_type IS NOT NULL
  AND total_floors IS NOT NULL
  AND rooms IS NOT NULL
  AND property_segment_id IS NULL;

-- Summary
SELECT '✅ Migration 008 completed' as status;

SELECT 
    'Property segments created: ' || COUNT(*) as summary
FROM property_segments
UNION ALL
SELECT 
    'Listings with segment: ' || COUNT(*)
FROM listings
WHERE property_segment_id IS NOT NULL;

