CREATE TABLE IF NOT EXISTS listings (
    id BIGINT PRIMARY KEY,
    url TEXT,
    region INT,
    deal_type TEXT,
    rooms INT,
    area_total NUMERIC,
    floor INT,
    address TEXT,
    seller_type TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS listing_prices (
    id BIGINT REFERENCES listings(id),
    seen_at TIMESTAMPTZ NOT NULL,
    price NUMERIC NOT NULL,
    PRIMARY KEY (id, seen_at)
);

ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;

ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_listings_region_deal_rooms
    ON listings (region, deal_type, rooms);

CREATE INDEX IF NOT EXISTS idx_listings_is_active
    ON listings (is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_listing_prices_latest
    ON listing_prices (id, seen_at DESC);
