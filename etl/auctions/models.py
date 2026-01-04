"""
Pydantic models for auction lots.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class AuctionSource(str, Enum):
    """Auction source types."""
    FSSP = "fssp"                # ФССП - торги приставов
    BANKRUPT = "bankrupt"        # Банкротство (Федресурс, lot-online)
    BANK_PLEDGE = "bank_pledge"  # Залоговое имущество банков
    DGI_MOSCOW = "dgi_moscow"    # ДГИ Москвы


class AuctionStatus(str, Enum):
    """Auction status."""
    ANNOUNCED = "announced"      # Объявлен
    ACTIVE = "active"            # Идут торги
    COMPLETED = "completed"      # Завершен (продан)
    FAILED = "failed"            # Не состоялся
    CANCELLED = "cancelled"      # Отменен


class PropertyType(str, Enum):
    """Property type."""
    APARTMENT = "apartment"      # Квартира
    ROOM = "room"                # Комната
    HOUSE = "house"              # Дом
    LAND = "land"                # Земельный участок
    COMMERCIAL = "commercial"    # Коммерческая недвижимость
    PARKING = "parking"          # Машиноместо
    OTHER = "other"              # Прочее


class AuctionLot(BaseModel):
    """Main auction lot model."""

    # External identifiers
    external_id: str
    platform_id: Optional[int] = None
    source_type: AuctionSource
    source_url: Optional[str] = None

    # Lot info
    lot_number: Optional[str] = None
    case_number: Optional[str] = None  # For bankruptcy/FSSP

    # Property details
    property_type: PropertyType = PropertyType.APARTMENT
    title: Optional[str] = None
    description: Optional[str] = None

    # Location
    region: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    address_normalized: Optional[str] = None
    fias_id: Optional[str] = None

    # Coordinates
    lat: Optional[Decimal] = None
    lon: Optional[Decimal] = None

    # Property characteristics
    area_total: Optional[Decimal] = None
    area_living: Optional[Decimal] = None
    area_kitchen: Optional[Decimal] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    building_year: Optional[int] = None

    # Pricing
    initial_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None
    step_price: Optional[Decimal] = None
    deposit_amount: Optional[Decimal] = None
    final_price: Optional[Decimal] = None

    # Auction timing
    auction_date: Optional[datetime] = None
    auction_end_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None

    # Status
    status: AuctionStatus = AuctionStatus.ANNOUNCED
    is_repeat_auction: bool = False
    repeat_number: int = 0

    # Organizer info
    organizer_name: Optional[str] = None
    organizer_inn: Optional[str] = None
    organizer_contact: Optional[str] = None

    # Debtor info (for bankruptcy/FSSP)
    debtor_name: Optional[str] = None
    debtor_inn: Optional[str] = None

    # Bank info (for pledges)
    bank_name: Optional[str] = None

    # Metadata
    photos: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    raw_data: Optional[dict] = None

    # Timestamps
    published_at: Optional[datetime] = None

    class Config:
        use_enum_values = True

    @field_validator('area_total', 'area_living', 'area_kitchen', mode='before')
    @classmethod
    def parse_area(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            # Remove common suffixes and clean
            v = v.replace('м²', '').replace('кв.м', '').replace('кв. м', '')
            v = v.replace(',', '.').strip()
            try:
                return Decimal(v)
            except Exception:
                return None
        return v

    @field_validator('initial_price', 'current_price', 'step_price', 'deposit_amount', 'final_price', mode='before')
    @classmethod
    def parse_price(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            # Remove currency symbols and spaces
            v = v.replace('₽', '').replace('руб', '').replace('р.', '')
            v = v.replace(' ', '').replace('\xa0', '').replace(',', '.')
            try:
                return Decimal(v)
            except Exception:
                return None
        return v

    @field_validator('rooms', 'floor', 'total_floors', 'building_year', mode='before')
    @classmethod
    def parse_int(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return None
        return v

    def is_share(self) -> bool:
        """Check if this is a share (доля) - we skip these."""
        if self.title:
            title_lower = self.title.lower()
            if 'доля' in title_lower or 'долей' in title_lower:
                return True
        if self.description:
            desc_lower = self.description.lower()
            if 'доля в праве' in desc_lower:
                return True
        return False

    def is_valid_for_collection(self) -> bool:
        """
        Check if lot should be collected based on requirements:
        - NOT a share (доля)
        - Is real estate (apartment, room, house)
        """
        # Skip shares
        if self.is_share():
            return False

        # Only collect real estate
        valid_types = {PropertyType.APARTMENT, PropertyType.ROOM, PropertyType.HOUSE}
        if self.property_type not in valid_types:
            return False

        return True


class AuctionPriceHistory(BaseModel):
    """Price history record."""
    lot_id: int
    price: Decimal
    price_type: str = "current"  # initial, current, final
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class AuctionMarketComparison(BaseModel):
    """Comparison with market prices."""
    lot_id: int
    market_price_estimate: Optional[Decimal] = None
    market_price_per_sqm: Optional[Decimal] = None
    estimation_method: Optional[str] = None
    estimation_confidence: Optional[Decimal] = None
    discount_from_market: Optional[Decimal] = None
    comparables_count: Optional[int] = None
