"""Geocoding module using DaData API for address normalization and coordinates."""
from __future__ import annotations

import os
import logging
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

import requests

LOGGER = logging.getLogger(__name__)

# DaData API endpoints
DADATA_CLEAN_URL = "https://cleaner.dadata.ru/api/v1/clean/address"
DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"

# Rate limiting
DADATA_REQUESTS_PER_SECOND = 10
_last_request_time = 0.0


@dataclass
class GeocodingResult:
    """Result of geocoding operation."""
    lat: Optional[float] = None
    lon: Optional[float] = None
    fias_id: Optional[str] = None
    fias_address: Optional[str] = None
    postal_code: Optional[str] = None
    quality_code: Optional[int] = None
    district: Optional[str] = None
    city_district: Optional[str] = None
    region: Optional[str] = None

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lon is not None


def _get_dadata_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Get DaData API credentials from environment."""
    api_key = os.getenv("DADATA_API_KEY")
    secret_key = os.getenv("DADATA_SECRET_KEY")
    return api_key, secret_key


def _rate_limit():
    """Simple rate limiting for DaData API."""
    global _last_request_time
    min_interval = 1.0 / DADATA_REQUESTS_PER_SECOND
    elapsed = time.time() - _last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request_time = time.time()


def geocode_address(address: str) -> Optional[GeocodingResult]:
    """
    Geocode an address using DaData API.

    Uses the "clean" API endpoint which normalizes the address
    and returns coordinates, FIAS data, and quality metrics.

    Args:
        address: Address string to geocode (e.g., "Москва, ул. Тверская, 1")

    Returns:
        GeocodingResult with coordinates and metadata, or None if failed
    """
    api_key, secret_key = _get_dadata_credentials()

    if not api_key or not secret_key:
        LOGGER.warning("DaData credentials not configured. Set DADATA_API_KEY and DADATA_SECRET_KEY")
        return None

    _rate_limit()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {api_key}",
        "X-Secret": secret_key,
    }

    try:
        response = requests.post(
            DADATA_CLEAN_URL,
            headers=headers,
            json=[address],
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        if not data or len(data) == 0:
            LOGGER.debug(f"Empty response for address: {address[:50]}...")
            return None

        result_data = data[0]

        # Extract coordinates
        lat = result_data.get("geo_lat")
        lon = result_data.get("geo_lon")

        # Parse quality code (0 = exact match, higher = worse)
        qc = result_data.get("qc", 10)

        result = GeocodingResult(
            lat=float(lat) if lat else None,
            lon=float(lon) if lon else None,
            fias_id=result_data.get("fias_id"),
            fias_address=result_data.get("result"),
            postal_code=result_data.get("postal_code"),
            quality_code=int(qc) if qc is not None else None,
            district=result_data.get("city_district"),
            city_district=result_data.get("city_district_with_type"),
            region=result_data.get("region_with_type"),
        )

        if result.has_coordinates:
            LOGGER.debug(f"✅ Geocoded: {address[:50]}... -> ({result.lat}, {result.lon})")
        else:
            LOGGER.debug(f"⚠️ No coordinates for: {address[:50]}...")

        return result

    except requests.exceptions.RequestException as e:
        LOGGER.warning(f"DaData request failed: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        LOGGER.warning(f"DaData response parsing failed: {e}")
        return None


def geocode_addresses_batch(addresses: list[str], batch_size: int = 10) -> list[Optional[GeocodingResult]]:
    """
    Geocode multiple addresses in batches.

    DaData supports up to 10 addresses per request in batch mode.

    Args:
        addresses: List of address strings
        batch_size: Number of addresses per batch (max 10)

    Returns:
        List of GeocodingResult (same order as input), None for failed addresses
    """
    api_key, secret_key = _get_dadata_credentials()

    if not api_key or not secret_key:
        LOGGER.warning("DaData credentials not configured")
        return [None] * len(addresses)

    batch_size = min(batch_size, 10)  # DaData limit
    results = []

    for i in range(0, len(addresses), batch_size):
        batch = addresses[i:i + batch_size]

        _rate_limit()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {api_key}",
            "X-Secret": secret_key,
        }

        try:
            response = requests.post(
                DADATA_CLEAN_URL,
                headers=headers,
                json=batch,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            for j, result_data in enumerate(data):
                if not result_data:
                    results.append(None)
                    continue

                lat = result_data.get("geo_lat")
                lon = result_data.get("geo_lon")
                qc = result_data.get("qc", 10)

                result = GeocodingResult(
                    lat=float(lat) if lat else None,
                    lon=float(lon) if lon else None,
                    fias_id=result_data.get("fias_id"),
                    fias_address=result_data.get("result"),
                    postal_code=result_data.get("postal_code"),
                    quality_code=int(qc) if qc is not None else None,
                    district=result_data.get("city_district"),
                    city_district=result_data.get("city_district_with_type"),
                    region=result_data.get("region_with_type"),
                )
                results.append(result)

            LOGGER.info(f"Geocoded batch {i//batch_size + 1}: {len(batch)} addresses")

        except Exception as e:
            LOGGER.warning(f"Batch geocoding failed: {e}")
            results.extend([None] * len(batch))

    return results


def update_listing_coordinates(
    conn,
    listing_id: int,
    geocoding_result: GeocodingResult
) -> bool:
    """
    Update listing with geocoding results.

    Args:
        conn: Database connection
        listing_id: Listing ID to update
        geocoding_result: Geocoding result with coordinates and metadata

    Returns:
        True if updated, False otherwise
    """
    if not geocoding_result or not geocoding_result.has_coordinates:
        return False

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE listings
            SET
                lat = %(lat)s,
                lon = %(lon)s,
                fias_id = %(fias_id)s,
                fias_address = %(fias_address)s,
                postal_code = %(postal_code)s,
                address_quality_code = %(quality_code)s
            WHERE id = %(listing_id)s
            AND (lat IS NULL OR lon IS NULL);
            """,
            {
                "listing_id": listing_id,
                "lat": geocoding_result.lat,
                "lon": geocoding_result.lon,
                "fias_id": geocoding_result.fias_id,
                "fias_address": geocoding_result.fias_address,
                "postal_code": geocoding_result.postal_code,
                "quality_code": geocoding_result.quality_code,
            }
        )
        return cur.rowcount > 0


def geocode_listings_without_coordinates(conn, limit: int = 100) -> Tuple[int, int]:
    """
    Geocode listings that don't have coordinates yet.

    Args:
        conn: Database connection
        limit: Maximum number of listings to process

    Returns:
        Tuple of (success_count, failed_count)
    """
    # Get listings without coordinates
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, COALESCE(address_full, address) as address
            FROM listings
            WHERE (lat IS NULL OR lon IS NULL)
            AND (address IS NOT NULL OR address_full IS NOT NULL)
            LIMIT %s;
            """,
            (limit,)
        )
        listings = cur.fetchall()

    if not listings:
        LOGGER.info("No listings need geocoding")
        return 0, 0

    LOGGER.info(f"Geocoding {len(listings)} listings...")

    success = 0
    failed = 0

    # Process one by one (batch API requires different format)
    for i, (listing_id, address) in enumerate(listings):
        try:
            geocoding_result = geocode_address(address)
            if update_listing_coordinates(conn, listing_id, geocoding_result):
                success += 1
                if success % 50 == 0:
                    LOGGER.info(f"Progress: {success} geocoded, {failed} failed")
            else:
                failed += 1
        except Exception as e:
            LOGGER.warning(f"Failed to geocode listing {listing_id}: {e}")
            failed += 1

    conn.commit()
    LOGGER.info(f"Geocoding complete: {success} success, {failed} failed")

    return success, failed
