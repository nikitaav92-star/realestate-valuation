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
    seller_type: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


class PricePoint(BaseModel):
    id: int
    seen_at: datetime = Field(default_factory=datetime.utcnow)
    price: float
