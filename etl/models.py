"""Pydantic models shared across ETL components."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Listing(BaseModel):
    id: int
    url: str = ""
    region: Optional[int] = None
    deal_type: str = ""
    rooms: Optional[int] = None
    area_total: Optional[float] = None
    floor: Optional[int] = None
    address: str = ""
    address_full: Optional[str] = None  # Full address from listing page
    seller_type: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    # Apartment details
    area_living: Optional[float] = None
    area_kitchen: Optional[float] = None
    balcony: Optional[bool] = None
    loggia: Optional[bool] = None
    renovation: Optional[str] = None
    rooms_layout: Optional[str] = None
    # House details
    house_year: Optional[int] = None
    house_material: Optional[str] = None
    house_series: Optional[str] = None
    house_has_elevator: Optional[bool] = None
    house_has_parking: Optional[bool] = None


class PricePoint(BaseModel):
    id: int
    seen_at: datetime = Field(default_factory=datetime.utcnow)
    price: float
