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
