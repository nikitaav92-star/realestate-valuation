"""
Address normalization and cadastral number enrichment using FIAS/Dadata.

Features:
- Normalize addresses to FIAS standard
- Get cadastral numbers for buildings
- Geocode addresses to coordinates
- Enrich with FIAS GUID
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

LOGGER = logging.getLogger(__name__)

DADATA_API_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
DADATA_CLEAN_URL = "https://cleaner.dadata.ru/api/v1/clean/address"


@dataclass
class NormalizedAddress:
    """Normalized address with FIAS and cadastral data."""
    
    # Original
    raw_address: str
    
    # FIAS normalized
    fias_address: Optional[str] = None  # Полный адрес по ФИАС
    fias_id: Optional[str] = None       # GUID дома в ФИАС
    
    # Components
    postal_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    house: Optional[str] = None
    flat: Optional[str] = None
    
    # Geocoding
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Cadastral
    cadastral_number: Optional[str] = None  # Кадастровый номер здания
    
    # Quality
    qc: Optional[int] = None  # Quality code: 0=exact, 1=ok, 2-5=problems
    qc_complete: Optional[int] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if address is valid (qc <= 1)."""
        return self.qc is not None and self.qc <= 1


class AddressNormalizer:
    """Normalize addresses using Dadata API."""
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DADATA_API_KEY")
        self.secret_key = secret_key or os.getenv("DADATA_SECRET_KEY")
        
        if not self.api_key or not self.secret_key:
            LOGGER.warning("Dadata API keys not configured. Address normalization will be skipped.")
            self.enabled = False
        else:
            self.enabled = True
            
    def _headers(self, use_secret: bool = False) -> dict:
        """Get HTTP headers for Dadata API."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if use_secret:
            headers["Authorization"] = f"Token {self.api_key}"
            headers["X-Secret"] = self.secret_key
        else:
            headers["Authorization"] = f"Token {self.api_key}"
        return headers
    
    def normalize(self, address: str) -> Optional[NormalizedAddress]:
        """
        Normalize address using Dadata API.
        
        Args:
            address: Raw address string (e.g., "Москва, ул. Ленина, 10")
            
        Returns:
            NormalizedAddress with FIAS data and cadastral number, or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            # Clean address using Dadata
            response = httpx.post(
                DADATA_CLEAN_URL,
                headers=self._headers(use_secret=True),
                json=[address],
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()[0]
            
            # Extract data
            result = NormalizedAddress(
                raw_address=address,
                fias_address=data.get("result"),
                fias_id=data.get("fias_id"),
                postal_code=data.get("postal_code"),
                region=data.get("region"),
                city=data.get("city") or data.get("settlement"),
                street=data.get("street"),
                house=data.get("house"),
                flat=data.get("flat"),
                latitude=float(data["geo_lat"]) if data.get("geo_lat") else None,
                longitude=float(data["geo_lon"]) if data.get("geo_lon") else None,
                cadastral_number=data.get("cadastral_number"),
                qc=int(data.get("qc", 99)),
                qc_complete=int(data.get("qc_complete", 99)),
            )
            
            LOGGER.debug(f"Normalized: {address} -> {result.fias_address} (qc={result.qc})")
            return result
            
        except Exception as e:
            LOGGER.error(f"Failed to normalize address {address}: {e}")
            return None
    
    def geocode(self, latitude: float, longitude: float) -> Optional[NormalizedAddress]:
        """
        Reverse geocode coordinates to normalized address.
        
        Args:
            latitude: Latitude (e.g., 55.755826)
            longitude: Longitude (e.g., 37.6173)
            
        Returns:
            NormalizedAddress or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            # Geolocate using Dadata
            response = httpx.post(
                f"{DADATA_API_URL}/geolocate/address",
                headers=self._headers(),
                json={"lat": latitude, "lon": longitude, "radius_meters": 100},
                timeout=10.0,
            )
            response.raise_for_status()
            
            suggestions = response.json().get("suggestions", [])
            if not suggestions:
                LOGGER.warning(f"No address found for coordinates ({latitude}, {longitude})")
                return None
                
            data = suggestions[0]["data"]
            
            result = NormalizedAddress(
                raw_address=f"{latitude},{longitude}",
                fias_address=suggestions[0]["value"],
                fias_id=data.get("fias_id"),
                postal_code=data.get("postal_code"),
                region=data.get("region"),
                city=data.get("city") or data.get("settlement"),
                street=data.get("street"),
                house=data.get("house"),
                latitude=latitude,
                longitude=longitude,
                cadastral_number=data.get("cadastral_number"),
                qc=int(data.get("qc", 99)),
            )
            
            LOGGER.debug(f"Geocoded: ({latitude}, {longitude}) -> {result.fias_address}")
            return result
            
        except Exception as e:
            LOGGER.error(f"Failed to geocode ({latitude}, {longitude}): {e}")
            return None


# Singleton instance
_normalizer: Optional[AddressNormalizer] = None


def get_normalizer() -> AddressNormalizer:
    """Get singleton AddressNormalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = AddressNormalizer()
    return _normalizer


def normalize_address(address: str) -> Optional[NormalizedAddress]:
    """Convenience function to normalize address."""
    return get_normalizer().normalize(address)


def geocode_coords(lat: float, lon: float) -> Optional[NormalizedAddress]:
    """Convenience function to geocode coordinates."""
    return get_normalizer().geocode(lat, lon)
