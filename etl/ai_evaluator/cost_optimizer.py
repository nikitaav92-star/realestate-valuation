"""Cost optimization strategies for AI photo analysis."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Protocol

LOGGER = logging.getLogger(__name__)


class AnalysisStrategy(str, Enum):
    """Analysis strategies for cost optimization."""
    
    ALL = "all"  # Analyze all listings
    IMPORTANT = "important"  # Only premium/anomalies
    NEW = "new"  # Only new listings
    ON_DEMAND = "on_demand"  # Only on user request


@dataclass
class ListingPriority:
    """Priority scoring for selective analysis."""
    
    listing_id: int
    price: float
    area_total: float
    price_per_sqm: float
    first_seen_days_ago: int
    priority_score: float
    
    def should_analyze(self, strategy: AnalysisStrategy) -> bool:
        """Determine if listing should be analyzed."""
        
        if strategy == AnalysisStrategy.ALL:
            return True
        
        if strategy == AnalysisStrategy.ON_DEMAND:
            return False  # Only on explicit request
        
        if strategy == AnalysisStrategy.NEW:
            return self.first_seen_days_ago < 1
        
        if strategy == AnalysisStrategy.IMPORTANT:
            # Important if:
            # 1. Premium (>15M руб)
            # 2. Price anomaly (too high/low per sqm)
            # 3. New (today)
            
            is_premium = self.price > 15000000
            is_expensive_per_sqm = self.price_per_sqm > 250000
            is_cheap_per_sqm = self.price_per_sqm < 150000
            is_new = self.first_seen_days_ago < 1
            
            return is_premium or is_expensive_per_sqm or is_cheap_per_sqm or is_new
        
        return False


class CostOptimizer:
    """Optimize AI analysis costs."""
    
    def __init__(self, strategy: AnalysisStrategy = AnalysisStrategy.IMPORTANT):
        """Initialize cost optimizer.
        
        Parameters
        ----------
        strategy : AnalysisStrategy
            Analysis strategy to use
        """
        self.strategy = strategy
    
    def filter_listings_for_analysis(
        self,
        listings: List[ListingPriority],
    ) -> List[ListingPriority]:
        """Filter listings based on strategy.
        
        Parameters
        ----------
        listings : list
            All available listings
            
        Returns
        -------
        list
            Filtered listings to analyze
        """
        if self.strategy == AnalysisStrategy.ALL:
            return listings
        
        filtered = [
            listing for listing in listings
            if listing.should_analyze(self.strategy)
        ]
        
        # Sort by priority
        filtered.sort(key=lambda x: x.priority_score, reverse=True)
        
        LOGGER.info(
            f"Filtered {len(filtered)}/{len(listings)} listings for analysis "
            f"(strategy={self.strategy.value})"
        )
        
        return filtered
    
    def estimate_cost(
        self,
        listings_count: int,
        *,
        photos_per_listing: int = 1,
        cost_per_photo: float = 0.00425,
    ) -> dict:
        """Estimate analysis cost.
        
        Parameters
        ----------
        listings_count : int
            Number of listings to analyze
        photos_per_listing : int
            Photos to analyze per listing
        cost_per_photo : float
            Cost per photo (GPT-4 Vision low detail default)
            
        Returns
        -------
        dict
            Cost estimate
        """
        total_photos = listings_count * photos_per_listing
        total_cost = total_photos * cost_per_photo
        
        # Estimate time (assume 2s per photo)
        total_time_sec = total_photos * 2
        total_time_hours = total_time_sec / 3600
        
        return {
            "listings_count": listings_count,
            "photos_per_listing": photos_per_listing,
            "total_photos": total_photos,
            "cost_per_photo": cost_per_photo,
            "total_cost_usd": total_cost,
            "estimated_time_hours": total_time_hours,
        }
    
    def calculate_priority_score(
        self,
        price: float,
        area_total: float,
        first_seen_days_ago: int,
    ) -> float:
        """Calculate priority score for listing.
        
        Higher score = higher priority for analysis.
        
        Parameters
        ----------
        price : float
            Listing price
        area_total : float
            Total area in m²
        first_seen_days_ago : int
            Days since first seen
            
        Returns
        -------
        float
            Priority score (0-100)
        """
        score = 0.0
        
        price_per_sqm = price / area_total if area_total > 0 else 0
        
        # Premium listings (>15M)
        if price > 15000000:
            score += 30
        
        # Price anomalies
        if price_per_sqm > 250000:  # Expensive per sqm
            score += 25
        elif price_per_sqm < 150000:  # Cheap per sqm (potential deal)
            score += 20
        
        # Recency bonus
        if first_seen_days_ago < 1:
            score += 25  # New today
        elif first_seen_days_ago < 7:
            score += 10  # This week
        
        # Large apartments
        if area_total > 100:
            score += 10
        
        return min(score, 100)  # Cap at 100

