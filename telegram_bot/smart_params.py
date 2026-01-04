"""
Smart parameter detection based on database statistics.

Uses actual market data to estimate apartment parameters:
- Number of rooms based on area + building type
- Building type from nearby listings
- Typical characteristics by building type
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, List, Tuple
import os
from dataclasses import dataclass


def _get_db_dsn():
    """Get database DSN from environment."""
    dsn = os.getenv("PG_DSN")
    if not dsn:
        user = os.getenv("PG_USER")
        password = os.getenv("PG_PASS")
        host = os.getenv("PG_HOST", "localhost")
        port = os.getenv("PG_PORT", "5432")
        database = os.getenv("PG_DB")

        if not all([user, password, database]):
            raise ValueError(
                "Database credentials not configured. "
                "Set PG_DSN or (PG_USER, PG_PASS, PG_DB) in .env file."
            )

        dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return dsn


@dataclass
class BuildingTypeStats:
    """Statistics for a building type."""
    building_type: str
    typical_rooms_by_area: Dict[int, List[float]]  # rooms -> list of typical areas
    avg_floor_height: float
    year_range: Tuple[int, int]
    sample_count: int


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(_get_db_dsn(), cursor_factory=RealDictCursor)


def get_building_type_statistics() -> Dict[str, BuildingTypeStats]:
    """
    Analyze database to get statistics for each building type.
    
    Returns mapping: building_type -> BuildingTypeStats
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get statistics for each building type
    cur.execute("""
        SELECT 
            building_type,
            rooms,
            area_total,
            building_height,
            building_year,
            COUNT(*) as cnt
        FROM listings
        WHERE 
            building_type IS NOT NULL 
            AND rooms IS NOT NULL 
            AND area_total IS NOT NULL
            AND area_total BETWEEN 20 AND 200
        GROUP BY building_type, rooms, area_total, building_height, building_year
        ORDER BY building_type, rooms, area_total
    """)
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    # Process statistics
    stats_by_type = {}
    
    for row in rows:
        btype = row['building_type']
        
        if btype not in stats_by_type:
            stats_by_type[btype] = {
                'rooms_areas': {},  # rooms -> list of areas
                'years': [],
                'heights': [],
                'total_count': 0
            }
        
        rooms = row['rooms']
        area = float(row['area_total'])
        
        if rooms not in stats_by_type[btype]['rooms_areas']:
            stats_by_type[btype]['rooms_areas'][rooms] = []
        
        stats_by_type[btype]['rooms_areas'][rooms].append(area)
        
        if row['building_year']:
            stats_by_type[btype]['years'].append(row['building_year'])
        
        if row['building_height']:
            stats_by_type[btype]['heights'].append(row['building_height'])
        
        stats_by_type[btype]['total_count'] += row['cnt']
    
    # Convert to BuildingTypeStats objects
    result = {}
    
    for btype, data in stats_by_type.items():
        # Calculate typical areas for each room count
        typical_rooms_by_area = {}
        for rooms, areas in data['rooms_areas'].items():
            typical_rooms_by_area[rooms] = sorted(areas)
        
        # Calculate averages
        avg_height = sum(data['heights']) / len(data['heights']) if data['heights'] else 0
        year_range = (min(data['years']), max(data['years'])) if data['years'] else (0, 0)
        
        result[btype] = BuildingTypeStats(
            building_type=btype,
            typical_rooms_by_area=typical_rooms_by_area,
            avg_floor_height=avg_height,
            year_range=year_range,
            sample_count=data['total_count']
        )
    
    return result


def estimate_rooms_smart(
    area: float, 
    building_type: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> Tuple[int, float]:
    """
    Smart room count estimation based on area and building type.
    
    Args:
        area: Total area in m²
        building_type: Building type (panel, brick, monolithic, etc.)
        lat, lon: Coordinates to find similar listings
        
    Returns:
        (estimated_rooms, confidence_score)
    """
    
    # If no building type, use simple heuristic
    if not building_type:
        if area < 30:
            return 1, 0.6
        elif area < 45:
            return 1, 0.7
        elif area < 70:
            return 2, 0.7
        elif area < 90:
            return 3, 0.7
        elif area < 120:
            return 4, 0.6
        else:
            return 5, 0.5
    
    # Query database for similar listings
    conn = get_db_connection()
    cur = conn.cursor()
    
    query_params = [building_type, area - 10, area + 10]
    distance_condition = ""
    
    if lat and lon:
        query_params.extend([lon, lat])
        distance_condition = """
            AND ST_DWithin(
                location::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                5000
            )
        """
    
    cur.execute(f"""
        SELECT 
            rooms,
            COUNT(*) as cnt,
            AVG(area_total) as avg_area,
            MIN(area_total) as min_area,
            MAX(area_total) as max_area
        FROM listings
        WHERE 
            building_type = %s
            AND area_total BETWEEN %s AND %s
            AND rooms IS NOT NULL
            {distance_condition}
        GROUP BY rooms
        ORDER BY cnt DESC
        LIMIT 3
    """, query_params)
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    if not results:
        # Fallback to simple heuristic
        if area < 45:
            return 1, 0.6
        elif area < 70:
            return 2, 0.6
        else:
            return 3, 0.5
    
    # Most common room count for this area + building type
    best_match = results[0]
    total_count = sum(r['cnt'] for r in results)
    confidence = best_match['cnt'] / total_count
    
    return best_match['rooms'], confidence


def get_typical_params_for_building_type(building_type: str) -> Dict:
    """Get typical parameters for a building type."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            building_type,
            AVG(building_height) as avg_height,
            MODE() WITHIN GROUP (ORDER BY building_height) as typical_height,
            AVG(building_year) as avg_year,
            MIN(building_year) as min_year,
            MAX(building_year) as max_year,
            COUNT(*) as sample_size
        FROM listings
        WHERE building_type = %s
            AND building_height IS NOT NULL
            AND building_year IS NOT NULL
        GROUP BY building_type
    """, (building_type,))
    
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    if not result:
        return {}
    
    return {
        'avg_height': float(result['avg_height']) if result['avg_height'] else None,
        'typical_height': result['typical_height'],
        'avg_year': int(result['avg_year']) if result['avg_year'] else None,
        'year_range': (result['min_year'], result['max_year']),
        'sample_size': result['sample_size']
    }


def find_similar_listings_by_area(
    area: float,
    building_type: Optional[str] = None,
    radius: float = 10
) -> List[Dict]:
    """
    Find similar listings by area (±radius m²).
    
    Returns list of {rooms, area, building_type, count}
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    conditions = ["area_total BETWEEN %s AND %s"]
    params = [area - radius, area + radius]
    
    if building_type:
        conditions.append("building_type = %s")
        params.append(building_type)
    
    query = f"""
        SELECT 
            rooms,
            building_type,
            ROUND(AVG(area_total)::numeric, 1) as avg_area,
            COUNT(*) as cnt
        FROM listings
        WHERE {' AND '.join(conditions)}
            AND rooms IS NOT NULL
        GROUP BY rooms, building_type
        ORDER BY cnt DESC
        LIMIT 10
    """
    
    cur.execute(query, params)
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(r) for r in results]


def get_room_distribution_by_type(building_type: str) -> Dict[int, float]:
    """
    Get room count distribution for a building type.
    
    Returns: {rooms: percentage}
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        WITH room_counts AS (
            SELECT 
                rooms,
                COUNT(*) as cnt
            FROM listings
            WHERE building_type = %s
                AND rooms IS NOT NULL
            GROUP BY rooms
        )
        SELECT 
            rooms,
            cnt,
            ROUND(100.0 * cnt / SUM(cnt) OVER (), 1) as percentage
        FROM room_counts
        ORDER BY rooms
    """, (building_type,))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return {r['rooms']: float(r['percentage']) for r in results}


# Building type characteristics from Moscow market
BUILDING_TYPE_INFO = {
    'panel': {
        'name_ru': 'Панель',
        'typical_series': ['П-44', 'П-3', 'II-49', 'П-46'],
        'typical_years': (1960, 2000),
        'typical_heights': [5, 9, 12, 14, 16, 17],
        'description': 'Панельные дома советского и постсоветского периода'
    },
    'brick': {
        'name_ru': 'Кирпич',
        'typical_series': ['Сталинка', 'Хрущёвка кирпичная'],
        'typical_years': (1930, 2020),
        'typical_heights': [5, 9, 10],
        'description': 'Кирпичные дома, обычно более старые или элитные'
    },
    'monolithic': {
        'name_ru': 'Монолит',
        'typical_series': ['Современная застройка'],
        'typical_years': (2000, 2025),
        'typical_heights': [17, 20, 25, 30],
        'description': 'Монолитные дома современной застройки'
    },
    'block': {
        'name_ru': 'Блочный',
        'typical_series': ['Блочные серии'],
        'typical_years': (1960, 1990),
        'typical_heights': [5, 9, 12],
        'description': 'Блочные дома советского периода'
    },
    'monolithic_brick': {
        'name_ru': 'Монолит-кирпич',
        'typical_series': ['Современная застройка'],
        'typical_years': (2000, 2025),
        'typical_heights': [17, 20, 25],
        'description': 'Монолитно-кирпичные дома'
    }
}


if __name__ == "__main__":
    # Test smart estimation
    print("🧪 Testing smart parameter estimation\n")
    
    # Test cases
    test_cases = [
        (37.8, 'panel', None, None),
        (44, 'panel', None, None),
        (65, 'brick', None, None),
        (85, 'monolithic', None, None),
    ]
    
    for area, btype, lat, lon in test_cases:
        rooms, confidence = estimate_rooms_smart(area, btype, lat, lon)
        print(f"📏 {area}m² ({btype}):")
        print(f"   Комнат: {rooms} (уверенность: {confidence*100:.0f}%)")
        
        # Get similar listings
        similar = find_similar_listings_by_area(area, btype)
        if similar:
            print(f"   Похожие: ", end="")
            for s in similar[:3]:
                print(f"{s['rooms']}к ({s['cnt']}шт) ", end="")
            print()
        print()

