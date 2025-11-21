"""Helpers that convert raw CIAN payloads into internal models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from etl.models import Listing, PricePoint

_CANDIDATE_PATHS: List[Iterable[str]] = [
    ("data", "offersSerialized"),
    ("data", "items"),
    ("data", "offers"),
    ("result", "offers"),
    ("result", "items"),
    ("offersSerialized",),
]


def extract_offers(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the offer list from a response, tolerating schema shifts."""
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


def _get_offer_id(offer: Dict[str, Any]) -> int:
    for key in ("offerId", "id"):
        value = offer.get(key)
        if value:
            return int(value)
    raise ValueError("offer id is missing in payload")


def _get_geo_coordinate(offer: Dict[str, Any], key: str) -> Optional[float]:
    geo = offer.get("geo") or {}
    coords = geo.get("coordinates") or {}
    value = coords.get(key) or coords.get(key.upper())
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_area(offer: Dict[str, Any]) -> Optional[float]:
    for key in ("totalSquare", "spaceTotal"):
        if key in offer:
            return _safe_float(offer.get(key))
    area = offer.get("areaTotal") or offer.get("area") or {}
    if isinstance(area, dict):
        return _safe_float(area.get("value") or area.get("total"))
    return _safe_float(area)


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_price(offer: Dict[str, Any]) -> float:
    price = offer.get("price")
    if isinstance(price, dict):
        for key in ("value", "rub", "amount"):
            if price.get(key) is not None:
                return float(price[key])
    if price is not None:
        return float(price)
    return 0.0


def _extract_rooms(offer: Dict[str, Any]) -> Optional[int]:
    return _safe_int(offer.get("rooms") or offer.get("roomsCount") or offer.get("roomsCountTotal"))


def _extract_floor(offer: Dict[str, Any]) -> Optional[int]:
    return _safe_int(offer.get("floor") or offer.get("floorNumber"))


def _extract_seen_at(offer: Dict[str, Any]) -> datetime:
    candidates = [
        offer.get("addedTimestamp"),
        offer.get("creationDate"),
        offer.get("creationTs"),
    ]
    for value in candidates:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(
                    tzinfo=None
                )
            except ValueError:
                continue
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_newbuilding(offer: Dict[str, Any]) -> bool:
    """Check if offer is a newbuilding (should be excluded)."""
    # Check building_status field
    building_status = offer.get("buildingStatus") or offer.get("building_status") or ""
    if isinstance(building_status, str):
        building_status = building_status.lower()
        if building_status in ("new", "newbuilding", "новостройка", "новострой"):
            return True
    
    # Check category field
    category = offer.get("category") or ""
    if isinstance(category, str):
        category = category.lower()
        if "newbuilding" in category or "новострой" in category:
            return True
    
    # Check URL for newbuilding indicators
    url = str(offer.get("seoUrl") or offer.get("absoluteUrl") or offer.get("url") or "")
    url_lower = url.lower()
    if "/newbuilding/" in url_lower or "/new/" in url_lower:
        return True
    
    # Check houseType or objectType
    house_type = offer.get("houseType") or offer.get("house_type") or offer.get("objectType") or ""
    if isinstance(house_type, str):
        house_type = house_type.lower()
        if "newbuilding" in house_type or "новострой" in house_type:
            return True
    
    return False


def _is_apartment(offer: Dict[str, Any]) -> bool:
    """Check if offer is an apartment (апартаменты) - should be excluded."""
    # Check property_type field
    property_type = offer.get("propertyType") or offer.get("property_type") or ""
    if isinstance(property_type, str):
        property_type = property_type.lower()
        if "apartment" in property_type or "апартамент" in property_type:
            return True
    
    # Check URL for apartment indicators
    url = str(offer.get("seoUrl") or offer.get("absoluteUrl") or offer.get("url") or "")
    url_lower = url.lower()
    if "/apartment/" in url_lower or "/апартамент" in url_lower:
        return True
    
    # Check title/description for apartment indicators
    title = str(offer.get("title") or offer.get("name") or "").lower()
    description = str(offer.get("description") or offer.get("text") or "").lower()
    
    apartment_keywords = [
        "апартамент", "apartment", "апартаменты", "apartments",
        "коммерческая недвижимость", "коммерческая"
    ]
    
    text_to_check = f"{title} {description}"
    for keyword in apartment_keywords:
        if keyword in text_to_check:
            return True
    
    return False


def _is_apartment_share(offer: Dict[str, Any]) -> bool:
    """Check if offer is an apartment share (доля квартиры) - should be excluded."""
    # Check area - shares are usually < 20 m²
    area_total = _get_area(offer)
    if area_total is not None and area_total < 20:
        return True
    
    # Check title/description for share indicators
    title = str(offer.get("title") or offer.get("name") or "").lower()
    description = str(offer.get("description") or offer.get("text") or "").lower()
    
    share_keywords = [
        "доля", "доли", "долевая", "долевое", "долевой",
        "share", "shares", "часть квартиры", "часть кв",
        "1/2", "1/3", "1/4", "2/3", "3/4", "1/5", "доля в",
        "продается доля", "продаю долю"
    ]
    
    text_to_check = f"{title} {description}"
    for keyword in share_keywords:
        if keyword in text_to_check:
            return True
    
    # Check URL for share indicators
    url = str(offer.get("seoUrl") or offer.get("absoluteUrl") or offer.get("url") or "")
    url_lower = url.lower()
    if "/share/" in url_lower or "/доля" in url_lower:
        return True
    
    # Check propertyType or objectType
    property_type = offer.get("propertyType") or offer.get("property_type") or ""
    if isinstance(property_type, str):
        property_type = property_type.lower()
        if "share" in property_type or "доля" in property_type:
            return True
    
    # Check roomType - sometimes shares are marked differently
    room_type = offer.get("roomType") or offer.get("room_type") or ""
    if isinstance(room_type, str):
        room_type = room_type.lower()
        if "share" in room_type or "доля" in room_type:
            return True
    
    # Check address for share indicators
    address = str(offer.get("address") or offer.get("geoLabel") or "").lower()
    if "доля" in address or "долевая" in address:
        return True
    
    return False


def to_listing(offer: Dict[str, Any]) -> Listing:
    """Map a raw offer dict to Listing.
    
    Performs validation checks:
    - Excludes newbuildings (only secondary market)
    - Excludes apartment shares (доли квартир)
    - Excludes apartments (апартаменты) - only flats allowed
    """
    # Filter out newbuildings - only secondary market allowed
    if _is_newbuilding(offer):
        raise ValueError("Newbuilding detected - should be excluded")
    
    # Filter out apartment shares - only full apartments allowed
    if _is_apartment_share(offer):
        raise ValueError("Apartment share detected - should be excluded")
    
    # Filter out apartments (апартаменты) - only flats allowed
    if _is_apartment(offer):
        raise ValueError("Apartment detected - should be excluded")
    
    region = offer.get("region") or offer.get("regionId")
    if region is not None:
        region = _safe_int(region)
    
    # Get area (already validated by _is_apartment_share)
    area_total = _get_area(offer)
    
    return Listing(
        id=_get_offer_id(offer),
        url=str(offer.get("seoUrl") or offer.get("absoluteUrl") or offer.get("url") or ""),
        region=region,
        deal_type=str(offer.get("operationName") or offer.get("dealType") or ""),
        rooms=_extract_rooms(offer),
        area_total=area_total,  # Already validated by _is_apartment_share
        floor=_extract_floor(offer),
        address=str(offer.get("address") or offer.get("geoLabel") or ""),
        seller_type=str(offer.get("userType") or offer.get("ownerType") or offer.get("sellerName") or ""),
        lat=_get_geo_coordinate(offer, "lat"),
        lon=_get_geo_coordinate(offer, "lng"),
    )


def to_price(offer: Dict[str, Any]) -> PricePoint:
    """Extract price information for the offer."""
    return PricePoint(
        id=_get_offer_id(offer),
        price=_extract_price(offer),
        seen_at=_extract_seen_at(offer),
    )
