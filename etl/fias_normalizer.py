"""Address normalization using DaData Suggest API (primary) with FIAS fallback.

DaData Suggest API is FREE (10k requests/day) and works reliably.
FIAS Public API (fias.nalog.ru) is blocked from most VPS providers.
DaData Clean API requires paid subscription.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Dict, Any

import re
import requests

LOGGER = logging.getLogger(__name__)


def _clean_address_for_dadata(address: str) -> str:
    """Clean address by removing district info that confuses DaData Suggest API.

    DaData Suggest works better with simple "City, Street, House" format.
    It doesn't understand Moscow districts like "ЮЗАО, р-н Северное Бутово".
    """
    if not address:
        return address

    # Remove округ (ЮЗАО, ВАО, СВАО, ЦАО, НАО, ТАО, etc.) with optional full name in parentheses
    address = re.sub(r',\s*[СЗЮВЦНТ]+АО\s*(?:\([^)]+\))?', '', address)

    # Remove standalone parentheses with district names
    address = re.sub(r'\s*\([^)]*(?:московский|округ)[^)]*\)', '', address, flags=re.IGNORECASE)

    # Remove "поселение" and "поселок" with names
    address = re.sub(r',\s*\w+\s+поселение', '', address)
    address = re.sub(r',\s*\w+\s+поселок', '', address)

    # Remove район (р-н ...)
    address = re.sub(r',\s*р-н\s+[^,]+', '', address)

    # Remove ЖК names (жилой комплекс, ЖК ...)
    address = re.sub(r',\s*(?:ЖК|жилой комплекс)\s+[^,]+', '', address, flags=re.IGNORECASE)
    address = re.sub(r',\s*\w+\s+жилой\s+комплекс', '', address, flags=re.IGNORECASE)

    # Remove "Резиденсез" and similar marketing names
    address = re.sub(r',\s*\w+\s+(?:Резиденс|Резиденсез|Парк|Сити|Хаус)[^,]*', '', address, flags=re.IGNORECASE)

    # Remove multiple street names (keep only the first one with house number)
    # Pattern: "ул. X, шоссе Y, ул. Z" -> keep first with number
    parts = address.split(',')
    if len(parts) > 2:
        # Find the part with house number
        for i, part in enumerate(parts):
            if re.search(r'\d+', part) and re.search(r'(ул\.|пер\.|просп\.|пр-т|шоссе|наб\.|бульв\.)', part, re.IGNORECASE):
                # Keep city + this part
                address = parts[0] + ',' + part
                break

    # Clean up double commas and extra spaces
    address = re.sub(r',\s*,', ',', address)
    address = re.sub(r'\s+', ' ', address).strip()
    address = address.rstrip(',').strip()

    return address

# DaData Suggest API endpoint (FREE, 10k/day)
DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"

# FIAS Public API as fallback (usually blocked from VPS)
FIAS_PUBLIC_AVAILABLE = False
FIAS_USE_LIBRARY = False
try:
    from fias_public_api import get_token_sync, SyncFPA
    FIAS_PUBLIC_AVAILABLE = True
    FIAS_USE_LIBRARY = True
except ImportError:
    try:
        from etl.fias_public_api import normalize_address_fias_direct
        FIAS_PUBLIC_AVAILABLE = True
        FIAS_USE_LIBRARY = False
    except ImportError:
        pass


def normalize_address_dadata_suggest(address: str) -> Optional[Dict[str, Any]]:
    """Normalize address using FREE DaData Suggest API (10k requests/day).

    Parameters
    ----------
    address : str
        Raw address string to normalize

    Returns
    -------
    dict or None
        Dictionary with normalized address data including coordinates:
        - fias_address: Normalized address string
        - fias_id: FIAS GUID
        - postal_code: 6-digit postal code
        - quality_code: 0 if FIAS found, 1 otherwise
        - lat: Latitude (float)
        - lon: Longitude (float)
    """
    api_key = os.getenv("DADATA_API_KEY")
    if not api_key:
        LOGGER.debug("DADATA_API_KEY not configured")
        return None

    if not address or len(address.strip()) < 5:
        return None

    # Clean address for better DaData recognition
    cleaned_address = _clean_address_for_dadata(address.strip())

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            DADATA_SUGGEST_URL,
            headers=headers,
            json={"query": cleaned_address, "count": 1},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            suggestions = data.get("suggestions", [])

            if suggestions:
                s = suggestions[0]
                d = s.get("data", {})

                fias_address = s.get("value")
                fias_id = d.get("fias_id")

                # Extract coordinates
                lat = None
                lon = None
                if d.get("geo_lat"):
                    try:
                        lat = float(d["geo_lat"])
                    except (ValueError, TypeError):
                        pass
                if d.get("geo_lon"):
                    try:
                        lon = float(d["geo_lon"])
                    except (ValueError, TypeError):
                        pass

                return {
                    "fias_address": fias_address,
                    "fias_id": fias_id,
                    "postal_code": d.get("postal_code"),
                    "quality_code": 0 if fias_id else 1,
                    "lat": lat,
                    "lon": lon,
                }
        elif response.status_code == 403:
            LOGGER.warning("DaData API returned 403 - check API key or daily limit")
        else:
            LOGGER.debug(f"DaData Suggest API returned {response.status_code}")

    except requests.exceptions.Timeout:
        LOGGER.debug(f"DaData Suggest API timeout for: {address[:50]}")
    except requests.exceptions.RequestException as e:
        LOGGER.debug(f"DaData Suggest API error: {e}")
    except Exception as e:
        LOGGER.debug(f"DaData Suggest failed: {e}")

    return None


def normalize_address_fias_public(address: str) -> Optional[Dict[str, Any]]:
    """Normalize address using free FIAS Public API.
    
    Parameters
    ----------
    address : str
        Raw address string to normalize
    
    Returns
    -------
    dict or None
        Dictionary with normalized address data, or None if fails
    """
    if not FIAS_PUBLIC_AVAILABLE:
        return None
    
    if not address or len(address.strip()) < 5:
        LOGGER.debug(f"Address too short: {address}")
        return None
    
    try:
        if FIAS_USE_LIBRARY:
            # Use library if available
            from fias_public_api import get_token_sync, SyncFPA
            
            # Get token (automatically obtained from public API)
            token = get_token_sync()
            api = SyncFPA(token)
            
            # Search for address
            results = api.search(address.strip())
            
            if not results or len(results) == 0:
                LOGGER.debug(f"No results found for address: {address}")
                return None
            
            # Take first result (most relevant)
            result = results[0]
            
            # Get details for more information
            object_id = result.get("id")
            if object_id:
                try:
                    details = api.details(object_id)
                    fias_id = details.get("fias_id") or details.get("guid")
                    full_address = details.get("address") or details.get("full_address") or result.get("address")
                except Exception:
                    # If details fail, use search result
                    fias_id = result.get("fias_id") or result.get("guid")
                    full_address = result.get("address")
            else:
                fias_id = result.get("fias_id") or result.get("guid")
                full_address = result.get("address")
            
            if not full_address:
                LOGGER.debug(f"No address found in result: {result}")
                return None
            
            # Quality code: 0 = exact match (if found), 1 = good match
            quality_code = 0 if object_id else 1
            
            return {
                "fias_address": full_address,
                "fias_id": fias_id,
                "postal_code": None,  # FIAS Public API doesn't provide postal code
                "quality_code": quality_code,
            }
        else:
            # Use direct implementation
            from etl.fias_public_api import normalize_address_fias_direct
            return normalize_address_fias_direct(address)
        
    except Exception as e:
        LOGGER.debug(f"FIAS Public API failed for '{address}': {e}")
        return None


def normalize_address(address: str, api_key: Optional[str] = None, secret: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Normalize address using DaData Suggest API (primary) or FIAS (fallback).

    DaData Suggest API is FREE (10k requests/day) and works reliably.
    FIAS Public API is used as fallback but is usually blocked from VPS.

    Parameters
    ----------
    address : str
        Raw address string to normalize
    api_key : str, optional
        Deprecated. Kept for backward compatibility.
    secret : str, optional
        Deprecated. Kept for backward compatibility.

    Returns
    -------
    dict or None
        Dictionary with normalized address data:
        - fias_address: Normalized address string
        - fias_id: FIAS GUID
        - postal_code: 6-digit postal code
        - quality_code: Address quality (0=exact, 1=good, 2-5=problems)
        - lat: Latitude (float, from DaData only)
        - lon: Longitude (float, from DaData only)
        Returns None if normalization fails
    """
    if not address or len(address.strip()) < 5:
        LOGGER.debug(f"Address too short: {address}")
        return None

    # PRIMARY: Try DaData Suggest API (FREE, 10k/day, works reliably)
    result = normalize_address_dadata_suggest(address)
    if result:
        LOGGER.debug(f"✅ Address normalized via DaData Suggest: {address[:50]}")
        return result

    # FALLBACK: Try FIAS Public API (usually blocked from VPS)
    result = normalize_address_fias_public(address)
    if result:
        LOGGER.debug(f"✅ Address normalized via FIAS Public API: {address[:50]}")
        return result

    LOGGER.warning(f"❌ Failed to normalize address: {address[:50]}")
    return None


def batch_normalize_addresses(addresses: list[str], api_key: Optional[str] = None, secret: Optional[str] = None) -> list[Optional[Dict[str, Any]]]:
    """Normalize multiple addresses sequentially using the FIAS Public API."""
    if not addresses:
        return []
    results: list[Optional[Dict[str, Any]]] = []
    for address in addresses:
        results.append(normalize_address(address))
    return results
