"""Database helpers for idempotent upsert logic."""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

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


def update_listing_details(
    conn: PGConnection,
    listing_id: int,
    details: Dict[str, Any]
) -> None:
    """Update listing with detailed information from detail page.

    Parameters
    ----------
    conn : PGConnection
        Database connection
    listing_id : int
        Listing ID
    details : dict
        Dictionary with keys: description, published_at, building_type, property_type
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE listings
            SET
                description = COALESCE(%(description)s, description),
                published_at = COALESCE(%(published_at)s, published_at),
                building_type = COALESCE(%(building_type)s, building_type),
                property_type = COALESCE(%(property_type)s, property_type)
            WHERE id = %(listing_id)s;
            """,
            {
                "listing_id": listing_id,
                "description": details.get("description"),
                "published_at": details.get("published_at"),
                "building_type": details.get("building_type"),
                "property_type": details.get("property_type"),
            },
        )


def insert_listing_photos(
    conn: PGConnection,
    listing_id: int,
    photos: List[Dict[str, Any]]
) -> int:
    """Insert photos for a listing.

    Parameters
    ----------
    conn : PGConnection
        Database connection
    listing_id : int
        Listing ID
    photos : list of dict
        List of photo dicts with keys: url, order, width, height

    Returns
    -------
    int
        Number of photos inserted (excludes duplicates)
    """
    inserted = 0
    with conn.cursor() as cur:
        for photo in photos:
            try:
                cur.execute(
                    """
                    INSERT INTO listing_photos (listing_id, photo_url, photo_order, width, height)
                    VALUES (%(listing_id)s, %(photo_url)s, %(photo_order)s, %(width)s, %(height)s)
                    ON CONFLICT (listing_id, photo_url) DO NOTHING;
                    """,
                    {
                        "listing_id": listing_id,
                        "photo_url": photo["url"],
                        "photo_order": photo["order"],
                        "width": photo.get("width"),
                        "height": photo.get("height"),
                    },
                )
                if cur.rowcount > 0:
                    inserted += 1
            except Exception as e:
                # Log and continue with next photo
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to insert photo {photo['url']} for listing {listing_id}: {e}"
                )
                continue

    return inserted


def upsert_fias_data(
    conn: PGConnection,
    listing_id: int,
    fias_address: Optional[str] = None,
    fias_id: Optional[str] = None,
    postal_code: Optional[str] = None,
    cadastral_number: Optional[str] = None,
    quality_code: Optional[int] = None,
) -> None:
    """
    Update FIAS and cadastral data for a listing.
    
    Args:
        conn: Database connection
        listing_id: Listing ID
        fias_address: Normalized FIAS address
        fias_id: FIAS GUID
        postal_code: 6-digit postal code
        cadastral_number: Cadastral number from Rosreestr
        quality_code: Address quality (0=exact, 1=good, 2-5=problems)
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE listings
            SET
                fias_address = %(fias_address)s,
                fias_id = %(fias_id)s,
                postal_code = %(postal_code)s,
                cadastral_number = %(cadastral_number)s,
                address_quality_code = %(quality_code)s
            WHERE id = %(listing_id)s;
            """,
            {
                "listing_id": listing_id,
                "fias_address": fias_address,
                "fias_id": fias_id,
                "postal_code": postal_code,
                "cadastral_number": cadastral_number,
                "quality_code": quality_code,
            },
        )
