-- Migration: Valuation History and Comparables Tracking
-- Purpose: Store historical valuations and their comparables for trend analysis

-- Table: valuation_history
-- Stores each valuation request with results
CREATE TABLE IF NOT EXISTS valuation_history (
    valuation_id SERIAL PRIMARY KEY,
    
    -- Request parameters
    address TEXT NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    district_id INTEGER REFERENCES districts(district_id),
    
    -- Property characteristics
    area_total NUMERIC(6, 2) NOT NULL,
    rooms INTEGER,
    floor INTEGER,
    total_floors INTEGER,
    building_type TEXT,
    building_type_source TEXT, -- 'auto' or 'manual'
    
    -- Valuation results
    estimated_price BIGINT NOT NULL,
    estimated_price_per_sqm NUMERIC(10, 2) NOT NULL,
    price_range_low BIGINT,
    price_range_high BIGINT,
    confidence INTEGER,
    method_used TEXT,
    
    -- Metadata
    comparables_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    user_ip TEXT,
    user_agent TEXT,
    
    -- Indexes for fast lookup
    CONSTRAINT check_confidence CHECK (confidence >= 0 AND confidence <= 100)
);

CREATE INDEX idx_valuation_history_address ON valuation_history(address);
CREATE INDEX idx_valuation_history_coords ON valuation_history(lat, lon);
CREATE INDEX idx_valuation_history_created_at ON valuation_history(created_at DESC);

-- Table: valuation_comparables
-- Stores comparables used for each valuation
CREATE TABLE IF NOT EXISTS valuation_comparables (
    comparable_id SERIAL PRIMARY KEY,
    valuation_id INTEGER NOT NULL REFERENCES valuation_history(valuation_id) ON DELETE CASCADE,
    
    -- Comparable listing info
    listing_id BIGINT NOT NULL,
    url TEXT,
    
    -- Property details
    price BIGINT NOT NULL,
    price_per_sqm NUMERIC(10, 2) NOT NULL,
    area_total NUMERIC(6, 2) NOT NULL,
    rooms INTEGER,
    building_type TEXT,
    
    -- Matching metrics
    distance_km NUMERIC(5, 2),
    similarity_score NUMERIC(5, 2),
    weight NUMERIC(5, 4),
    rank INTEGER, -- 1, 2, 3 for TOP-3
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_valuation_comparables_valuation ON valuation_comparables(valuation_id);
CREATE INDEX idx_valuation_comparables_listing ON valuation_comparables(listing_id);
CREATE INDEX idx_valuation_comparables_rank ON valuation_comparables(valuation_id, rank);

-- View: valuation_history_summary
-- Quick summary of valuations by address
CREATE OR REPLACE VIEW valuation_history_summary AS
SELECT 
    address,
    COUNT(*) as valuation_count,
    MIN(estimated_price) as min_price,
    MAX(estimated_price) as max_price,
    AVG(estimated_price) as avg_price,
    MIN(created_at) as first_valuation,
    MAX(created_at) as last_valuation,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 86400 as days_tracked
FROM valuation_history
GROUP BY address
HAVING COUNT(*) > 1
ORDER BY last_valuation DESC;

-- Comments
COMMENT ON TABLE valuation_history IS 'Historical record of all property valuations';
COMMENT ON TABLE valuation_comparables IS 'Comparables used for each valuation for auditability';
COMMENT ON VIEW valuation_history_summary IS 'Summary of valuation trends by address';
