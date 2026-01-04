-- Migration: Add full address and detailed apartment/house information
-- Date: 2025-11-20
-- Purpose: Store full addresses, apartment details, and house details

-- Add full address field (complete address from listing page)
ALTER TABLE listings ADD COLUMN IF NOT EXISTS address_full TEXT;

-- Apartment details
ALTER TABLE listings ADD COLUMN IF NOT EXISTS area_living NUMERIC;  -- Жилая площадь
ALTER TABLE listings ADD COLUMN IF NOT EXISTS area_kitchen NUMERIC;  -- Площадь кухни
ALTER TABLE listings ADD COLUMN IF NOT EXISTS balcony BOOLEAN;  -- Есть балкон
ALTER TABLE listings ADD COLUMN IF NOT EXISTS loggia BOOLEAN;  -- Есть лоджия
ALTER TABLE listings ADD COLUMN IF NOT EXISTS renovation TEXT;  -- Ремонт (без ремонта, косметический, евроремонт и т.д.)
ALTER TABLE listings ADD COLUMN IF NOT EXISTS rooms_layout TEXT;  -- Планировка (смежные, раздельные, свободная)

-- House details
ALTER TABLE listings ADD COLUMN IF NOT EXISTS house_year INTEGER;  -- Год постройки
ALTER TABLE listings ADD COLUMN IF NOT EXISTS house_material TEXT;  -- Материал стен (панельный, кирпичный, монолитный и т.д.)
ALTER TABLE listings ADD COLUMN IF NOT EXISTS house_series TEXT;  -- Серия дома
ALTER TABLE listings ADD COLUMN IF NOT EXISTS house_has_elevator BOOLEAN;  -- Есть лифт
ALTER TABLE listings ADD COLUMN IF NOT EXISTS house_has_parking BOOLEAN;  -- Есть парковка

-- Property type validation (apartment, flat, studio, share, newbuilding)
-- property_type already exists, but we'll add a check constraint
ALTER TABLE listings ADD CONSTRAINT IF NOT EXISTS check_property_type 
    CHECK (property_type IS NULL OR property_type IN ('flat', 'apartment', 'studio', 'share', 'newbuilding'));

-- Add index on property_type for filtering
CREATE INDEX IF NOT EXISTS idx_listings_property_type ON listings(property_type) WHERE property_type IS NOT NULL;

-- Add index on address_full for full-text search
CREATE INDEX IF NOT EXISTS idx_listings_address_full ON listings USING gin(to_tsvector('russian', COALESCE(address_full, '')));

-- Comments for documentation
COMMENT ON COLUMN listings.address_full IS 'Complete address from listing page (before normalization)';
COMMENT ON COLUMN listings.area_living IS 'Living area in square meters';
COMMENT ON COLUMN listings.area_kitchen IS 'Kitchen area in square meters';
COMMENT ON COLUMN listings.balcony IS 'Has balcony';
COMMENT ON COLUMN listings.loggia IS 'Has loggia';
COMMENT ON COLUMN listings.renovation IS 'Renovation type (без ремонта, косметический, евроремонт, дизайнерский)';
COMMENT ON COLUMN listings.rooms_layout IS 'Room layout (смежные, раздельные, свободная планировка)';
COMMENT ON COLUMN listings.house_year IS 'Year of construction';
COMMENT ON COLUMN listings.house_material IS 'Wall material (панельный, кирпичный, монолитный, блочный)';
COMMENT ON COLUMN listings.house_series IS 'House series (e.g., П-44, КОПЭ)';
COMMENT ON COLUMN listings.house_has_elevator IS 'Has elevator';
COMMENT ON COLUMN listings.house_has_parking IS 'Has parking';

SELECT '✅ Migration 004 completed - Full address and apartment/house details added';

