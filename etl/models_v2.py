"""Pydantic models V2 - All fields required for data quality."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, validator


class Listing(BaseModel):
    """Listing model with strict validation - all fields required."""
    
    # Core identification (REQUIRED)
    id: int = Field(..., description="CIAN offer ID")
    url: str = Field(..., description="Full CIAN URL", min_length=10)
    
    # Location (REQUIRED)
    region: int = Field(..., description="Region ID (1=Moscow)", gt=0)
    address: str = Field(..., description="Full address", min_length=5)
    lat: float = Field(..., description="Latitude", ge=-90, le=90)
    lon: float = Field(..., description="Longitude", ge=-180, le=180)
    
    # Property details (REQUIRED)
    deal_type: Literal["sale", "rent"] = Field(..., description="Deal type")
    rooms: int = Field(..., description="Number of rooms (0=studio)", ge=0, le=10)
    area_total: float = Field(..., description="Total area in m²", gt=0)
    floor: int = Field(..., description="Floor number", ge=1)
    
    # Seller info (REQUIRED)
    seller_type: str = Field(..., description="Seller type: owner/agent/developer", min_length=1)
    
    # Temporal tracking (auto-filled)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    
    @validator('url')
    def validate_url(cls, v):
        """Ensure URL is from CIAN."""
        if not v.startswith('https://www.cian.ru/'):
            raise ValueError('URL must be from cian.ru')
        return v
    
    @validator('seller_type')
    def normalize_seller_type(cls, v):
        """Normalize seller type."""
        v = v.lower()
        if v in ('owner', 'homeowner', 'собственник'):
            return 'owner'
        elif v in ('agent', 'realtor', 'агент', 'риелтор'):
            return 'agent'
        elif v in ('developer', 'builder', 'застройщик'):
            return 'developer'
        return v


class PricePoint(BaseModel):
    """Price point with strict validation."""
    
    id: int = Field(..., description="Listing ID")
    seen_at: datetime = Field(default_factory=datetime.utcnow)
    price: float = Field(..., description="Price in rubles", gt=0)
    
    @validator('price')
    def validate_price(cls, v):
        """Ensure price is reasonable."""
        if v < 100000:  # Less than 100k rubles
            raise ValueError('Price too low')
        if v > 1000000000:  # More than 1 billion
            raise ValueError('Price too high')
        return v


class ListingValidationError(Exception):
    """Raised when listing data is invalid."""
    pass

