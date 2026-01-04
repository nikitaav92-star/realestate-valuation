#!/usr/bin/env python3
"""
Intelligent price estimation using multi-dimensional segmentation.

Estimates property price based on:
- Location (coordinates or address)
- Building type (panel, brick, monolithic, block)
- Building height (floors)
- Rooms count
- Area

Uses hierarchical fallback strategy if exact segment has insufficient data.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, List
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


class PriceEstimator:
    """Intelligent price estimator with hierarchical fallback."""
    
    def __init__(self):
        self.conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        self.cursor = self.conn.cursor()
    
    def estimate(
        self,
        lat: float = None,
        lon: float = None,
        address: str = None,
        building_type: str = 'panel',
        total_floors: int = 9,
        rooms: int = 2,
        area: float = 50.0
    ) -> Dict:
        """
        Estimate property price.
        
        Args:
            lat, lon: Coordinates (if known)
            address: Address string (if coordinates unknown)
            building_type: panel, brick, monolithic, block
            total_floors: Total floors in building
            rooms: Number of rooms
            area: Total area in sqm
        
        Returns:
            Dict with estimate details
        """
        print("=" * 80)
        print("🏠 PRICE ESTIMATION")
        print("=" * 80)
        
        # Normalize inputs
        building_type = self._normalize_building_type(building_type)
        building_height = self._classify_height(total_floors)
        rooms_grouped = min(rooms, 5) if rooms else 2
        
        print(f"\n📋 Input Parameters:")
        print(f"   Location: {f'({lat}, {lon})' if lat else address}")
        print(f"   Building: {building_type}, {building_height} ({total_floors} floors)")
        print(f"   Rooms: {rooms}")
        print(f"   Area: {area} m²")
        
        # Find district
        district = self._find_district(lat, lon, address)
        if not district:
            return self._create_error_result("Could not determine district")
        
        print(f"\n📍 District: {district['name']} (level {district['level']})")
        
        # Strategy 1: Exact match
        result = self._exact_match(
            district['district_id'], 
            building_type, 
            building_height, 
            rooms_grouped
        )
        
        if result and result['confidence'] >= 60:
            return self._create_result(result, area, strategy='exact', district=district)
        
        # Strategy 2: Relaxed building height
        result = self._relaxed_height(
            district['district_id'],
            building_type,
            rooms_grouped
        )
        
        if result and result['confidence'] >= 40:
            return self._create_result(result, area, strategy='relaxed_height', district=district)
        
        # Strategy 3: Relaxed building type
        result = self._relaxed_type(
            district['district_id'],
            building_height,
            rooms_grouped
        )
        
        if result and result['confidence'] >= 40:
            return self._create_result(result, area, strategy='relaxed_type', district=district)
        
        # Strategy 4: District level only
        result = self._district_level(
            district['district_id'],
            rooms_grouped
        )
        
        if result:
            return self._create_result(result, area, strategy='district_only', district=district)
        
        # Strategy 5: Parent district
        if district['parent_id']:
            result = self._district_level(district['parent_id'], rooms_grouped)
            if result:
                return self._create_result(result, area, strategy='parent_district', district=district)
        
        # Fallback: Global average
        return self._global_average(area, rooms)
    
    def _normalize_building_type(self, raw: str) -> str:
        """Normalize building type."""
        mapping = {
            'панель': 'panel',
            'панельный': 'panel',
            'кирпич': 'brick',
            'кирпичный': 'brick',
            'монолит': 'monolithic',
            'монолитный': 'monolithic',
            'блок': 'block',
            'блочный': 'block'
        }
        return mapping.get(raw.lower(), raw.lower())
    
    def _classify_height(self, floors: int) -> str:
        """Classify building height."""
        if floors <= 5:
            return 'low'
        elif floors <= 10:
            return 'medium'
        else:
            return 'high'
    
    def _find_district(self, lat: float = None, lon: float = None, address: str = None) -> Optional[Dict]:
        """Find district by coordinates or address."""
        if lat and lon:
            self.cursor.execute("""
                SELECT 
                    district_id,
                    name,
                    level,
                    parent_district_id as parent_id
                FROM districts
                WHERE ST_Contains(
                    geometry,
                    ST_SetSRID(ST_Point(%s, %s), 4326)
                )
                ORDER BY level DESC  -- Prefer most granular
                LIMIT 1
            """, (lon, lat))
        elif address:
            # Parse district from address
            import re
            match = re.search(r'р-н\s+([А-ЯЁа-яё\-\s]+?)(?:,|$)', address)
            if match:
                district_name = match.group(1).strip()
                self.cursor.execute("""
                    SELECT 
                        district_id,
                        name,
                        level,
                        parent_district_id as parent_id
                    FROM districts
                    WHERE LOWER(name) LIKE LOWER(%s)
                    ORDER BY level DESC
                    LIMIT 1
                """, (f'%{district_name}%',))
        
        return self.cursor.fetchone()
    
    def _exact_match(self, district_id: int, building_type: str, height: str, rooms: int) -> Optional[Dict]:
        """Strategy 1: Exact match on all dimensions."""
        self.cursor.execute("""
            SELECT 
                ma.median_price_per_sqm,
                ma.avg_price_per_sqm,
                ma.min_price,
                ma.max_price,
                ma.total_listings,
                ma.confidence_score as confidence,
                ma.price_stddev
            FROM multidim_aggregates ma
            JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
            WHERE ma.district_id = %s
              AND ps.building_type = %s
              AND ps.building_height = %s
              AND ps.rooms_count = %s
              AND ma.date = CURRENT_DATE
            LIMIT 1
        """, (district_id, building_type, height, rooms))
        
        return self.cursor.fetchone()
    
    def _relaxed_height(self, district_id: int, building_type: str, rooms: int) -> Optional[Dict]:
        """Strategy 2: Ignore building height, average across heights."""
        self.cursor.execute("""
            SELECT 
                ROUND(AVG(ma.median_price_per_sqm)::numeric, 2) as median_price_per_sqm,
                ROUND(AVG(ma.avg_price_per_sqm)::numeric, 2) as avg_price_per_sqm,
                MIN(ma.min_price) as min_price,
                MAX(ma.max_price) as max_price,
                SUM(ma.total_listings) as total_listings,
                ROUND(AVG(ma.confidence_score)::numeric, 0) as confidence,
                ROUND(AVG(ma.price_stddev)::numeric, 2) as price_stddev
            FROM multidim_aggregates ma
            JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
            WHERE ma.district_id = %s
              AND ps.building_type = %s
              AND ps.rooms_count = %s
              AND ma.date = CURRENT_DATE
            GROUP BY ma.district_id
        """, (district_id, building_type, rooms))
        
        return self.cursor.fetchone()
    
    def _relaxed_type(self, district_id: int, height: str, rooms: int) -> Optional[Dict]:
        """Strategy 3: Ignore building type, average across types."""
        self.cursor.execute("""
            SELECT 
                ROUND(AVG(ma.median_price_per_sqm)::numeric, 2) as median_price_per_sqm,
                ROUND(AVG(ma.avg_price_per_sqm)::numeric, 2) as avg_price_per_sqm,
                MIN(ma.min_price) as min_price,
                MAX(ma.max_price) as max_price,
                SUM(ma.total_listings) as total_listings,
                ROUND(AVG(ma.confidence_score)::numeric, 0) as confidence,
                ROUND(AVG(ma.price_stddev)::numeric, 2) as price_stddev
            FROM multidim_aggregates ma
            JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
            WHERE ma.district_id = %s
              AND ps.building_height = %s
              AND ps.rooms_count = %s
              AND ma.date = CURRENT_DATE
            GROUP BY ma.district_id
        """, (district_id, height, rooms))
        
        return self.cursor.fetchone()
    
    def _district_level(self, district_id: int, rooms: int) -> Optional[Dict]:
        """Strategy 4: District + rooms only."""
        self.cursor.execute("""
            SELECT 
                ROUND(AVG(ma.median_price_per_sqm)::numeric, 2) as median_price_per_sqm,
                ROUND(AVG(ma.avg_price_per_sqm)::numeric, 2) as avg_price_per_sqm,
                MIN(ma.min_price) as min_price,
                MAX(ma.max_price) as max_price,
                SUM(ma.total_listings) as total_listings,
                ROUND(AVG(ma.confidence_score)::numeric, 0) as confidence,
                ROUND(AVG(ma.price_stddev)::numeric, 2) as price_stddev
            FROM multidim_aggregates ma
            JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
            WHERE ma.district_id = %s
              AND ps.rooms_count = %s
              AND ma.date = CURRENT_DATE
            GROUP BY ma.district_id
        """, (district_id, rooms))
        
        return self.cursor.fetchone()
    
    def _global_average(self, area: float, rooms: int) -> Dict:
        """Strategy 5: Global average for rooms."""
        self.cursor.execute("""
            SELECT 
                ROUND(AVG(median_price_per_sqm)::numeric, 2) as median_price_per_sqm
            FROM multidim_aggregates ma
            JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
            WHERE ps.rooms_count = %s
              AND ma.date = CURRENT_DATE
        """, (min(rooms, 5),))
        
        result = self.cursor.fetchone()
        price_per_sqm = result['median_price_per_sqm'] if result else 200000
        
        return {
            'estimated_price': int(price_per_sqm * area),
            'price_per_sqm': int(price_per_sqm),
            'confidence': 10,
            'strategy': 'global_average',
            'sample_size': 0,
            'range_min': None,
            'range_max': None
        }
    
    def _create_result(self, data: Dict, area: float, strategy: str, district: Dict) -> Dict:
        """Create formatted result."""
        price_per_sqm = float(data['median_price_per_sqm'])
        estimated_price = price_per_sqm * area
        
        # Calculate confidence-adjusted range
        stddev = float(data.get('price_stddev', 0)) if data.get('price_stddev') else price_per_sqm * 0.15
        
        return {
            'estimated_price': int(estimated_price),
            'price_per_sqm': int(price_per_sqm),
            'confidence': int(data['confidence']),
            'strategy': strategy,
            'district': district['name'],
            'district_level': district['level'],
            'sample_size': data['total_listings'],
            'range_min': int((price_per_sqm - stddev) * area),
            'range_max': int((price_per_sqm + stddev) * area),
            'range_min_sqm': int(price_per_sqm - stddev),
            'range_max_sqm': int(price_per_sqm + stddev)
        }
    
    def _create_error_result(self, message: str) -> Dict:
        """Create error result."""
        return {
            'error': message,
            'estimated_price': None,
            'confidence': 0
        }
    
    def close(self):
        """Close database connection."""
        self.cursor.close()
        self.conn.close()


def print_estimate(result: Dict, area: float):
    """Pretty print estimation result."""
    if 'error' in result:
        print(f"\n❌ Error: {result['error']}")
        return
    
    print("\n" + "=" * 80)
    print("💰 PRICE ESTIMATE")
    print("=" * 80)
    
    print(f"\n✅ Estimated Price: {result['estimated_price']:,} ₽")
    print(f"   Price per m²: {result['price_per_sqm']:,} ₽/m²")
    print(f"   For area: {area:.1f} m²")
    
    if result.get('range_min') and result.get('range_max'):
        print(f"\n📊 Price Range:")
        print(f"   Min: {result['range_min']:,} ₽  ({result['range_min_sqm']:,} ₽/m²)")
        print(f"   Max: {result['range_max']:,} ₽  ({result['range_max_sqm']:,} ₽/m²)")
    
    print(f"\n🎯 Confidence: {result['confidence']}%")
    
    strategy_desc = {
        'exact': 'Exact match (all parameters)',
        'relaxed_height': 'Building type + rooms (all heights)',
        'relaxed_type': 'Building height + rooms (all types)',
        'district_only': 'District + rooms only',
        'parent_district': 'Parent district average',
        'global_average': 'Global average for rooms'
    }
    
    print(f"📍 Strategy: {strategy_desc.get(result['strategy'], result['strategy'])}")
    print(f"🏘️  District: {result.get('district', 'Unknown')} (level {result.get('district_level', '?')})")
    print(f"📈 Sample size: {result.get('sample_size', 0)} comparable listings")
    
    print("\n" + "=" * 80)


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description='Estimate property price')
    parser.add_argument('--lat', type=float, help='Latitude')
    parser.add_argument('--lon', type=float, help='Longitude')
    parser.add_argument('--address', type=str, help='Address string')
    parser.add_argument('--type', type=str, default='panel', 
                       choices=['panel', 'brick', 'monolithic', 'block'],
                       help='Building type')
    parser.add_argument('--floors', type=int, default=9, help='Total floors in building')
    parser.add_argument('--rooms', type=int, default=2, help='Number of rooms')
    parser.add_argument('--area', type=float, default=50.0, help='Total area in sqm')
    
    args = parser.parse_args()
    
    if not args.lat and not args.address:
        print("❌ Error: Provide either --lat/--lon or --address")
        parser.print_help()
        return
    
    # Run estimation
    estimator = PriceEstimator()
    
    result = estimator.estimate(
        lat=args.lat,
        lon=args.lon,
        address=args.address,
        building_type=args.type,
        total_floors=args.floors,
        rooms=args.rooms,
        area=args.area
    )
    
    print_estimate(result, args.area)
    
    estimator.close()


if __name__ == '__main__':
    main()

