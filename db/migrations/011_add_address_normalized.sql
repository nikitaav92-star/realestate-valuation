-- Migration: Add address_normalized column for deduplication
-- Date: 2025-01-04

-- Add normalized address column
ALTER TABLE valuation_history ADD COLUMN IF NOT EXISTS address_normalized VARCHAR(500);

-- Populate for existing records
UPDATE valuation_history
SET address_normalized = lower(regexp_replace(
    regexp_replace(
        regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(address, '\s+', ' ', 'g'),
                        '(россия,?\s*|москва,?\s*|г\.?\s*москва,?\s*)', '', 'gi'
                    ),
                    '\bг\.?\s*', '', 'gi'
                ),
                '\bул\.?\s*', '', 'gi'
            ),
            '\bулица\s+', '', 'gi'
        ),
        '\bд\.?\s*', '', 'gi'
    ),
    '\bдом\s+', '', 'gi'
))
WHERE address_normalized IS NULL;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_valuation_history_address_normalized
ON valuation_history(address_normalized);

-- Create index for grouping
CREATE INDEX IF NOT EXISTS idx_valuation_history_address_normalized_created
ON valuation_history(address_normalized, created_at DESC);
