"""Mapper V2 - Strict validation, all fields required."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from etl.models_v2 import Listing, PricePoint, ListingValidationError

LOGGER = logging.getLogger(__name__)

_CANDIDATE_PATHS: List[tuple] = [
    ("data", "offersSerialized"),
    ("data", "items"),
    ("data", "offers"),
    ("result", "offers"),
    ("result", "items"),
    ("offersSerialized",),
]


def extract_offers(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the offer list from a response."""
    for path in _CANDIDATE_PATHS:
        current: Any = resp
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                break
        else:
            if isinstance(current, list):
                return current
    return []


def _get_required_field(offer: Dict[str, Any], field_name: str, *alternative_names: str) -> Any:
    """Get required field or raise error.
    
    Parameters
    ----------
    offer : dict
        Offer data
    field_name : str
        Primary field name
    *alternative_names : str
        Alternative field names to try
        
    Returns
    -------
    Any
        Field value
        
    Raises
    ------
    ListingValidationError
        If field is missing or None
    """
    # Try primary name
    value = offer.get(field_name)
    if value is not None:
        return value
    
    # Try alternatives
    for alt_name in alternative_names:
        value = offer.get(alt_name)
        if value is not None:
            return value
    
    # Field is required but missing
    offer_id = offer.get("offerId") or offer.get("id") or "unknown"
    raise ListingValidationError(
        f"Required field '{field_name}' missing in offer {offer_id}"
    )


def _extract_id(offer: Dict[str, Any]) -> int:
    """Extract offer ID (REQUIRED)."""
    value = _get_required_field(offer, "offerId", "id")
    return int(value)


def _extract_url(offer: Dict[str, Any]) -> str:
    """Extract URL (REQUIRED)."""
    value = _get_required_field(offer, "seoUrl", "absoluteUrl", "url")
    url = str(value)
    
    # Ensure it's a full URL
    if not url.startswith("http"):
        url = f"https://www.cian.ru{url}" if url.startswith("/") else f"https://www.cian.ru/sale/flat/{url}/"
    
    return url


def _extract_region(offer: Dict[str, Any]) -> int:
    """Extract region (REQUIRED)."""
    value = _get_required_field(offer, "region", "regionId")
    return int(value)


def _extract_address(offer: Dict[str, Any]) -> str:
    """Extract address (REQUIRED)."""
    value = _get_required_field(offer, "address", "geoLabel", "location")
    return str(value).strip()


def _extract_coordinates(offer: Dict[str, Any]) -> tuple[float, float]:
    """Extract lat/lon coordinates (REQUIRED).
    
    Returns
    -------
    tuple[float, float]
        (latitude, longitude)
    """
    geo = offer.get("geo") or {}
    coords = geo.get("coordinates") or {}
    
    lat = coords.get("lat") or coords.get("LAT") or coords.get("latitude")
    lon = coords.get("lng") or coords.get("LON") or coords.get("longitude")
    
    if lat is None or lon is None:
        offer_id = offer.get("offerId") or "unknown"
        raise ListingValidationError(f"Coordinates missing in offer {offer_id}")
    
    return float(lat), float(lon)


def _extract_deal_type(offer: Dict[str, Any]) -> str:
    """Extract deal type (REQUIRED)."""
    value = _get_required_field(offer, "operationName", "dealType", "deal_type")
    deal_type = str(value).lower()
    
    # Normalize
    if deal_type in ("sale", "продажа"):
        return "sale"
    elif deal_type in ("rent", "аренда"):
        return "rent"
    
    return deal_type


def _extract_rooms(offer: Dict[str, Any]) -> int:
    """Extract number of rooms (REQUIRED)."""
    value = _get_required_field(offer, "rooms", "roomsCount", "roomsCountTotal")
    return int(value)


def _extract_area(offer: Dict[str, Any]) -> float:
    """Extract total area (REQUIRED)."""
    # Try multiple field names
    for key in ("totalSquare", "spaceTotal", "areaTotal"):
        if key in offer:
            value = offer[key]
            if value is not None:
                return float(value)
    
    # Try nested structure
    area = offer.get("area")
    if isinstance(area, dict):
        value = area.get("value") or area.get("total")
        if value is not None:
            return float(value)
    elif area is not None:
        return float(area)
    
    # Required field missing
    offer_id = offer.get("offerId") or "unknown"
    raise ListingValidationError(f"Area missing in offer {offer_id}")


def _extract_floor(offer: Dict[str, Any]) -> int:
    """Extract floor number (REQUIRED)."""
    value = _get_required_field(offer, "floor", "floorNumber")
    floor = int(value)
    
    # Validate floor is reasonable
    if floor < 1:
        raise ListingValidationError(f"Invalid floor: {floor}")
    
    return floor


def _extract_seller_type(offer: Dict[str, Any]) -> str:
    """Extract seller type (REQUIRED)."""
    value = _get_required_field(offer, "userType", "ownerType", "sellerName", "sellerType")
    return str(value).strip()


def _extract_price(offer: Dict[str, Any]) -> float:
    """Extract price (REQUIRED)."""
    price = offer.get("price")
    
    if isinstance(price, dict):
        for key in ("value", "rub", "amount"):
            if price.get(key) is not None:
                return float(price[key])
    elif price is not None:
        return float(price)
    
    # Required field missing
    offer_id = offer.get("offerId") or "unknown"
    raise ListingValidationError(f"Price missing in offer {offer_id}")


def to_listing(offer: Dict[str, Any]) -> Listing:
    """Map raw offer to Listing model with strict validation.
    
    Parameters
    ----------
    offer : dict
        Raw offer data from CIAN API
        
    Returns
    -------
    Listing
        Validated listing model
        
    Raises
    ------
    ListingValidationError
        If any required field is missing or invalid
    """
    try:
        lat, lon = _extract_coordinates(offer)
        
        return Listing(
            id=_extract_id(offer),
            url=_extract_url(offer),
            region=_extract_region(offer),
            address=_extract_address(offer),
            lat=lat,
            lon=lon,
            deal_type=_extract_deal_type(offer),
            rooms=_extract_rooms(offer),
            area_total=_extract_area(offer),
            floor=_extract_floor(offer),
            seller_type=_extract_seller_type(offer),
        )
    except (ValueError, TypeError, KeyError) as e:
        offer_id = offer.get("offerId") or offer.get("id") or "unknown"
        raise ListingValidationError(f"Failed to map offer {offer_id}: {e}") from e


def to_price(offer: Dict[str, Any]) -> PricePoint:
    """Extract price point with validation.
    
    Parameters
    ----------
    offer : dict
        Raw offer data
        
    Returns
    -------
    PricePoint
        Validated price point
        
    Raises
    ------
    ListingValidationError
        If price is missing or invalid
    """
    try:
        return PricePoint(
            id=_extract_id(offer),
            price=_extract_price(offer),
        )
    except (ValueError, TypeError) as e:
        offer_id = offer.get("offerId") or "unknown"
        raise ListingValidationError(f"Failed to extract price from offer {offer_id}: {e}") from e


def validate_and_map_offers(offers: List[Dict[str, Any]]) -> tuple[List[Listing], List[PricePoint], List[str]]:
    """Validate and map offers, collecting errors.
    
    Parameters
    ----------
    offers : list
        Raw offers from CIAN API
        
    Returns
    -------
    tuple
        (valid_listings, valid_prices, errors)
    """
    valid_listings = []
    valid_prices = []
    errors = []
    
    for i, offer in enumerate(offers):
        try:
            listing = to_listing(offer)
            price = to_price(offer)
            
            valid_listings.append(listing)
            valid_prices.append(price)
            
        except ListingValidationError as e:
            errors.append(f"Offer {i}: {e}")
            LOGGER.warning(f"Skipping invalid offer {i}: {e}")
        except Exception as e:
            errors.append(f"Offer {i}: Unexpected error: {e}")
            LOGGER.error(f"Unexpected error mapping offer {i}: {e}", exc_info=True)
    
    LOGGER.info(
        f"Mapped {len(valid_listings)}/{len(offers)} offers "
        f"({len(errors)} errors)"
    )
    
    return valid_listings, valid_prices, errors

