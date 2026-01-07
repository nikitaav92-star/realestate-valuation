"""Database helpers for idempotent upsert logic."""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

import psycopg2
from psycopg2.extensions import connection as PGConnection

from etl.models import Listing

DEFAULT_DEV_DSN = "postgresql://realuser:strongpass123@localhost:5432/realdb"


def _build_dsn_from_components() -> Optional[str]:
    """Construct a DSN from granular PG_* env variables if available."""
    user = os.getenv("PG_USER") or os.getenv("POSTGRES_USER")
    password = (
        os.getenv("PG_PASSWORD")
        or os.getenv("PG_PASS")
        or os.getenv("POSTGRES_PASSWORD")
    )
    host = os.getenv("PG_HOST") or os.getenv("POSTGRES_HOST")
    port = os.getenv("PG_PORT") or os.getenv("POSTGRES_PORT")
    database = os.getenv("PG_DB") or os.getenv("POSTGRES_DB")

    if not all([user, password, host, port, database]):
        return None
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _resolve_pg_dsn() -> Optional[str]:
    """Return best-effort DSN from environment variables."""
    for key in ("PG_DSN", "PG_DSN_INTERNAL"):
        value = os.getenv(key)
        if value:
            return value

    composed = _build_dsn_from_components()
    if composed:
        return composed

    return DEFAULT_DEV_DSN



def get_db_connection() -> PGConnection:
    """Return a psycopg2 connection using the best available DSN."""
    dsn = _resolve_pg_dsn()
    if not dsn:
        raise RuntimeError(
            "PG_DSN is not set. Create .env per PRODUCTION_REQUIREMENTS.md or export PG_DSN."
        )
    return psycopg2.connect(dsn)


def upsert_listing(conn: PGConnection, listing: Listing, max_retries: int = 3) -> None:
    """Insert or update a listing row and keep first_seen/last_seen consistent.

    Includes retry logic for deadlock handling in parallel parsing.
    """
    import time
    import random

    for attempt in range(max_retries):
        try:
            with conn.cursor() as cur:
                cur.execute(
            """
            INSERT INTO listings (
                id, url, region, deal_type, rooms,
                area_total, floor, address, address_full, seller_type,
                lat, lon,
                area_living, area_kitchen, balcony, loggia, renovation, rooms_layout,
                house_year, house_material, house_series, house_has_elevator, house_has_parking,
                first_seen, last_seen, is_active
            )
            VALUES (
                %(id)s, %(url)s, %(region)s, %(deal_type)s, %(rooms)s,
                %(area_total)s, %(floor)s, %(address)s, %(address_full)s, %(seller_type)s,
                %(lat)s, %(lon)s,
                %(area_living)s, %(area_kitchen)s, %(balcony)s, %(loggia)s, %(renovation)s, %(rooms_layout)s,
                %(house_year)s, %(house_material)s, %(house_series)s, %(house_has_elevator)s, %(house_has_parking)s,
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
                address_full = COALESCE(EXCLUDED.address_full, listings.address_full),
                seller_type = EXCLUDED.seller_type,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                area_living = COALESCE(EXCLUDED.area_living, listings.area_living),
                area_kitchen = COALESCE(EXCLUDED.area_kitchen, listings.area_kitchen),
                balcony = COALESCE(EXCLUDED.balcony, listings.balcony),
                loggia = COALESCE(EXCLUDED.loggia, listings.loggia),
                renovation = COALESCE(EXCLUDED.renovation, listings.renovation),
                rooms_layout = COALESCE(EXCLUDED.rooms_layout, listings.rooms_layout),
                house_year = COALESCE(EXCLUDED.house_year, listings.house_year),
                house_material = COALESCE(EXCLUDED.house_material, listings.house_material),
                house_series = COALESCE(EXCLUDED.house_series, listings.house_series),
                house_has_elevator = COALESCE(EXCLUDED.house_has_elevator, listings.house_has_elevator),
                house_has_parking = COALESCE(EXCLUDED.house_has_parking, listings.house_has_parking),
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
                "address_full": listing.address_full,
                "seller_type": listing.seller_type,
                "lat": listing.lat,
                "lon": listing.lon,
                "area_living": listing.area_living,
                "area_kitchen": listing.area_kitchen,
                "balcony": listing.balcony,
                "loggia": listing.loggia,
                "renovation": listing.renovation,
                "rooms_layout": listing.rooms_layout,
                "house_year": listing.house_year,
                "house_material": listing.house_material,
                "house_series": listing.house_series,
                "house_has_elevator": listing.house_has_elevator,
                "house_has_parking": listing.house_has_parking,
            },
                )
            return  # Success
        except psycopg2.errors.DeadlockDetected:
            conn.rollback()
            if attempt < max_retries - 1:
                wait_time = (0.1 * (2 ** attempt)) + random.uniform(0, 0.1)
                time.sleep(wait_time)
            else:
                raise  # Re-raise after all retries exhausted


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
        Dictionary with keys: address_full, description, published_at, building_type, property_type,
        floor, total_floors, area_living, area_kitchen, balcony, loggia, renovation, rooms_layout,
        house_year, house_material, house_series, house_has_elevator, house_has_parking,
        has_encumbrances, encumbrance_types, encumbrance_details, encumbrance_confidence
    """
    import json

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE listings
            SET
                address_full = COALESCE(%(address_full)s, address_full),
                description = COALESCE(%(description)s, description),
                published_at = COALESCE(%(published_at)s, published_at),
                building_type = COALESCE(%(building_type)s, building_type),
                property_type = COALESCE(%(property_type)s, property_type),
                floor = COALESCE(%(floor)s, floor),
                total_floors = COALESCE(%(total_floors)s, total_floors),
                lat = COALESCE(%(lat)s, lat),
                lon = COALESCE(%(lon)s, lon),
                area_living = COALESCE(%(area_living)s, area_living),
                area_kitchen = COALESCE(%(area_kitchen)s, area_kitchen),
                balcony = COALESCE(%(balcony)s, balcony),
                loggia = COALESCE(%(loggia)s, loggia),
                renovation = COALESCE(%(renovation)s, renovation),
                rooms_layout = COALESCE(%(rooms_layout)s, rooms_layout),
                house_year = COALESCE(%(house_year)s, house_year),
                house_material = COALESCE(%(house_material)s, house_material),
                house_series = COALESCE(%(house_series)s, house_series),
                house_has_elevator = COALESCE(%(house_has_elevator)s, house_has_elevator),
                house_has_parking = COALESCE(%(house_has_parking)s, house_has_parking),
                is_newbuilding_resale = COALESCE(%(is_newbuilding_resale)s, is_newbuilding_resale),
                initial_price = COALESCE(%(initial_price)s, initial_price),
                price_change_pct = COALESCE(%(price_change_pct)s, price_change_pct),
                days_on_market = COALESCE(%(days_on_market)s, days_on_market),
                has_encumbrances = COALESCE(%(has_encumbrances)s, has_encumbrances),
                encumbrance_types = COALESCE(%(encumbrance_types)s, encumbrance_types),
                encumbrance_details = COALESCE(%(encumbrance_details)s, encumbrance_details),
                encumbrance_confidence = COALESCE(%(encumbrance_confidence)s, encumbrance_confidence),
                description_hash = COALESCE(%(description_hash)s, description_hash)
            WHERE id = %(listing_id)s;
            """,
            {
                "listing_id": listing_id,
                "address_full": details.get("address_full"),
                "description": details.get("description"),
                "published_at": details.get("published_at"),
                "building_type": details.get("building_type"),
                "property_type": details.get("property_type"),
                "floor": details.get("floor"),
                "total_floors": details.get("total_floors"),
                "lat": details.get("lat"),
                "lon": details.get("lon"),
                "area_living": details.get("area_living"),
                "area_kitchen": details.get("area_kitchen"),
                "balcony": details.get("balcony"),
                "loggia": details.get("loggia"),
                "renovation": details.get("renovation"),
                "rooms_layout": details.get("rooms_layout"),
                "house_year": details.get("house_year"),
                "house_material": details.get("house_material"),
                "house_series": details.get("house_series"),
                "house_has_elevator": details.get("house_has_elevator"),
                "house_has_parking": details.get("house_has_parking"),
                "is_newbuilding_resale": details.get("is_newbuilding_resale"),
                "initial_price": details.get("initial_price"),
                "price_change_pct": details.get("price_change_pct"),
                "days_on_market": details.get("days_on_market"),
                "has_encumbrances": details.get("has_encumbrances"),
                "encumbrance_types": details.get("encumbrance_types"),
                "encumbrance_details": json.dumps(details.get("encumbrance_details")) if details.get("encumbrance_details") else None,
                "encumbrance_confidence": details.get("encumbrance_confidence"),
                "description_hash": details.get("description_hash"),
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


def insert_price_history(
    conn: PGConnection,
    listing_id: int,
    price_history: List[Dict[str, Any]]
) -> int:
    """Insert price history records for a listing.

    Parameters
    ----------
    conn : PGConnection
        Database connection
    listing_id : int
        The listing's internal ID
    price_history : list
        List of {price, date} dicts from CIAN

    Returns
    -------
    int
        Number of records inserted
    """
    if not price_history:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for record in price_history:
            try:
                cur.execute(
                    """
                    INSERT INTO listing_price_history (listing_id, cian_id, price, recorded_at, source)
                    SELECT %(listing_id)s, l.id, %(price)s, %(recorded_at)s::timestamp, 'cian_history'
                    FROM listings l WHERE l.id = %(listing_id)s
                    ON CONFLICT DO NOTHING;
                    """,
                    {
                        "listing_id": listing_id,
                        "price": record.get("price"),
                        "recorded_at": record.get("date"),
                    },
                )
                if cur.rowcount > 0:
                    inserted += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to insert price history for listing {listing_id}: {e}"
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
