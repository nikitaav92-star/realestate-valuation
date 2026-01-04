"""Combined valuation engine using both Rosreestr and CIAN data."""

from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from .models import PropertyFeatures, ValuationRequest
from .knn_searcher import KNNSearcher, Comparable
from .rosreestr_searcher import RosreestrSearcher, RosreestrComparable


@dataclass
class CombinedEstimate:
    """Combined estimate from Rosreestr + CIAN."""
    # Market price (combined median)
    market_price: float
    market_price_per_sqm: float

    # Source breakdowns
    rosreestr_median_psm: Optional[float]
    rosreestr_count: int
    cian_median_psm: Optional[float]
    cian_count: int

    # Price range
    price_range_low: float
    price_range_high: float

    # Comparables
    rosreestr_comparables: List[RosreestrComparable]
    cian_comparables: List[Comparable]

    # Confidence and method
    confidence: int
    method_used: str


class CombinedEngine:
    """
    Combined valuation engine using Rosreestr + CIAN data.

    Key differences from HybridEngine:
    - Uses both Rosreestr (completed deals) and CIAN (asking prices)
    - Applies correct bargain discount:
        * Rosreestr: 0% (actual transaction prices)
        * CIAN: -7% (negotiation margin)
    - Calculates weighted median based on sample sizes
    """

    CIAN_BARGAIN_DISCOUNT = 0.07  # 7% discount for CIAN asking prices

    def __init__(self, dsn: Optional[str] = None):
        self.cian = KNNSearcher(dsn)
        self.rosreestr = RosreestrSearcher(dsn)

    def estimate(
        self,
        lat: float,
        lon: float,
        area_total: float,
        rooms: Optional[int] = None,
        floor: Optional[int] = None,
        total_floors: Optional[int] = None,
        building_year: Optional[int] = None,
        k: int = 10,
        max_distance_km: float = 5.0,
        cian_max_age_days: int = 90,
        rosreestr_max_age_days: int = 365
    ) -> CombinedEstimate:
        """
        Estimate property price using combined Rosreestr + CIAN data.

        Strategy:
        1. Get Rosreestr comparables (0% bargain)
        2. Get CIAN comparables (7% bargain applied)
        3. Calculate weighted median based on sample sizes
        4. More weight to Rosreestr (actual deals) when available
        """

        # Get Rosreestr estimate
        rosreestr_est = self.rosreestr.search(
            lat=lat,
            lon=lon,
            area_total=area_total,
            rooms=rooms,
            floor=floor,
            total_floors=total_floors,
            building_year=building_year,
            k=k,
            max_distance_km=max_distance_km,
            max_age_days=rosreestr_max_age_days
        )

        # Get CIAN estimate
        from .models import PropertyFeatures, ValuationRequest, BuildingType, BuildingHeight

        # Build features for CIAN
        building_height = None
        if total_floors:
            if total_floors <= 5:
                building_height = BuildingHeight.LOW
            elif total_floors <= 10:
                building_height = BuildingHeight.MEDIUM
            else:
                building_height = BuildingHeight.HIGH

        features = PropertyFeatures(
            lat=lat,
            lon=lon,
            area_total=area_total,
            rooms=rooms,
            floor=floor,
            total_floors=total_floors,
            building_height=building_height,
            building_year=building_year
        )

        cian_est = self.cian.search(
            features=features,
            k=k,
            max_distance_km=max_distance_km,
            max_age_days=cian_max_age_days
        )

        # Extract data
        rosreestr_psm = None
        rosreestr_count = 0
        rosreestr_comps = []

        if rosreestr_est and rosreestr_est.comparables:
            rosreestr_psm = rosreestr_est.median_price_per_sqm
            rosreestr_count = len(rosreestr_est.comparables)
            rosreestr_comps = rosreestr_est.comparables

        cian_psm = None
        cian_count = 0
        cian_comps = []

        if cian_est and cian_est.comparables:
            # Apply 7% bargain discount to CIAN prices
            cian_psm = cian_est.median_price_per_sqm * (1 - self.CIAN_BARGAIN_DISCOUNT)
            cian_count = len(cian_est.comparables)
            cian_comps = cian_est.comparables

        # Calculate combined market price
        market_price_per_sqm, method = self._combine_estimates(
            rosreestr_psm, rosreestr_count,
            cian_psm, cian_count
        )

        if market_price_per_sqm is None:
            raise ValueError("No valuation data available from either source")

        market_price = market_price_per_sqm * area_total

        # Calculate price range (±5%)
        price_range_low = market_price * 0.95
        price_range_high = market_price * 1.05

        # Calculate confidence
        total_comps = rosreestr_count + cian_count
        if total_comps >= 10:
            confidence = 80
        elif total_comps >= 5:
            confidence = 65
        elif total_comps >= 3:
            confidence = 50
        else:
            confidence = 30

        # Boost confidence if both sources available
        if rosreestr_count >= 3 and cian_count >= 3:
            confidence = min(90, confidence + 10)

        return CombinedEstimate(
            market_price=market_price,
            market_price_per_sqm=market_price_per_sqm,
            rosreestr_median_psm=rosreestr_psm,
            rosreestr_count=rosreestr_count,
            cian_median_psm=cian_psm,
            cian_count=cian_count,
            price_range_low=price_range_low,
            price_range_high=price_range_high,
            rosreestr_comparables=rosreestr_comps,
            cian_comparables=cian_comps,
            confidence=confidence,
            method_used=method
        )

    def _combine_estimates(
        self,
        rosreestr_psm: Optional[float],
        rosreestr_count: int,
        cian_psm: Optional[float],
        cian_count: int
    ) -> tuple[Optional[float], str]:
        """
        Combine Rosreestr and CIAN estimates with weighted average.

        Rosreestr gets higher weight because it's actual transaction data.
        CIAN already has 7% discount applied.
        """

        if rosreestr_psm is None and cian_psm is None:
            return None, "no_data"

        if rosreestr_psm is None:
            return cian_psm, "cian_only"

        if cian_psm is None:
            return rosreestr_psm, "rosreestr_only"

        # Both available - weighted average
        # Rosreestr weight: 1.5x per comparable (actual deals more reliable)
        rosreestr_weight = rosreestr_count * 1.5
        cian_weight = cian_count * 1.0

        total_weight = rosreestr_weight + cian_weight

        if total_weight == 0:
            return (rosreestr_psm + cian_psm) / 2, "simple_average"

        combined_psm = (
            rosreestr_psm * rosreestr_weight +
            cian_psm * cian_weight
        ) / total_weight

        return combined_psm, "combined_weighted"


def get_combined_estimate(
    lat: float,
    lon: float,
    area_total: float,
    rooms: Optional[int] = None,
    floor: Optional[int] = None,
    total_floors: Optional[int] = None,
    building_year: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """Convenience function for combined valuation."""

    engine = CombinedEngine()
    estimate = engine.estimate(
        lat=lat,
        lon=lon,
        area_total=area_total,
        rooms=rooms,
        floor=floor,
        total_floors=total_floors,
        building_year=building_year,
        **kwargs
    )

    # Format Rosreestr comparables for report
    rosreestr_deals = []
    for comp in estimate.rosreestr_comparables[:10]:
        rosreestr_deals.append({
            'source': 'Росреестр',
            'street': comp.street,
            'area': comp.area,
            'year': comp.year_build,
            'price': comp.price,
            'price_per_sqm': comp.price_per_sqm,
            'distance_km': comp.distance_km,
            'deal_date': comp.deal_date.strftime('%d.%m.%Y') if comp.deal_date else None
        })

    # Format CIAN comparables for report
    cian_analogs = []
    for comp in estimate.cian_comparables[:10]:
        cian_analogs.append({
            'source': 'ЦИАН',
            'url': comp.url,
            'area': comp.area_total,
            'year': comp.building_year,
            'price': comp.price,
            'price_per_sqm': comp.price_per_sqm,
            'distance_km': comp.distance_km
        })

    return {
        'market_price': estimate.market_price,
        'market_price_per_sqm': estimate.market_price_per_sqm,
        'price_range_low': estimate.price_range_low,
        'price_range_high': estimate.price_range_high,

        'rosreestr_median_psm': estimate.rosreestr_median_psm,
        'rosreestr_count': estimate.rosreestr_count,
        'cian_median_psm': estimate.cian_median_psm,
        'cian_count': estimate.cian_count,

        'rosreestr_deals': rosreestr_deals,
        'cian_analogs': cian_analogs,

        'confidence': estimate.confidence,
        'method_used': estimate.method_used,

        'area_total': area_total
    }
