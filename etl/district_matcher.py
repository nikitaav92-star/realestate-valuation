"""District matching module - assigns districts to listings based on coordinates."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

LOGGER = logging.getLogger(__name__)


def find_district_by_coordinates(conn, lat: float, lon: float) -> Optional[int]:
    """
    Find district ID by coordinates using PostGIS spatial query.

    Args:
        conn: Database connection
        lat: Latitude
        lon: Longitude

    Returns:
        district_id if found, None otherwise
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT district_id
            FROM districts
            WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(%s, %s), 4326))
            LIMIT 1;
            """,
            (lon, lat)  # Note: PostGIS uses (lon, lat) order
        )
        result = cur.fetchone()
        return result[0] if result else None


def update_listing_district(conn, listing_id: int, district_id: int) -> bool:
    """
    Update listing with district ID.

    Args:
        conn: Database connection
        listing_id: Listing ID
        district_id: District ID to assign

    Returns:
        True if updated, False otherwise
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE listings
            SET district_id = %s
            WHERE id = %s AND district_id IS NULL;
            """,
            (district_id, listing_id)
        )
        return cur.rowcount > 0


def assign_districts_to_listings(conn, limit: int = 1000) -> Tuple[int, int]:
    """
    Assign districts to listings that have coordinates but no district.

    Args:
        conn: Database connection
        limit: Maximum number of listings to process

    Returns:
        Tuple of (success_count, not_found_count)
    """
    # Get listings with coordinates but no district
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, lat, lon
            FROM listings
            WHERE lat IS NOT NULL
            AND lon IS NOT NULL
            AND district_id IS NULL
            LIMIT %s;
            """,
            (limit,)
        )
        listings = cur.fetchall()

    if not listings:
        LOGGER.info("No listings need district assignment")
        return 0, 0

    LOGGER.info(f"Assigning districts to {len(listings)} listings...")

    success = 0
    not_found = 0

    for listing_id, lat, lon in listings:
        district_id = find_district_by_coordinates(conn, lat, lon)
        if district_id:
            if update_listing_district(conn, listing_id, district_id):
                success += 1
        else:
            not_found += 1
            LOGGER.debug(f"No district found for listing {listing_id} at ({lat}, {lon})")

    conn.commit()
    LOGGER.info(f"District assignment complete: {success} assigned, {not_found} not found")

    return success, not_found


def extract_district_from_address(address: str) -> Optional[str]:
    """
    Extract district name from CIAN address string.

    CIAN addresses often contain district info like:
    "Москва, СВАО, р-н Алтуфьевский, ..."
    "Москва, ЗАО, р-н Очаково-Матвеевское, ..."

    Args:
        address: Address string

    Returns:
        District name if found, None otherwise
    """
    import re

    # Pattern: "р-н <District Name>" or "район <District Name>"
    patterns = [
        r'р-н\s+([А-ЯЁа-яё\-]+(?:\s+[А-ЯЁа-яё\-]+)?)',
        r'район\s+([А-ЯЁа-яё\-]+(?:\s+[А-ЯЁа-яё\-]+)?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, address, re.IGNORECASE)
        if match:
            district_name = match.group(1).strip()
            # Clean up common suffixes
            district_name = re.sub(r'(ий|ое|ая|ый)$', '', district_name)
            return district_name

    return None


def find_district_by_name(conn, district_name: str) -> Optional[int]:
    """
    Find district ID by name using fuzzy matching.

    Args:
        conn: Database connection
        district_name: District name to search

    Returns:
        district_id if found, None otherwise
    """
    with conn.cursor() as cur:
        # Try exact match first
        cur.execute(
            """
            SELECT district_id
            FROM districts
            WHERE LOWER(name) = LOWER(%s)
            OR LOWER(full_name) LIKE LOWER(%s)
            LIMIT 1;
            """,
            (district_name, f'%{district_name}%')
        )
        result = cur.fetchone()
        if result:
            return result[0]

        # Try partial match
        cur.execute(
            """
            SELECT district_id
            FROM districts
            WHERE LOWER(name) LIKE LOWER(%s)
            OR LOWER(full_name) LIKE LOWER(%s)
            LIMIT 1;
            """,
            (f'%{district_name}%', f'%{district_name}%')
        )
        result = cur.fetchone()
        return result[0] if result else None


def assign_districts_by_address(conn, limit: int = 1000) -> Tuple[int, int]:
    """
    Assign districts to listings by extracting district from address text.

    Fallback method when coordinates are not available.

    Args:
        conn: Database connection
        limit: Maximum number of listings to process

    Returns:
        Tuple of (success_count, not_found_count)
    """
    # Get listings without district and without coordinates
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, COALESCE(address_full, address) as address
            FROM listings
            WHERE district_id IS NULL
            AND (lat IS NULL OR lon IS NULL)
            AND (address IS NOT NULL OR address_full IS NOT NULL)
            LIMIT %s;
            """,
            (limit,)
        )
        listings = cur.fetchall()

    if not listings:
        LOGGER.info("No listings need district assignment by address")
        return 0, 0

    LOGGER.info(f"Assigning districts by address to {len(listings)} listings...")

    success = 0
    not_found = 0

    for listing_id, address in listings:
        district_name = extract_district_from_address(address)
        if district_name:
            district_id = find_district_by_name(conn, district_name)
            if district_id:
                if update_listing_district(conn, listing_id, district_id):
                    success += 1
                    continue

        not_found += 1

    conn.commit()
    LOGGER.info(f"District by address complete: {success} assigned, {not_found} not found")

    return success, not_found
