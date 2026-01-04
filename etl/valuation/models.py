"""Data models for valuation system."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum


class BuildingType(str, Enum):
    """Building construction types."""
    PANEL = "panel"
    BRICK = "brick"
    MONOLITHIC = "monolithic"
    BLOCK = "block"
    WOOD = "wood"
    OTHER = "other"
    UNKNOWN = "unknown"


class BuildingHeight(str, Enum):
    """Building height categories."""
    LOW = "low"        # 1-5 floors
    MEDIUM = "medium"  # 6-10 floors
    HIGH = "high"      # 11+ floors


@dataclass
class PropertyFeatures:
    """Property characteristics for valuation."""

    # Location
    lat: Optional[float] = None
    lon: Optional[float] = None
    district_id: Optional[int] = None

    # Physical
    area_total: float = 0.0
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None

    # Building
    building_type: Optional[BuildingType] = None
    building_height: Optional[BuildingHeight] = None
    building_year: Optional[int] = None

    # Quality
    renovation: Optional[str] = None
    has_elevator: Optional[bool] = None
    has_parking: Optional[bool] = None

    # Exclude from comparables (для исключения оцениваемого объекта из аналогов)
    exclude_listing_id: Optional[int] = None
    
    # For similarity calculation
    def to_vector(self) -> dict:
        """Convert to feature vector for KNN."""
        return {
            'area_total': self.area_total,
            'rooms': self.rooms or 0,
            'floor': self.floor or 0,
            'total_floors': self.total_floors or 0,
            'building_year': self.building_year or 2000,
            'building_type': self.building_type.value if self.building_type else 'unknown',
            'building_height': self.building_height.value if self.building_height else 'medium',
            'has_elevator': 1 if self.has_elevator else 0,
            'has_parking': 1 if self.has_parking else 0,
        }


@dataclass
class Comparable:
    """A comparable property used in valuation."""
    
    listing_id: int
    url: Optional[str]  # CIAN URL
    price: float
    price_per_sqm: float
    
    # Features
    area_total: float
    rooms: Optional[int]
    floor: Optional[int]
    
    # Location
    lat: Optional[float]
    lon: Optional[float]
    distance_km: float
    
    # Quality
    building_type: Optional[str]
    building_year: Optional[int]
    
    # Metadata
    seen_at: datetime
    age_days: int
    
    # Scores
    similarity_score: float  # 0-100
    weight: float            # 0-1
    
    def __repr__(self):
        return (
            f"Comparable(id={self.listing_id}, "
            f"price={self.price:,.0f}, "
            f"dist={self.distance_km:.1f}km, "
            f"sim={self.similarity_score:.0f}%)"
        )


@dataclass
class ValuationRequest:
    """Request for property valuation."""
    
    features: PropertyFeatures
    k: int = 10  # Number of comparables
    max_distance_km: float = 5.0
    max_age_days: int = 90


@dataclass
class GridEstimate:
    """Grid-based valuation estimate."""
    
    avg_price_per_sqm: float
    median_price_per_sqm: float
    
    district_id: Optional[int]
    property_segment_id: Optional[int]
    
    sample_size: int
    confidence: int  # 0-100
    
    fallback_level: str  # exact, relaxed_height, relaxed_type, district, global


@dataclass
class KNNEstimate:
    """KNN-based valuation estimate."""
    
    avg_price: float
    median_price: float
    avg_price_per_sqm: float
    median_price_per_sqm: float
    
    comparables: List[Comparable]
    
    confidence: int  # 0-100
    total_weight: float


@dataclass
class ValuationResponse:
    """Final valuation response."""
    
    # Primary estimates
    estimated_price: float
    estimated_price_per_sqm: float
    
    price_range_low: float
    price_range_high: float
    
    # Component estimates
    grid_estimate: Optional[GridEstimate]
    knn_estimate: Optional[KNNEstimate]
    
    # Metadata
    confidence: int  # 0-100, overall confidence
    method_used: str  # hybrid, knn_only, grid_only
    
    # Weights used
    grid_weight: float
    knn_weight: float
    
    # Request details
    request: ValuationRequest
    
    # Timestamp
    timestamp: datetime
    
    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"💰 Estimated Price: {self.estimated_price:,.0f} ₽\n"
            f"📊 Price/sqm: {self.estimated_price_per_sqm:,.0f} ₽\n"
            f"📈 Range: {self.price_range_low:,.0f} - {self.price_range_high:,.0f} ₽\n"
            f"🎯 Confidence: {self.confidence}%\n"
            f"🔧 Method: {self.method_used}\n"
            f"⚖️  Grid: {self.grid_weight:.0%} | KNN: {self.knn_weight:.0%}"
        )
