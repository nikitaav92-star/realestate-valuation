-- Migration 010: Add interest price fields to valuation_history
-- Date: 2025-12-16
-- Purpose: Add investment analysis fields (interest price, profit, etc.)

-- Add interest price fields to valuation_history
ALTER TABLE valuation_history 
ADD COLUMN IF NOT EXISTS interest_price BIGINT,
ADD COLUMN IF NOT EXISTS interest_price_per_sqm NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS expected_profit BIGINT,
ADD COLUMN IF NOT EXISTS profit_rate NUMERIC(5, 4),
ADD COLUMN IF NOT EXISTS investment_breakdown JSONB;

-- Update comments
COMMENT ON COLUMN valuation_history.interest_price IS 'Цена интереса (макс. цена покупки для достижения целевой прибыли)';
COMMENT ON COLUMN valuation_history.interest_price_per_sqm IS 'Цена интереса за м²';
COMMENT ON COLUMN valuation_history.expected_profit IS 'Ожидаемая прибыль при покупке по цене интереса';
COMMENT ON COLUMN valuation_history.profit_rate IS '% прибыли к вложениям';
COMMENT ON COLUMN valuation_history.investment_breakdown IS 'Детализация расходов (JSON)';

-- Drop and recreate view to include new fields
DROP VIEW IF EXISTS valuation_history_summary;
CREATE VIEW valuation_history_summary AS
SELECT 
    valuation_id,
    address,
    lat,
    lon,
    district_id,
    area_total,
    rooms,
    floor,
    total_floors,
    building_type,
    building_type_source,
    estimated_price,
    estimated_price_per_sqm,
    price_range_low,
    price_range_high,
    interest_price,
    interest_price_per_sqm,
    expected_profit,
    profit_rate,
    confidence,
    method_used,
    comparables_count,
    created_at,
    -- Calculate discount from market to interest price
    CASE 
        WHEN estimated_price > 0 AND interest_price IS NOT NULL
        THEN ROUND(((estimated_price - interest_price)::NUMERIC / estimated_price * 100), 2)
        ELSE NULL
    END as market_discount_percent
FROM valuation_history
ORDER BY created_at DESC;

COMMENT ON VIEW valuation_history_summary IS 'Summary view of valuation history with interest price analysis';
