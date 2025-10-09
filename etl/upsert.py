"""Database helpers for idempotent upsert logic."""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

import psycopg2
from psycopg2.extensions import connection as PGConnection

from etl.models import Listing


def get_db_connection() -> PGConnection:
    """Return a psycopg2 connection using the DSN from the environment."""
    dsn = os.getenv("PG_DSN")
    if not dsn:
        raise RuntimeError("PG_DSN is not set")
    return psycopg2.connect(dsn)


def upsert_listing(conn: PGConnection, listing: Listing) -> None:
    """Insert or update a listing row and keep first_seen/last_seen consistent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO listings (
                id, url, region, deal_type, rooms,
                area_total, floor, address, seller_type,
                lat, lon,
                first_seen, last_seen, is_active
            )
            VALUES (
                %(id)s, %(url)s, %(region)s, %(deal_type)s, %(rooms)s,
                %(area_total)s, %(floor)s, %(address)s, %(seller_type)s,
                %(lat)s, %(lon)s,
                NOW(), NOW(), TRUE
            )
            ON CONFLICT (id) DO UPDATE
            SET
                url = EXCLUDED.url,
                region = EXCLUDED.region,
                deal_type = EXCLUDED.deal_type,
                rooms = EXCLUDED.rooms,
                area_total = EXCLUDED.area_total,
                floor = EXCLUDED.floor,
                address = EXCLUDED.address,
                seller_type = EXCLUDED.seller_type,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                last_seen = NOW(),
                is_active = TRUE;
            """,
            {
                "id": listing.id,
                "url": listing.url,
                "region": listing.region,
                "deal_type": listing.deal_type,
                "rooms": listing.rooms,
                "area_total": listing.area_total,
                "floor": listing.floor,
                "address": listing.address,
                "seller_type": listing.seller_type,
                "lat": listing.lat,
                "lon": listing.lon,
            },
        )


def _get_latest_price(conn: PGConnection, listing_id: int) -> Optional[Decimal]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT price
            FROM listing_prices
            WHERE id = %s
            ORDER BY seen_at DESC
            LIMIT 1;
            """,
            (listing_id,),
        )
        row = cur.fetchone()
    return Decimal(row[0]) if row is not None else None


def upsert_price_if_changed(conn: PGConnection, listing_id: int, new_price: float) -> bool:
    """Insert a price point only when the value has changed.

    Returns True if a new record was inserted to simplify testing.
    """
    latest = _get_latest_price(conn, listing_id)
    price_decimal = Decimal(str(new_price))
    if latest is not None and latest == price_decimal:
        return False

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO listing_prices (id, seen_at, price)
            VALUES (%s, clock_timestamp(), %s);
            """,
            (listing_id, price_decimal),
        )
    return True
