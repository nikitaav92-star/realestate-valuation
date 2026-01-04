-- Mass Product Scraping Schema
-- Supports multi-source e-commerce data collection with price history
-- Compatible with existing realdb structure

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- PRODUCT SOURCES
-- =============================================================================

CREATE TABLE IF NOT EXISTS product_sources (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    timezone VARCHAR(50) DEFAULT 'UTC',
    default_currency CHAR(3) DEFAULT 'RUB',
    is_active BOOLEAN DEFAULT true,
    strategy_config JSONB,  -- Per-site anti-bot strategy
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE product_sources IS 'Master data for target e-commerce sites';
COMMENT ON COLUMN product_sources.strategy_config IS 'Anti-bot strategy: rate limits, proxy config, captcha type';

CREATE INDEX idx_product_sources_slug ON product_sources(slug) WHERE is_active;
CREATE INDEX idx_product_sources_active ON product_sources(is_active);

-- =============================================================================
-- PRODUCTS (Canonical SKU)
-- =============================================================================

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES product_sources(id) ON DELETE CASCADE,
    external_id VARCHAR(200) NOT NULL,  -- Site-specific product ID
    url TEXT NOT NULL,
    name TEXT NOT NULL,
    brand VARCHAR(200),
    category_path TEXT[],  -- Array of category hierarchy
    image_url TEXT,
    metadata JSONB,  -- Flexible storage for site-specific attributes
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT uq_products_source_external UNIQUE (source_id, external_id)
);

COMMENT ON TABLE products IS 'Canonical product catalog (SCD Type 2 ready)';
COMMENT ON COLUMN products.external_id IS 'Product ID from source site (SKU, ASIN, etc.)';
COMMENT ON COLUMN products.category_path IS 'Category breadcrumb as array: ["Electronics", "Smartphones", "Apple"]';
COMMENT ON COLUMN products.metadata IS 'Site-specific attributes: specs, features, seller info';
COMMENT ON COLUMN products.is_active IS 'False when product disappears from site for >7 days';

CREATE INDEX idx_products_source_external ON products(source_id, external_id);
CREATE INDEX idx_products_source_active ON products(source_id) WHERE is_active;
CREATE INDEX idx_products_last_seen ON products(last_seen DESC) WHERE is_active;
CREATE INDEX idx_products_brand ON products(brand) WHERE brand IS NOT NULL;
CREATE INDEX idx_products_category ON products USING GIN(category_path);
CREATE INDEX idx_products_metadata ON products USING GIN(metadata);

-- =============================================================================
-- PRODUCT OFFERS (Price & Availability Snapshots)
-- =============================================================================

CREATE TABLE IF NOT EXISTS product_offers (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Pricing (stored as integer minor units: cents, kopecks)
    price_minor INTEGER NOT NULL,
    currency CHAR(3) DEFAULT 'RUB',
    original_price_minor INTEGER,  -- Pre-discount price
    discount_percent NUMERIC(5, 2),
    
    -- Availability
    in_stock BOOLEAN DEFAULT true,
    stock_level INTEGER,  -- Exact stock if available
    availability_text TEXT,  -- "In stock", "2-3 days", "Out of stock"
    
    -- Delivery & Seller
    delivery_text TEXT,
    seller VARCHAR(200),
    seller_rating NUMERIC(3, 2),
    
    -- Raw data
    raw_payload JSONB,  -- Complete API response for debugging
    
    CONSTRAINT chk_price_minor_positive CHECK (price_minor > 0)
);

COMMENT ON TABLE product_offers IS 'Immutable snapshot of price/availability per collection run';
COMMENT ON COLUMN product_offers.price_minor IS 'Price in minor units (e.g., 12345 = 123.45 RUB)';
COMMENT ON COLUMN product_offers.original_price_minor IS 'Pre-discount price for promotion tracking';
COMMENT ON COLUMN product_offers.stock_level IS 'Exact stock count if site exposes it';
COMMENT ON COLUMN product_offers.raw_payload IS 'Full API response for audit/debugging';

CREATE INDEX idx_product_offers_product_time ON product_offers(product_id, collected_at DESC);
CREATE INDEX idx_product_offers_collected ON product_offers(collected_at DESC);
CREATE INDEX idx_product_offers_price ON product_offers(price_minor);
CREATE INDEX idx_product_offers_stock ON product_offers(in_stock, collected_at DESC);

-- =============================================================================
-- SCRAPE RUNS (Execution Metadata)
-- =============================================================================

CREATE TABLE IF NOT EXISTS scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES product_sources(id) ON DELETE CASCADE,
    run_uuid UUID DEFAULT uuid_generate_v4() UNIQUE,
    
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',  -- running, completed, failed, partial
    
    -- Metrics
    products_requested INTEGER DEFAULT 0,
    products_collected INTEGER DEFAULT 0,
    products_failed INTEGER DEFAULT 0,
    
    -- Anti-bot telemetry
    captcha_solved INTEGER DEFAULT 0,
    captcha_cost_usd NUMERIC(10, 4) DEFAULT 0,
    proxy_provider VARCHAR(50),
    escalation_level VARCHAR(50),  -- http_direct, smart_proxy, playwright_headless
    
    -- Diagnostics
    error_summary TEXT,
    notes TEXT,
    
    CONSTRAINT chk_scrape_runs_status CHECK (status IN ('running', 'completed', 'failed', 'partial'))
);

COMMENT ON TABLE scrape_runs IS 'Observability: track each scraping execution';
COMMENT ON COLUMN scrape_runs.escalation_level IS 'Highest anti-bot level used: http_direct → playwright_headed';
COMMENT ON COLUMN scrape_runs.captcha_cost_usd IS 'Estimated captcha solving cost for this run';

CREATE INDEX idx_scrape_runs_source_time ON scrape_runs(source_id, started_at DESC);
CREATE INDEX idx_scrape_runs_status ON scrape_runs(status, started_at DESC);
CREATE INDEX idx_scrape_runs_uuid ON scrape_runs(run_uuid);

-- =============================================================================
-- SCRAPE FAILURES (Error Diagnostics)
-- =============================================================================

CREATE TABLE IF NOT EXISTS scrape_failures (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES scrape_runs(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES products(id) ON DELETE SET NULL,
    
    failed_at TIMESTAMPTZ DEFAULT NOW(),
    error_type VARCHAR(50) NOT NULL,  -- http_timeout, captcha_failed, blocked, parse_error
    http_status INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    resolved_at TIMESTAMPTZ,
    
    -- Context
    url TEXT,
    proxy_used VARCHAR(100),
    escalation_level VARCHAR(50)
);

COMMENT ON TABLE scrape_failures IS 'Detailed error log for debugging and alerting';
COMMENT ON COLUMN scrape_failures.error_type IS 'Categorized error for metrics: http_timeout, blocked, etc.';
COMMENT ON COLUMN scrape_failures.resolved_at IS 'Timestamp when product was successfully collected on retry';

CREATE INDEX idx_scrape_failures_run ON scrape_failures(run_id, failed_at DESC);
CREATE INDEX idx_scrape_failures_product ON scrape_failures(product_id, failed_at DESC) WHERE product_id IS NOT NULL;
CREATE INDEX idx_scrape_failures_error_type ON scrape_failures(error_type, failed_at DESC);
CREATE INDEX idx_scrape_failures_unresolved ON scrape_failures(failed_at DESC) WHERE resolved_at IS NULL;

-- =============================================================================
-- VIEWS: Analytics-Ready Queries
-- =============================================================================

-- Latest offer per product
CREATE OR REPLACE VIEW v_products_latest_offers AS
SELECT DISTINCT ON (po.product_id)
    p.id AS product_id,
    p.source_id,
    p.external_id,
    p.name,
    p.brand,
    p.category_path,
    p.url,
    po.collected_at,
    po.price_minor,
    po.currency,
    po.original_price_minor,
    po.discount_percent,
    po.in_stock,
    po.stock_level,
    po.seller
FROM products p
INNER JOIN product_offers po ON p.id = po.product_id
WHERE p.is_active
ORDER BY po.product_id, po.collected_at DESC;

COMMENT ON VIEW v_products_latest_offers IS 'Latest price/availability snapshot per active product';

-- Price history timeline
CREATE OR REPLACE VIEW v_product_price_history AS
SELECT
    product_id,
    collected_at,
    price_minor,
    currency,
    original_price_minor,
    discount_percent,
    in_stock,
    LAG(price_minor) OVER (PARTITION BY product_id ORDER BY collected_at) AS prev_price_minor,
    CASE
        WHEN LAG(price_minor) OVER (PARTITION BY product_id ORDER BY collected_at) IS NOT NULL THEN
            ROUND(
                ((price_minor - LAG(price_minor) OVER (PARTITION BY product_id ORDER BY collected_at))::NUMERIC 
                / LAG(price_minor) OVER (PARTITION BY product_id ORDER BY collected_at) * 100),
                2
            )
        ELSE NULL
    END AS price_change_percent
FROM product_offers
ORDER BY product_id, collected_at DESC;

COMMENT ON VIEW v_product_price_history IS 'Price timeline with change percentages';

-- Daily price drops (≥5%)
CREATE OR REPLACE VIEW v_daily_price_drops AS
SELECT
    p.id AS product_id,
    p.name,
    p.brand,
    p.url,
    ps.name AS source,
    pph.collected_at,
    pph.prev_price_minor,
    pph.price_minor,
    pph.price_change_percent,
    pph.in_stock
FROM v_product_price_history pph
INNER JOIN products p ON pph.product_id = p.id
INNER JOIN product_sources ps ON p.source_id = ps.id
WHERE pph.price_change_percent <= -5.0
    AND pph.collected_at >= CURRENT_DATE
    AND p.is_active
ORDER BY pph.price_change_percent ASC;

COMMENT ON VIEW v_daily_price_drops IS 'Products with ≥5% price drop today';

-- Scraping health dashboard
CREATE OR REPLACE VIEW v_scraping_health AS
SELECT
    ps.name AS source,
    sr.started_at::DATE AS run_date,
    COUNT(sr.id) AS runs_count,
    SUM(sr.products_collected) AS total_collected,
    SUM(sr.products_failed) AS total_failed,
    ROUND(
        AVG(CASE WHEN sr.products_requested > 0 THEN 
            (sr.products_collected::NUMERIC / sr.products_requested * 100)
        ELSE 0 END),
        2
    ) AS avg_success_rate,
    SUM(sr.captcha_solved) AS total_captcha_solved,
    SUM(sr.captcha_cost_usd) AS total_captcha_cost
FROM scrape_runs sr
INNER JOIN product_sources ps ON sr.source_id = ps.id
WHERE sr.started_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY ps.name, sr.started_at::DATE
ORDER BY run_date DESC, source;

COMMENT ON VIEW v_scraping_health IS '7-day scraping metrics dashboard';

-- =============================================================================
-- TRIGGERS: Auto-update timestamps
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_product_sources_updated_at
    BEFORE UPDATE ON product_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- SAMPLE DATA (for testing)
-- =============================================================================

-- Example product source
INSERT INTO product_sources (slug, name, base_url, timezone, strategy_config)
VALUES (
    'ozon',
    'Ozon.ru',
    'https://www.ozon.ru',
    'Europe/Moscow',
    '{"rate_limit_rps": 1.5, "captcha_type": "recaptcha_v2", "proxy_requirement": "residential"}'::jsonb
) ON CONFLICT (slug) DO NOTHING;

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
