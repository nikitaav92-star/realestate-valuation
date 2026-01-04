"""Hybrid valuation engine combining Grid and KNN approaches."""

from datetime import datetime
from typing import Optional

from .models import (
    PropertyFeatures, ValuationRequest, ValuationResponse,
    GridEstimate, KNNEstimate
)
from .grid_estimator import GridEstimator
from .knn_searcher import KNNSearcher


class HybridEngine:
    """
    Hybrid valuation engine combining Grid and KNN methods.
    
    Strategy:
    - If KNN has high confidence (70+) and good comparables (5+), use KNN-heavy (80/20)
    - If Grid has high confidence (60+) but KNN is weak, use Grid-heavy (30/70)
    - Otherwise, balanced approach (50/50)
    - If only one method works, use it at 100%
    """
    
    def __init__(self, dsn: Optional[str] = None):
        self.grid = GridEstimator(dsn)
        self.knn = KNNSearcher(dsn)
    
    def estimate(self, request: ValuationRequest) -> ValuationResponse:
        """
        Generate valuation estimate using BOTTOM 3 prices + 7% bargain.
        
        Strategy: Take 1-3 lowest comparable prices, apply 7% discount (торг).
        This gives conservative buyer-side valuation.
        
        Args:
            request: Valuation request with property features
        
        Returns:
            ValuationResponse with conservative estimate
        """
        
        # Get both estimates
        grid_est = self.grid.estimate(request.features)
        knn_est = self.knn.search(
            request.features,
            k=request.k,
            max_distance_km=request.max_distance_km,
            max_age_days=request.max_age_days
        )
        
        # Determine weights and method
        grid_weight, knn_weight, method = self._determine_weights(grid_est, knn_est)
        
        # Calculate combined estimate using BOTTOM 3 strategy
        if knn_est and len(knn_est.comparables) >= 1:
            # Filter outliers using IQR method before BOTTOM-3 calculation
            prices = sorted([c.price_per_sqm for c in knn_est.comparables])
            if len(prices) >= 4:
                q1_idx = len(prices) // 4
                q3_idx = (3 * len(prices)) // 4
                q1 = prices[q1_idx]
                q3 = prices[q3_idx]
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                filtered_comps = [c for c in knn_est.comparables
                                  if lower_bound <= c.price_per_sqm <= upper_bound]
                # Use filtered if we still have enough comparables
                if len(filtered_comps) >= 3:
                    work_comps = filtered_comps
                else:
                    work_comps = knn_est.comparables
            else:
                work_comps = knn_est.comparables

            # Sort by PRICE PER SQM (ascending) - not total price!
            sorted_comps = sorted(work_comps, key=lambda c: c.price_per_sqm)

            # Take bottom 1-3 (depending on availability)
            bottom_count = min(3, len(sorted_comps))
            bottom_comps = sorted_comps[:bottom_count]

            # Average of bottom prices PER SQM
            bottom_avg_psm = sum(c.price_per_sqm for c in bottom_comps) / len(bottom_comps)
            
            # Apply 7% bargain discount
            BARGAIN_DISCOUNT = 0.93  # 7% торг
            
            estimated_psm = bottom_avg_psm * BARGAIN_DISCOUNT
            estimated_price = estimated_psm * request.features.area_total
            
            # Confidence based on number of comparables
            if len(knn_est.comparables) >= 5:
                confidence = 75
            elif len(knn_est.comparables) >= 3:
                confidence = 65
            else:
                confidence = 50

            # Price range depends on confidence
            # Higher confidence → narrower range, lower confidence → wider range
            if confidence >= 70:
                range_pct = 0.05  # ±5%
            elif confidence >= 50:
                range_pct = 0.10  # ±10%
            else:
                range_pct = 0.15  # ±15%

            price_low = estimated_price * (1 - range_pct)
            price_high = estimated_price * (1 + range_pct)
            
            method = f"bottom_{bottom_count}_with_bargain"
        
        elif grid_est:
            # Fallback to Grid only
            estimated_psm = grid_est.median_price_per_sqm
            estimated_price = estimated_psm * request.features.area_total
            confidence = grid_est.confidence

            # Price range depends on confidence
            if confidence >= 70:
                range_pct = 0.05  # ±5%
            elif confidence >= 50:
                range_pct = 0.10  # ±10%
            else:
                range_pct = 0.15  # ±15%

            price_low = estimated_price * (1 - range_pct)
            price_high = estimated_price * (1 + range_pct)

            method = "grid_only"
            grid_weight = 1.0
            knn_weight = 0.0
        
        else:
            raise ValueError("No estimation method succeeded")
        
        return ValuationResponse(
            estimated_price=estimated_price,
            estimated_price_per_sqm=estimated_psm,
            price_range_low=price_low,
            price_range_high=price_high,
            grid_estimate=grid_est,
            knn_estimate=knn_est,
            confidence=confidence,
            method_used=method,
            grid_weight=grid_weight,
            knn_weight=knn_weight,
            request=request,
            timestamp=datetime.now()
        )
    
    def _determine_weights(
        self,
        grid_est: Optional[GridEstimate],
        knn_est: Optional[KNNEstimate]
    ) -> tuple[float, float, str]:
        """
        Determine optimal weights for grid vs KNN.
        
        Returns:
            (grid_weight, knn_weight, method_name)
        """
        
        if not grid_est and not knn_est:
            raise ValueError("Both estimation methods failed")
        
        if not grid_est:
            return (0.0, 1.0, "knn_only")
        
        if not knn_est:
            return (1.0, 0.0, "grid_only")
        
        # Both available - determine optimal mix
        
        # Strong KNN: high confidence + many comparables
        if knn_est.confidence >= 70 and len(knn_est.comparables) >= 5:
            return (0.2, 0.8, "hybrid_knn_heavy")
        
        # Weak KNN but strong Grid
        if knn_est.confidence < 40 and grid_est.confidence >= 60:
            return (0.7, 0.3, "hybrid_grid_heavy")
        
        # Balanced
        return (0.5, 0.5, "hybrid_balanced")
