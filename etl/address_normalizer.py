"""Address normalization helpers using the public FIAS API."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from etl.fias_normalizer import normalize_address as normalize_fias

LOGGER = logging.getLogger(__name__)


@dataclass
class NormalizedAddress:
    """Normalized address with optional cadastral/geo metadata."""

    raw_address: str
    fias_address: Optional[str] = None
    fias_id: Optional[str] = None
    postal_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    house: Optional[str] = None
    flat: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    cadastral_number: Optional[str] = None
    qc: Optional[int] = None
    qc_complete: Optional[int] = None

    @property
    def is_valid(self) -> bool:
        """Return True when quality code indicates an exact/good match."""
        return self.qc is not None and self.qc <= 1


class AddressNormalizer:
    """Normalize addresses via the free FIAS public API."""

    def __init__(self) -> None:
        self.enabled = True

    def normalize(self, address: str) -> Optional[NormalizedAddress]:
        """Normalize a textual address using the FIAS API."""
        if not address or len(address.strip()) < 5:
            LOGGER.debug("Address too short to normalize: %s", address)
            return None

        fias_data = normalize_fias(address)
        if not fias_data:
            return None

        return NormalizedAddress(
            raw_address=address,
            fias_address=fias_data.get("fias_address"),
            fias_id=fias_data.get("fias_id"),
            postal_code=fias_data.get("postal_code"),
            qc=fias_data.get("quality_code"),
        )

    def geocode(self, latitude: float, longitude: float) -> Optional[NormalizedAddress]:
        """FIAS API does not support reverse geocoding; return None."""
        LOGGER.debug(
            "Reverse geocoding (%s, %s) is not supported without Dadata", latitude, longitude
        )
        return None


_normalizer: Optional[AddressNormalizer] = None


def get_normalizer() -> AddressNormalizer:
    """Get singleton AddressNormalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = AddressNormalizer()
    return _normalizer


def normalize_address(address: str) -> Optional[NormalizedAddress]:
    """Convenience wrapper around the singleton normalizer."""
    return get_normalizer().normalize(address)


def geocode_coords(lat: float, lon: float) -> Optional[NormalizedAddress]:
    """Convenience wrapper for reverse geocoding (currently unsupported)."""
    return get_normalizer().geocode(lat, lon)
