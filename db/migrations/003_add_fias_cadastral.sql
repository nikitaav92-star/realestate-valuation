-- Migration: Add FIAS and cadastral data fields
-- Date: 2025-11-03
-- Purpose: Store normalized addresses and cadastral numbers

-- Add FIAS fields to listings table
ALTER TABLE listings ADD COLUMN IF NOT EXISTS fias_address TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS fias_id UUID;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS postal_code VARCHAR(6);
ALTER TABLE listings ADD COLUMN IF NOT EXISTS cadastral_number VARCHAR(50);
ALTER TABLE listings ADD COLUMN IF NOT EXISTS address_quality_code INTEGER;

-- Add index on FIAS ID for fast lookups
CREATE INDEX IF NOT EXISTS idx_listings_fias_id ON listings(fias_id);
CREATE INDEX IF NOT EXISTS idx_listings_cadastral_number ON listings(cadastral_number);

-- Add comments for documentation
COMMENT ON COLUMN listings.fias_address IS 'Normalized address according to FIAS standard';
COMMENT ON COLUMN listings.fias_id IS 'FIAS GUID (unique address identifier in Russian address system)';
COMMENT ON COLUMN listings.postal_code IS '6-digit postal code';
COMMENT ON COLUMN listings.cadastral_number IS 'Cadastral number of the building (from Rosreestr)';
COMMENT ON COLUMN listings.address_quality_code IS 'Address quality: 0=exact match, 1=good, 2-5=problems';

-- Create view for addresses with quality issues
CREATE OR REPLACE VIEW addresses_need_review AS
SELECT 
    id,
    url,
    address as raw_address,
    fias_address,
    address_quality_code,
    CASE 
        WHEN address_quality_code = 0 THEN 'Exact match'
        WHEN address_quality_code = 1 THEN 'Good'
        WHEN address_quality_code = 2 THEN 'Corrected'
        WHEN address_quality_code = 3 THEN 'Incomplete'
        WHEN address_quality_code >= 4 THEN 'Invalid'
        ELSE 'Not normalized'
    END as quality_status
FROM listings
WHERE address_quality_code IS NULL OR address_quality_code >= 2
ORDER BY address_quality_code DESC NULLS FIRST;

-- Create view for statistics
CREATE OR REPLACE VIEW address_normalization_stats AS
SELECT 
    COUNT(*) as total_listings,
    COUNT(fias_id) as normalized_count,
    COUNT(cadastral_number) as with_cadastral,
    ROUND(100.0 * COUNT(fias_id) / NULLIF(COUNT(*), 0), 1) as pct_normalized,
    ROUND(100.0 * COUNT(cadastral_number) / NULLIF(COUNT(*), 0), 1) as pct_with_cadastral,
    COUNT(*) FILTER (WHERE address_quality_code = 0) as exact_matches,
    COUNT(*) FILTER (WHERE address_quality_code = 1) as good_matches,
    COUNT(*) FILTER (WHERE address_quality_code >= 2) as need_review
FROM listings;

SELECT '✅ Migration 003 completed - FIAS and cadastral fields added';
