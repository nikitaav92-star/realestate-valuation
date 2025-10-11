-- CIAN Schema V3 - With photos and AI condition ratings
-- Updated: 2025-10-11
-- Purpose: Add photo storage and AI-based condition evaluation

-- Include V2 schema first
\i schema_v2_strict.sql

-- =============================================================================
-- LISTING PHOTOS
-- =============================================================================

CREATE TABLE IF NOT EXISTS listing_photos (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    
    -- Photo metadata
    photo_url TEXT NOT NULL,
    photo_order INT DEFAULT 0,  -- 0 = main photo
    is_main BOOLEAN DEFAULT FALSE,
    
    -- Download status (optional - for local storage)
    downloaded BOOLEAN DEFAULT FALSE,
    local_path TEXT,
    s3_url TEXT,
    file_size_bytes BIGINT,
    
    -- Metadata
    width INT,
    height INT,
    format TEXT,  -- jpg, png, webp
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT uq_listing_photo UNIQUE(listing_id, photo_url)
);

CREATE INDEX idx_listing_photos_listing ON listing_photos(listing_id);
CREATE INDEX idx_listing_photos_main ON listing_photos(listing_id, is_main) WHERE is_main = TRUE;
CREATE INDEX idx_listing_photos_order ON listing_photos(listing_id, photo_order);
CREATE INDEX idx_listing_photos_not_downloaded ON listing_photos(listing_id) WHERE downloaded = FALSE;

COMMENT ON TABLE listing_photos IS 'Photos from CIAN listings';
COMMENT ON COLUMN listing_photos.photo_order IS '0 = main photo, 1+ = additional photos';
COMMENT ON COLUMN listing_photos.is_main IS 'True for the primary/cover photo';

-- =============================================================================
-- AI CONDITION RATINGS
-- =============================================================================

CREATE TABLE IF NOT EXISTS listing_condition_ratings (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    
    -- Condition rating (1-5 scale)
    condition_score INT NOT NULL CHECK (condition_score BETWEEN 1 AND 5),
    condition_label TEXT NOT NULL CHECK (
        condition_label IN ('excellent', 'good', 'fair', 'poor', 'very_poor')
    ),
    
    -- AI analysis details
    ai_model TEXT NOT NULL,  -- gpt-4-vision-preview, claude-3.5-sonnet
    ai_analysis TEXT,  -- Detailed description from AI
    confidence NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    
    -- Condition details
    repair_quality TEXT CHECK (repair_quality IN ('excellent', 'good', 'average', 'poor')),
    furniture_condition TEXT,
    cleanliness TEXT CHECK (cleanliness IN ('excellent', 'good', 'average', 'poor')),
    modern_design BOOLEAN,
    needs_renovation BOOLEAN,
    
    -- Metadata
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    cost_usd NUMERIC(10,4),
    processing_time_sec NUMERIC(6,2),
    
    CONSTRAINT uq_listing_condition UNIQUE(listing_id)
);

CREATE INDEX idx_condition_ratings_listing ON listing_condition_ratings(listing_id);
CREATE INDEX idx_condition_ratings_score ON listing_condition_ratings(condition_score);
CREATE INDEX idx_condition_ratings_analyzed ON listing_condition_ratings(analyzed_at DESC);
CREATE INDEX idx_condition_ratings_model ON listing_condition_ratings(ai_model);

COMMENT ON TABLE listing_condition_ratings IS 'AI-based condition ratings using GPT-4 Vision or Claude';
COMMENT ON COLUMN listing_condition_ratings.condition_score IS '1=very poor, 2=poor, 3=fair, 4=good, 5=excellent';
COMMENT ON COLUMN listing_condition_ratings.confidence IS 'AI confidence score (0.0-1.0)';

-- =============================================================================
-- VIEWS: Enhanced with photos and condition
-- =============================================================================

-- Listings with photos and condition
CREATE OR REPLACE VIEW v_listings_complete AS
SELECT 
    l.*,
    lp.price AS current_price,
    lp.seen_at AS price_updated_at,
    ROUND(lp.price / l.area_total, 0) AS price_per_sqm,
    
    -- Main photo
    ph.photo_url AS main_photo_url,
    
    -- Condition rating
    lcr.condition_score,
    lcr.condition_label,
    lcr.ai_analysis,
    lcr.confidence AS condition_confidence,
    lcr.needs_renovation,
    
    -- Adjusted price based on condition
    CASE 
        WHEN lcr.condition_score = 5 THEN lp.price * 1.10
        WHEN lcr.condition_score = 4 THEN lp.price * 1.05
        WHEN lcr.condition_score = 3 THEN lp.price * 1.00
        WHEN lcr.condition_score = 2 THEN lp.price * 0.90
        WHEN lcr.condition_score = 1 THEN lp.price * 0.80
        ELSE lp.price
    END AS adjusted_price
FROM listings l
JOIN LATERAL (
    SELECT price, seen_at
    FROM listing_prices
    WHERE id = l.id
    ORDER BY seen_at DESC
    LIMIT 1
) lp ON true
LEFT JOIN LATERAL (
    SELECT photo_url
    FROM listing_photos
    WHERE listing_id = l.id AND is_main = TRUE
    LIMIT 1
) ph ON true
LEFT JOIN listing_condition_ratings lcr ON l.id = lcr.listing_id
WHERE l.is_active = TRUE;

COMMENT ON VIEW v_listings_complete IS 'Complete listing data with photos, prices, and AI condition ratings';

-- Statistics with condition analysis
CREATE OR REPLACE VIEW v_stats_with_condition AS
SELECT 
    condition_label,
    condition_score,
    COUNT(*) AS listings_count,
    ROUND(AVG(current_price), 0) AS avg_price,
    ROUND(AVG(price_per_sqm), 0) AS avg_price_per_sqm,
    ROUND(AVG(area_total), 1) AS avg_area,
    ROUND(AVG(confidence), 2) AS avg_confidence
FROM v_listings_complete
WHERE condition_score IS NOT NULL
GROUP BY condition_label, condition_score
ORDER BY condition_score DESC;

COMMENT ON VIEW v_stats_with_condition IS 'Statistics grouped by AI-rated condition';

-- Underpriced listings (good condition but low price)
CREATE OR REPLACE VIEW v_underpriced_opportunities AS
SELECT 
    id,
    url,
    address,
    rooms,
    area_total,
    current_price,
    price_per_sqm,
    condition_score,
    condition_label,
    adjusted_price,
    (adjusted_price - current_price) AS potential_value,
    ROUND(((adjusted_price - current_price) / current_price * 100), 1) AS underpriced_percent
FROM v_listings_complete
WHERE condition_score >= 4  -- Good or excellent condition
    AND price_per_sqm < (
        SELECT AVG(price_per_sqm) * 0.85  -- 15% below average
        FROM v_listings_complete
    )
ORDER BY underpriced_percent DESC;

COMMENT ON VIEW v_underpriced_opportunities IS 'Good condition apartments priced below market';

