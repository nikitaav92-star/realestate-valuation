-- =============================================================================
-- AUCTION LOTS DATABASE SCHEMA
-- Separate from main listings DB to avoid price contamination
-- =============================================================================
--
-- Sources:
--   1. FSSP (Federal Bailiff Service) - enforcement auctions
--   2. Bankruptcy (Fedresurs, lot-online) - bankruptcy sales
--   3. Bank Pledges - bank collateral sales
--   4. DGI Moscow - city property auctions
--
-- IMPORTANT: This DB is isolated from main realestate DB!
-- Auction prices follow different market dynamics.
-- =============================================================================

-- Enable PostGIS if not exists
CREATE EXTENSION IF NOT EXISTS postgis;

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

-- Auction source types
CREATE TYPE auction_source AS ENUM (
    'fssp',           -- ФССП - торги приставов
    'bankrupt',       -- Банкротство (Федресурс, lot-online)
    'bank_pledge',    -- Залоговое имущество банков
    'dgi_moscow'      -- ДГИ Москвы
);

-- Auction status
CREATE TYPE auction_status AS ENUM (
    'announced',      -- Объявлен
    'active',         -- Идут торги
    'completed',      -- Завершен (продан)
    'failed',         -- Не состоялся
    'cancelled'       -- Отменен
);

-- Property type
CREATE TYPE auction_property_type AS ENUM (
    'apartment',      -- Квартира
    'room',           -- Комната
    'house',          -- Дом
    'land',           -- Земельный участок
    'commercial',     -- Коммерческая недвижимость
    'parking',        -- Машиноместо
    'other'           -- Прочее
);

-- =============================================================================
-- MAIN TABLES
-- =============================================================================

-- Source platforms (for tracking multiple sites per source type)
CREATE TABLE auction_platforms (
    id SERIAL PRIMARY KEY,
    source_type auction_source NOT NULL,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    parser_module VARCHAR(255),  -- e.g., 'etl.auctions.fssp_parser'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Main auction lots table
CREATE TABLE auction_lots (
    id SERIAL PRIMARY KEY,

    -- External identifiers
    external_id VARCHAR(255) NOT NULL,        -- ID from source platform
    platform_id INTEGER REFERENCES auction_platforms(id),
    source_type auction_source NOT NULL,
    source_url VARCHAR(1000),                 -- Direct link to lot

    -- Lot info
    lot_number VARCHAR(100),                  -- Номер лота
    case_number VARCHAR(255),                 -- Номер дела (для банкротства/ФССП)

    -- Property details
    property_type auction_property_type DEFAULT 'apartment',
    title VARCHAR(500),
    description TEXT,

    -- Location
    region VARCHAR(255),
    city VARCHAR(255),
    district VARCHAR(255),
    address TEXT,
    address_normalized TEXT,                  -- FIAS normalized
    fias_id VARCHAR(50),

    -- Coordinates
    lat NUMERIC(10, 7),
    lon NUMERIC(10, 7),
    geom GEOMETRY(Point, 4326),

    -- Property characteristics
    area_total NUMERIC(10, 2),               -- Общая площадь
    area_living NUMERIC(10, 2),              -- Жилая площадь
    area_kitchen NUMERIC(10, 2),             -- Кухня
    rooms INTEGER,                            -- Кол-во комнат
    floor INTEGER,
    total_floors INTEGER,
    building_year INTEGER,

    -- Pricing
    initial_price NUMERIC(15, 2),            -- Начальная цена
    current_price NUMERIC(15, 2),            -- Текущая цена (может меняться)
    step_price NUMERIC(15, 2),               -- Шаг аукциона
    deposit_amount NUMERIC(15, 2),           -- Задаток
    final_price NUMERIC(15, 2),              -- Финальная цена (если продан)

    -- Calculated fields
    price_per_sqm NUMERIC(12, 2),            -- Цена за м²
    discount_percent NUMERIC(5, 2),          -- Дисконт от рынка (расчетный)

    -- Auction timing
    auction_date TIMESTAMPTZ,                -- Дата проведения
    auction_end_date TIMESTAMPTZ,            -- Дата окончания приема заявок
    application_deadline TIMESTAMPTZ,        -- Крайний срок подачи заявки

    -- Status
    status auction_status DEFAULT 'announced',
    is_repeat_auction BOOLEAN DEFAULT FALSE, -- Повторные торги
    repeat_number INTEGER DEFAULT 0,         -- Номер повторных торгов

    -- Organizer info
    organizer_name VARCHAR(500),             -- Организатор
    organizer_inn VARCHAR(20),
    organizer_contact TEXT,

    -- Debtor info (for bankruptcy/FSSP)
    debtor_name VARCHAR(500),
    debtor_inn VARCHAR(20),

    -- Bank info (for pledges)
    bank_name VARCHAR(255),

    -- Metadata
    photos JSONB DEFAULT '[]',               -- Array of photo URLs
    documents JSONB DEFAULT '[]',            -- Array of document URLs
    raw_data JSONB,                          -- Original parsed data

    -- Timestamps
    published_at TIMESTAMPTZ,                -- Когда опубликован на источнике
    first_seen_at TIMESTAMPTZ DEFAULT NOW(), -- Когда мы впервые увидели
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),  -- Последняя проверка
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_lot_per_platform UNIQUE (platform_id, external_id)
);

-- Price history (for tracking price changes during auction)
CREATE TABLE auction_price_history (
    id SERIAL PRIMARY KEY,
    lot_id INTEGER REFERENCES auction_lots(id) ON DELETE CASCADE,
    price NUMERIC(15, 2) NOT NULL,
    price_type VARCHAR(50) DEFAULT 'current', -- initial, current, final
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bid history (if we can track bids)
CREATE TABLE auction_bids (
    id SERIAL PRIMARY KEY,
    lot_id INTEGER REFERENCES auction_lots(id) ON DELETE CASCADE,
    bid_amount NUMERIC(15, 2) NOT NULL,
    bid_time TIMESTAMPTZ,
    bidder_info VARCHAR(255),                -- Anonymized bidder info if available
    is_winning BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comparison with market prices
CREATE TABLE auction_market_comparison (
    id SERIAL PRIMARY KEY,
    lot_id INTEGER REFERENCES auction_lots(id) ON DELETE CASCADE,

    -- Market estimate (from our valuation API)
    market_price_estimate NUMERIC(15, 2),
    market_price_per_sqm NUMERIC(12, 2),
    estimation_method VARCHAR(50),
    estimation_confidence NUMERIC(5, 2),

    -- Discount calculation
    discount_from_market NUMERIC(5, 2),      -- Percentage discount

    -- Comparable listings count
    comparables_count INTEGER,

    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Primary lookups
CREATE INDEX idx_auction_lots_source ON auction_lots(source_type);
CREATE INDEX idx_auction_lots_status ON auction_lots(status);
CREATE INDEX idx_auction_lots_property_type ON auction_lots(property_type);
CREATE INDEX idx_auction_lots_auction_date ON auction_lots(auction_date);

-- Location indexes
CREATE INDEX idx_auction_lots_region ON auction_lots(region);
CREATE INDEX idx_auction_lots_city ON auction_lots(city);
CREATE INDEX idx_auction_lots_district ON auction_lots(district);
CREATE INDEX idx_auction_lots_geom ON auction_lots USING GIST(geom);

-- Price indexes
CREATE INDEX idx_auction_lots_current_price ON auction_lots(current_price);
CREATE INDEX idx_auction_lots_price_per_sqm ON auction_lots(price_per_sqm);

-- Property characteristics
CREATE INDEX idx_auction_lots_area ON auction_lots(area_total);
CREATE INDEX idx_auction_lots_rooms ON auction_lots(rooms);

-- Composite indexes for common queries
CREATE INDEX idx_auction_lots_active_moscow ON auction_lots(city, status)
    WHERE city = 'Москва' AND status IN ('announced', 'active');

CREATE INDEX idx_auction_lots_source_status ON auction_lots(source_type, status);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_auction_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auction_lots_updated
    BEFORE UPDATE ON auction_lots
    FOR EACH ROW
    EXECUTE FUNCTION update_auction_updated_at();

-- Auto-calculate geom from lat/lon
CREATE OR REPLACE FUNCTION update_auction_geom()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.lat IS NOT NULL AND NEW.lon IS NOT NULL THEN
        NEW.geom = ST_SetSRID(ST_MakePoint(NEW.lon, NEW.lat), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auction_lots_geom
    BEFORE INSERT OR UPDATE ON auction_lots
    FOR EACH ROW
    EXECUTE FUNCTION update_auction_geom();

-- Auto-calculate price_per_sqm
CREATE OR REPLACE FUNCTION update_auction_price_per_sqm()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.current_price IS NOT NULL AND NEW.area_total IS NOT NULL AND NEW.area_total > 0 THEN
        NEW.price_per_sqm = NEW.current_price / NEW.area_total;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auction_price_per_sqm
    BEFORE INSERT OR UPDATE ON auction_lots
    FOR EACH ROW
    EXECUTE FUNCTION update_auction_price_per_sqm();

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Active auctions summary
CREATE VIEW v_active_auctions AS
SELECT
    l.id,
    l.source_type,
    p.name as platform_name,
    l.lot_number,
    l.property_type,
    l.address,
    l.city,
    l.district,
    l.area_total,
    l.rooms,
    l.floor,
    l.total_floors,
    l.initial_price,
    l.current_price,
    l.price_per_sqm,
    l.auction_date,
    l.status,
    l.source_url,
    l.is_repeat_auction,
    l.repeat_number,
    mc.market_price_estimate,
    mc.discount_from_market
FROM auction_lots l
LEFT JOIN auction_platforms p ON l.platform_id = p.id
LEFT JOIN auction_market_comparison mc ON l.id = mc.lot_id
WHERE l.status IN ('announced', 'active')
ORDER BY l.auction_date ASC;

-- Auctions by source
CREATE VIEW v_auctions_by_source AS
SELECT
    source_type,
    status,
    COUNT(*) as count,
    AVG(current_price) as avg_price,
    AVG(price_per_sqm) as avg_price_per_sqm,
    AVG(area_total) as avg_area
FROM auction_lots
GROUP BY source_type, status
ORDER BY source_type, status;

-- Best deals (highest discount)
CREATE VIEW v_best_auction_deals AS
SELECT
    l.*,
    mc.market_price_estimate,
    mc.discount_from_market,
    mc.comparables_count
FROM auction_lots l
JOIN auction_market_comparison mc ON l.id = mc.lot_id
WHERE l.status IN ('announced', 'active')
  AND mc.discount_from_market > 10  -- More than 10% discount
ORDER BY mc.discount_from_market DESC;

-- Moscow apartments on auction
CREATE VIEW v_moscow_auction_apartments AS
SELECT *
FROM auction_lots
WHERE city = 'Москва'
  AND property_type = 'apartment'
  AND status IN ('announced', 'active')
ORDER BY auction_date ASC;

-- =============================================================================
-- SEED DATA: Platforms
-- =============================================================================

INSERT INTO auction_platforms (source_type, name, url, parser_module) VALUES
    ('fssp', 'ФССП России - Торги', 'https://torgi.gov.ru/', 'etl.auctions.fssp_parser'),
    ('fssp', 'Торги приставов', 'https://fssprus.ru/torgi', 'etl.auctions.fssp_parser'),
    ('bankrupt', 'Федресурс', 'https://bankrot.fedresurs.ru/', 'etl.auctions.fedresurs_parser'),
    ('bankrupt', 'Lot-Online', 'https://lot-online.ru/', 'etl.auctions.lot_online_parser'),
    ('bankrupt', 'ЕФРСБ', 'https://old.bankrot.fedresurs.ru/', 'etl.auctions.efrsb_parser'),
    ('bank_pledge', 'Сбербанк - Витрина залогов', 'https://www.sberbank.ru/ru/person/credits/money/zalog', 'etl.auctions.sber_parser'),
    ('bank_pledge', 'ВТБ - Залоговое имущество', 'https://www.vtb.ru/personal/zalog/', 'etl.auctions.vtb_parser'),
    ('bank_pledge', 'Альфа-Банк - Залоги', 'https://alfabank.ru/personal/loans/collateral/', 'etl.auctions.alfa_parser'),
    ('dgi_moscow', 'ДГИ Москвы', 'https://investmoscow.ru/', 'etl.auctions.dgi_parser'),
    ('dgi_moscow', 'Росимущество Москва', 'https://torgi.gov.ru/', 'etl.auctions.rosim_parser');

-- =============================================================================
-- STATISTICS & MONITORING
-- =============================================================================

-- Scraping statistics
CREATE TABLE auction_scrape_stats (
    id SERIAL PRIMARY KEY,
    platform_id INTEGER REFERENCES auction_platforms(id),
    scrape_date DATE DEFAULT CURRENT_DATE,
    lots_found INTEGER DEFAULT 0,
    lots_new INTEGER DEFAULT 0,
    lots_updated INTEGER DEFAULT 0,
    lots_closed INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    duration_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily stats view
CREATE VIEW v_daily_scrape_stats AS
SELECT
    s.scrape_date,
    p.source_type,
    p.name as platform_name,
    s.lots_found,
    s.lots_new,
    s.lots_updated,
    s.lots_closed,
    s.errors,
    s.duration_seconds
FROM auction_scrape_stats s
JOIN auction_platforms p ON s.platform_id = p.id
ORDER BY s.scrape_date DESC, p.source_type;

-- =============================================================================
-- PERMISSIONS (adjust as needed)
-- =============================================================================

-- Grant permissions to application user
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO realuser;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO realuser;

COMMENT ON TABLE auction_lots IS 'Main table for auction lots from all sources (FSSP, bankruptcy, banks, DGI). Separate from main listings to avoid price contamination.';
COMMENT ON TABLE auction_platforms IS 'Source platforms for auction data';
COMMENT ON TABLE auction_price_history IS 'Track price changes during auction lifecycle';
COMMENT ON TABLE auction_market_comparison IS 'Comparison with market prices from main valuation system';
