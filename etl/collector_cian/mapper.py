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


def to_listing(offer: Dict[str, Any]) -> Listing:
    """Map a raw offer dict to Listing."""
    region = offer.get("region") or offer.get("regionId")
    if region is not None:
        region = _safe_int(region)
    return Listing(
        id=_get_offer_id(offer),
        url=str(offer.get("seoUrl") or offer.get("absoluteUrl") or offer.get("url") or ""),
        region=region,
        deal_type=str(offer.get("operationName") or offer.get("dealType") or ""),
        rooms=_extract_rooms(offer),
        area_total=_get_area(offer),
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
