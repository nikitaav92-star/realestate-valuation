-- Migration 012: Duplicate tracking system
-- Detects and links re-posted listings (same property, different CIAN ID)

-- Add fields to listings for duplicate tracking
ALTER TABLE listings ADD COLUMN IF NOT EXISTS is_repost BOOLEAN DEFAULT FALSE;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS original_listing_id BIGINT REFERENCES listings(id);
ALTER TABLE listings ADD COLUMN IF NOT EXISTS description_hash VARCHAR(64);

-- Table for tracking duplicate relationships
CREATE TABLE IF NOT EXISTS listing_duplicates (
    id SERIAL PRIMARY KEY,
    original_listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    duplicate_listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    similarity_score DECIMAL(3,2) NOT NULL DEFAULT 1.0,
    match_reason VARCHAR(50) NOT NULL, -- 'exact_description', 'same_address_price', 'similar_property'
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(original_listing_id, duplicate_listing_id),
    CHECK (original_listing_id != duplicate_listing_id)
);

-- Indexes for efficient duplicate detection
CREATE INDEX IF NOT EXISTS idx_listings_description_hash ON listings(description_hash) WHERE description_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_fias_area_rooms ON listings(fias_address, area_total, rooms) WHERE fias_address IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_is_repost ON listings(is_repost) WHERE is_repost = TRUE;
CREATE INDEX IF NOT EXISTS idx_listings_original ON listings(original_listing_id) WHERE original_listing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listing_duplicates_original ON listing_duplicates(original_listing_id);
CREATE INDEX IF NOT EXISTS idx_listing_duplicates_duplicate ON listing_duplicates(duplicate_listing_id);

-- Comment on columns
COMMENT ON COLUMN listings.is_repost IS 'True if this listing is a re-post of an earlier listing';
COMMENT ON COLUMN listings.original_listing_id IS 'ID of the original listing if this is a repost';
COMMENT ON COLUMN listings.description_hash IS 'MD5 hash of normalized description for duplicate detection';
COMMENT ON TABLE listing_duplicates IS 'Tracks relationships between duplicate/reposted listings';
