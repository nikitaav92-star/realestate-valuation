"""Grid-based price estimator using multi-dimensional aggregates."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import date, timedelta

from .models import PropertyFeatures, GridEstimate, BuildingType, BuildingHeight


class GridEstimator:
    """
    Grid-based estimator using pre-aggregated price data.
    
    Strategy:
    1. Try exact match (district × building_type × height × rooms)
    2. Relax height constraint
    3. Relax building_type constraint
    4. Use district-level aggregate
    5. Use global average (last resort)
    """
    
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv(
            "PG_DSN",
            "postgresql://realuser:strongpass123@localhost:5432/realdb"
        )
    
    def estimate(self, features: PropertyFeatures) -> Optional[GridEstimate]:
        """Get grid-based estimate for property."""
        
        conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)
        
        try:
            # Try strategies in order
            estimate = (
                self._exact_match(conn, features) or
                self._relaxed_height(conn, features) or
                self._relaxed_type(conn, features) or
                self._district_level(conn, features) or
                self._global_average(conn, features)
            )
            
            return estimate
        
        finally:
            conn.close()
    
    def _get_property_segment_id(
        self,
        conn,
        building_type: Optional[str],
        building_height: Optional[str],
        rooms: Optional[int]
    ) -> Optional[int]:
        """Find property_segment_id for given characteristics."""
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT segment_id
                FROM property_segments
                WHERE building_type = COALESCE(%s, 'other')
                  AND building_height = COALESCE(%s, 'medium')
                  AND rooms_count = LEAST(COALESCE(%s, 2), 5)
                LIMIT 1
            """, (building_type, building_height, rooms))
            
            row = cur.fetchone()
            return row['segment_id'] if row else None
    
    def _exact_match(
        self,
        conn,
        features: PropertyFeatures
    ) -> Optional[GridEstimate]:
        """Try exact match on all dimensions."""
        
        if not features.district_id:
            return None
        
        building_type = features.building_type.value if features.building_type else None
        building_height = features.building_height.value if features.building_height else None
        
        segment_id = self._get_property_segment_id(
            conn,
            building_type,
            building_height,
            features.rooms
        )
        
        if not segment_id:
            return None
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    avg_price_per_sqm,
                    median_price_per_sqm,
                    total_listings,
                    confidence_score,
                    district_id,
                    property_segment_id
                FROM multidim_aggregates
                WHERE district_id = %s
                  AND property_segment_id = %s
                  AND date >= CURRENT_DATE - INTERVAL '30 days'
                  AND total_listings >= 3
                ORDER BY date DESC
                LIMIT 1
            """, (features.district_id, segment_id))
            
            row = cur.fetchone()
            
            if row:
                return GridEstimate(
                    avg_price_per_sqm=float(row['avg_price_per_sqm']),
                    median_price_per_sqm=float(row['median_price_per_sqm']),
                    district_id=row['district_id'],
                    property_segment_id=row['property_segment_id'],
                    sample_size=row['total_listings'],
                    confidence=row['confidence_score'] or 50,
                    fallback_level='exact'
                )
        
        return None
    
    def _relaxed_height(
        self,
        conn,
        features: PropertyFeatures
    ) -> Optional[GridEstimate]:
        """Relax building height constraint."""
        
        if not features.district_id:
            return None
        
        building_type = features.building_type.value if features.building_type else None
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    AVG(avg_price_per_sqm) as avg_price_per_sqm,
                    AVG(median_price_per_sqm) as median_price_per_sqm,
                    SUM(total_listings) as total_listings,
                    district_id
                FROM multidim_aggregates ma
                JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
                WHERE ma.district_id = %s
                  AND ps.building_type = COALESCE(%s, 'other')
                  AND ps.rooms_count = LEAST(COALESCE(%s, 2), 5)
                  AND ma.date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY ma.district_id
                HAVING SUM(total_listings) >= 3
            """, (features.district_id, building_type, features.rooms))
            
            row = cur.fetchone()
            
            if row:
                sample_size = row['total_listings']
                confidence = min(100, 30 + (sample_size // 5) * 10)
                
                return GridEstimate(
                    avg_price_per_sqm=float(row['avg_price_per_sqm']),
                    median_price_per_sqm=float(row['median_price_per_sqm']),
                    district_id=row['district_id'],
                    property_segment_id=None,
                    sample_size=sample_size,
                    confidence=confidence,
                    fallback_level='relaxed_height'
                )
        
        return None
    
    def _relaxed_type(
        self,
        conn,
        features: PropertyFeatures
    ) -> Optional[GridEstimate]:
        """Relax building type constraint."""
        
        if not features.district_id:
            return None
        
        building_height = features.building_height.value if features.building_height else None
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    AVG(avg_price_per_sqm) as avg_price_per_sqm,
                    AVG(median_price_per_sqm) as median_price_per_sqm,
                    SUM(total_listings) as total_listings,
                    district_id
                FROM multidim_aggregates ma
                JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
                WHERE ma.district_id = %s
                  AND ps.building_height = COALESCE(%s, 'medium')
                  AND ps.rooms_count = LEAST(COALESCE(%s, 2), 5)
                  AND ma.date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY ma.district_id
                HAVING SUM(total_listings) >= 3
            """, (features.district_id, building_height, features.rooms))
            
            row = cur.fetchone()
            
            if row:
                sample_size = row['total_listings']
                confidence = min(100, 20 + (sample_size // 10) * 10)
                
                return GridEstimate(
                    avg_price_per_sqm=float(row['avg_price_per_sqm']),
                    median_price_per_sqm=float(row['median_price_per_sqm']),
                    district_id=row['district_id'],
                    property_segment_id=None,
                    sample_size=sample_size,
                    confidence=confidence,
                    fallback_level='relaxed_type'
                )
        
        return None
    
    def _district_level(
        self,
        conn,
        features: PropertyFeatures
    ) -> Optional[GridEstimate]:
        """District-level aggregate (no property constraints)."""
        
        if not features.district_id:
            return None
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    AVG(avg_price_per_sqm) as avg_price_per_sqm,
                    AVG(median_price_per_sqm) as median_price_per_sqm,
                    SUM(total_listings) as total_listings,
                    district_id
                FROM multidim_aggregates
                WHERE district_id = %s
                  AND date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY district_id
                HAVING SUM(total_listings) >= 3
            """, (features.district_id,))
            
            row = cur.fetchone()
            
            if row:
                sample_size = row['total_listings']
                confidence = min(100, 10 + (sample_size // 20) * 10)
                
                return GridEstimate(
                    avg_price_per_sqm=float(row['avg_price_per_sqm']),
                    median_price_per_sqm=float(row['median_price_per_sqm']),
                    district_id=row['district_id'],
                    property_segment_id=None,
                    sample_size=sample_size,
                    confidence=confidence,
                    fallback_level='district'
                )
        
        return None
    
    def _global_average(
        self,
        conn,
        features: PropertyFeatures
    ) -> Optional[GridEstimate]:
        """Global average as last resort."""
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    AVG(COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0)) as avg_price_per_sqm,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0)
                    ) as median_price_per_sqm,
                    COUNT(*) as total_listings
                FROM listings l
                LEFT JOIN LATERAL (
                    SELECT price
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) lp ON TRUE
                WHERE l.area_total > 0
                  AND COALESCE(lp.price, l.initial_price) > 0
                  AND l.last_seen >= CURRENT_DATE - INTERVAL '90 days'
            """)
            
            row = cur.fetchone()
            
            if row and row['total_listings'] > 0:
                return GridEstimate(
                    avg_price_per_sqm=float(row['avg_price_per_sqm']),
                    median_price_per_sqm=float(row['median_price_per_sqm']),
                    district_id=None,
                    property_segment_id=None,
                    sample_size=row['total_listings'],
                    confidence=10,
                    fallback_level='global'
                )
        
        return None
