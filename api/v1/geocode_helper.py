"""Helper functions for geocoding and district detection."""

import os
import psycopg2
import requests
from psycopg2.extras import RealDictCursor
from typing import Optional, Tuple


DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
DADATA_API_KEY = os.getenv("DADATA_API_KEY")
DADATA_SECRET_KEY = os.getenv("DADATA_SECRET_KEY")


def find_district_by_coordinates(lat: float, lon: float) -> Optional[int]:
    """
    Find district_id by coordinates using PostGIS spatial query.
    Returns district_id or None if not found.
    """
    try:
        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT district_id, name
            FROM districts
            WHERE ST_Contains(
                geometry,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            )
            ORDER BY level DESC
            LIMIT 1
        """, (lon, lat))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return result['district_id']
        
        return None
    
    except Exception as e:
        print(f"Error finding district: {e}")
        return None


def get_district_avg_price(district_id: int) -> Optional[float]:
    """Get average price per sqm for a district."""
    try:
        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT AVG(initial_price / NULLIF(area_total, 0)) as avg_price_per_sqm
            FROM listings
            WHERE district_id = %s
              AND initial_price > 0
              AND area_total > 0
        """, (district_id,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result and result['avg_price_per_sqm']:
            return float(result['avg_price_per_sqm'])
        
        return None
    
    except Exception as e:
        print(f"Error getting district price: {e}")
        return None


def find_building_type_by_coordinates(lat: float, lon: float, radius_m: int = 200) -> Optional[str]:
    """
    Auto-detect building_type by finding nearby listings with known building_type.
    
    Args:
        lat: Latitude
        lon: Longitude
        radius_m: Search radius in meters (default 200m)
    
    Returns:
        Most common building_type nearby, or None if not found
    """
    result = find_building_type_with_sources(lat, lon, radius_m)
    return result['building_type'] if result else None


def find_building_type_with_sources(lat: float, lon: float, radius_m: int = 200) -> Optional[dict]:
    """
    Auto-detect building_type and return source listings for verification.
    
    Args:
        lat: Latitude
        lon: Longitude
        radius_m: Search radius in meters (default 200m)
    
    Returns:
        Dict with 'building_type' and 'sources' (list of nearby listings), or None
    """
    try:
        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        # First: Find most common building_type
        cursor.execute("""
            SELECT 
                building_type,
                COUNT(*) as count
            FROM listings
            WHERE building_type IS NOT NULL
              AND lat IS NOT NULL
              AND lon IS NOT NULL
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                  ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                  %s
              )
            GROUP BY building_type
            ORDER BY count DESC
            LIMIT 1
        """, (lon, lat, radius_m))
        
        result = cursor.fetchone()
        
        # If nothing found in radius_m, try wider search (500m)
        if not result and radius_m < 500:
            cursor.execute("""
                SELECT 
                    building_type,
                    COUNT(*) as count
                FROM listings
                WHERE building_type IS NOT NULL
                  AND lat IS NOT NULL
                  AND lon IS NOT NULL
                  AND ST_DWithin(
                      ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                      ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                      500
                  )
                GROUP BY building_type
                ORDER BY count DESC
                LIMIT 1
            """, (lon, lat))
            
            result = cursor.fetchone()
            radius_m = 500
        
        if not result or not result['building_type']:
            cursor.close()
            conn.close()
            return None
        
        detected_type = result['building_type']
        
        # Second: Get source listings with this building_type (for verification)
        cursor.execute("""
            SELECT 
                id,
                url,
                address,
                building_type,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) as distance_m
            FROM listings
            WHERE building_type = %s
              AND lat IS NOT NULL
              AND lon IS NOT NULL
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                  ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                  %s
              )
            ORDER BY distance_m ASC
            LIMIT 5
        """, (lon, lat, detected_type, lon, lat, radius_m))
        
        sources = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            'building_type': detected_type,
            'sources': [
                {
                    'id': s['id'],
                    'url': s['url'],
                    'address': s['address'],
                    'distance_m': int(s['distance_m'])
                }
                for s in sources if s['url']  # Only include listings with URLs
            ][:3]  # Max 3 sources for verification
        }
    
    except Exception as e:
        print(f"Error finding building type: {e}")
        return None


def find_building_info_by_coordinates(lat: float, lon: float, radius_m: int = 50) -> Optional[dict]:
    """
    Auto-detect building info (floors, year, type) by finding listings in the same building.

    Search strategy:
    1. First look for exact match (within 10m) - same building entrance
    2. Then expand to 50m - same building complex
    3. If nothing found, try 150m - nearby buildings of same type

    Args:
        lat: Latitude
        lon: Longitude
        radius_m: Initial search radius (default 50m)

    Returns:
        Dict with 'total_floors', 'building_year', 'building_type', 'sources_count'
    """
    try:
        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Progressive search: start small, expand if needed
        search_radii = [10, 50, 150]  # meters
        rows = []

        for search_radius in search_radii:
            cursor.execute("""
                SELECT
                    total_floors,
                    house_year,
                    building_type,
                    address,
                    ST_Distance(
                        ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) as distance_m
                FROM listings
                WHERE lat IS NOT NULL
                  AND lon IS NOT NULL
                  AND (total_floors IS NOT NULL OR house_year IS NOT NULL)
                  AND ST_DWithin(
                      ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                      ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                      %s
                  )
                ORDER BY distance_m ASC
                LIMIT 10
            """, (lon, lat, lon, lat, search_radius))

            rows = cursor.fetchall()
            if rows:
                print(f"🏢 Found {len(rows)} listings with building info within {search_radius}m")
                break

        cursor.close()
        conn.close()

        if not rows:
            return None

        # Aggregate: most common total_floors, most common year
        floors_counts = {}
        years_counts = {}
        types_counts = {}

        for r in rows:
            if r['total_floors']:
                f = r['total_floors']
                floors_counts[f] = floors_counts.get(f, 0) + 1
            if r['house_year']:
                y = r['house_year']
                years_counts[y] = years_counts.get(y, 0) + 1
            if r['building_type']:
                t = r['building_type']
                types_counts[t] = types_counts.get(t, 0) + 1

        result = {
            'total_floors': max(floors_counts, key=floors_counts.get) if floors_counts else None,
            'building_year': max(years_counts, key=years_counts.get) if years_counts else None,
            'building_type': max(types_counts, key=types_counts.get) if types_counts else None,
            'sources_count': len(rows),
            'confidence': 'high' if len(rows) >= 3 else 'medium' if len(rows) >= 1 else 'low'
        }

        return result if any([result['total_floors'], result['building_year'], result['building_type']]) else None

    except Exception as e:
        print(f"Error finding building info: {e}")
        return None


def get_building_info_from_dadata(address: str) -> Optional[dict]:
    """
    Get building information from DaData Suggestions API by address.

    Note: DaData doesn't always have building info (floors, year).
    Returns dict with 'total_floors', 'building_year', 'building_type', 'fias_id'
    or None if not found.
    """
    if not DADATA_API_KEY:
        return None

    try:
        # Use Suggestions API (free, more reliable)
        url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {DADATA_API_KEY}"
        }

        response = requests.post(
            url,
            headers=headers,
            json={"query": address, "count": 1},
            timeout=5
        )

        if response.status_code != 200:
            print(f"DaData API error: {response.status_code}")
            return None

        data = response.json()
        suggestions = data.get('suggestions', [])
        if not suggestions:
            return None

        result = suggestions[0].get('data', {})

        # Extract building info (DaData often doesn't have this data)
        floors = result.get('floors_count')
        year = result.get('build_year')
        fias_id = result.get('house_fias_id')

        # Map DaData building type to our types
        building_type = None
        capital_marker = result.get('capital_marker')
        if capital_marker and capital_marker != '0':
            type_map = {
                '1': 'panel',      # панельный
                '2': 'brick',      # кирпичный
                '3': 'monolithic', # монолитный
                '4': 'block',      # блочный
                '5': 'wood',       # деревянный
            }
            building_type = type_map.get(str(capital_marker))

        if not floors and not year and not building_type:
            return None

        return {
            'total_floors': int(floors) if floors else None,
            'building_year': int(year) if year else None,
            'building_type': building_type,
            'fias_id': fias_id,
            'source': 'dadata',
            'confidence': 'medium' if (floors or year) else 'low'
        }

    except Exception as e:
        print(f"Error getting building info from DaData: {e}")
        return None


def geocode_address(address: str) -> Optional[dict]:
    """
    Geocode address using DaData Suggestions API (free tier: 10000/month).

    Returns dict with 'lat', 'lon', 'address_formatted', or None if not found.
    """
    if not DADATA_API_KEY:
        print("⚠️  DADATA_API_KEY not set, trying local DB search")
        return geocode_from_local_db(address)

    try:
        url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {DADATA_API_KEY}"
        }

        response = requests.post(
            url,
            headers=headers,
            json={"query": address, "count": 1},
            timeout=5
        )

        if response.status_code != 200:
            print(f"DaData geocode error: {response.status_code}")
            return geocode_from_local_db(address)

        data = response.json()
        suggestions = data.get('suggestions', [])
        if not suggestions:
            return geocode_from_local_db(address)

        result = suggestions[0].get('data', {})
        lat = result.get('geo_lat')
        lon = result.get('geo_lon')

        if not lat or not lon:
            return geocode_from_local_db(address)

        return {
            'lat': float(lat),
            'lon': float(lon),
            'address_formatted': suggestions[0].get('value'),
            'source': 'dadata'
        }

    except Exception as e:
        print(f"DaData geocode error: {e}")
        return geocode_from_local_db(address)


def geocode_from_local_db(address: str) -> Optional[dict]:
    """Fallback geocoder using local listings database."""
    import re

    try:
        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Normalize address
        addr = address.lower()
        addr = re.sub(r'\bул\.?\s*', '', addr)
        addr = re.sub(r'\bд\.?\s*', '', addr)
        addr = re.sub(r'\bдом\s*', '', addr)
        addr = re.sub(r'\bг\.?\s*', '', addr)
        addr = re.sub(r'\bмосква,?\s*', '', addr)
        addr = addr.strip(' ,')

        # Extract street and house number
        match = re.search(r'([а-яёА-ЯЁ\-\s]+?),?\s*(\d+)', addr)
        if match:
            street_name = match.group(1).strip()
            house_num = match.group(2)
            search_pattern = f'%{street_name}%{house_num}%'
        else:
            search_pattern = f'%{addr}%'

        cursor.execute("""
            SELECT lat, lon, address
            FROM listings
            WHERE address ILIKE %s
              AND lat IS NOT NULL
              AND lon IS NOT NULL
            ORDER BY last_seen DESC
            LIMIT 1
        """, (search_pattern,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result:
            return {
                'lat': float(result['lat']),
                'lon': float(result['lon']),
                'address_formatted': result['address'],
                'source': 'local_db'
            }

        return None

    except Exception as e:
        print(f"Local geocode error: {e}")
        return None


def parse_property_text(text: str) -> dict:
    """
    Parse property description text to extract parameters.

    Example inputs:
    - "2-комнатная квартира, 53.6 м2, 15 этаж, Москва, ул. Коцюбинского, дом 10"
    - "3к 78м2 5/17 Ленинский проспект 30"
    - "Студия 28 м², 3 этаж, ул. Тверская 12"

    Returns dict with: address, area, rooms, floor, total_floors
    """
    import re

    result = {
        'address': None,
        'area': None,
        'rooms': None,
        'floor': None,
        'total_floors': None,
        'raw_text': text
    }

    text_lower = text.lower()

    # === Extract rooms ===
    # "2-комнатная", "2к", "2 комн", "двухкомнатная"
    rooms_patterns = [
        (r'(\d+)\s*-?\s*комн', None),  # None means use captured group
        (r'(\d+)\s*к\b', None),
        (r'студия', 0),
        (r'однокомнатн', 1),
        (r'двухкомнатн', 2),
        (r'трехкомнатн', 3),
        (r'трёхкомнатн', 3),
        (r'четырехкомнатн', 4),
        (r'четырёхкомнатн', 4),
        (r'пятикомнатн', 5),
    ]

    for pattern, rooms_val in rooms_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if rooms_val is None:
                result['rooms'] = int(match.group(1))
            else:
                result['rooms'] = rooms_val
            break

    # === Extract area ===
    # "53.6 м2", "78 кв.м", "28 м²", "45.5м"
    area_patterns = [
        r'(\d+[.,]?\d*)\s*(?:м2|м²|кв\.?\s*м|метр)',
        r'(\d+[.,]?\d*)\s*м\b',
    ]

    for pattern in area_patterns:
        match = re.search(pattern, text_lower)
        if match:
            area_str = match.group(1).replace(',', '.')
            result['area'] = float(area_str)
            break

    # === Extract floor / total_floors ===
    # "5/17 этаж", "15 этаж", "5 из 9", "этаж 5/17"
    floor_patterns = [
        r'(\d+)\s*/\s*(\d+)\s*эт',
        r'(\d+)\s*из\s*(\d+)',
        r'эт\w*\s*(\d+)\s*/\s*(\d+)',
        r'(\d+)\s*/\s*(\d+)',  # just X/Y
        r'(\d+)\s*эт',  # just floor
    ]

    for pattern in floor_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if len(match.groups()) >= 2 and match.group(2):
                result['floor'] = int(match.group(1))
                result['total_floors'] = int(match.group(2))
            else:
                result['floor'] = int(match.group(1))
            break

    # === Extract address ===
    # Remove parsed parts and clean up
    addr_text = text

    # Remove common prefixes
    addr_text = re.sub(r'^объект:\s*', '', addr_text, flags=re.IGNORECASE)
    addr_text = re.sub(r'\d+\s*-?\s*комнатн\w*\s*квартир\w*,?\s*', '', addr_text, flags=re.IGNORECASE)
    addr_text = re.sub(r'квартир\w*,?\s*', '', addr_text, flags=re.IGNORECASE)
    addr_text = re.sub(r'студия,?\s*', '', addr_text, flags=re.IGNORECASE)

    # Remove area
    addr_text = re.sub(r'\d+[.,]?\d*\s*(?:м2|м²|кв\.?\s*м|метр\w*),?\s*', '', addr_text, flags=re.IGNORECASE)

    # Remove floor info
    addr_text = re.sub(r'\d+\s*/\s*\d+\s*эт\w*,?\s*', '', addr_text, flags=re.IGNORECASE)
    addr_text = re.sub(r'\d+\s*эт\w*,?\s*', '', addr_text, flags=re.IGNORECASE)

    # Clean up
    addr_text = re.sub(r'\s+', ' ', addr_text).strip(' ,.')

    if addr_text and len(addr_text) > 5:
        result['address'] = addr_text

    return result


def find_rosreestr_deals_nearby(
    lat: float,
    lon: float,
    radius_m: int = 2000,
    max_age_days: int = 365,
    limit: int = 20,
    target_year: Optional[int] = None,
    target_floors: Optional[int] = None,
    target_area: Optional[float] = None
) -> list:
    """
    Find Rosreestr (actual transaction) deals near given coordinates.

    Args:
        lat: Latitude
        lon: Longitude
        radius_m: Search radius in meters (default 2000m)
        max_age_days: Maximum deal age in days (default 365 = 1 year)
        limit: Maximum number of deals to return
        target_year: Building year of target property (for class filtering)
        target_floors: Total floors of target building (for class filtering)
        target_area: Area of target property (for area filtering)

    Returns:
        List of deals with distance, price, area, etc. Filtered by building class if params provided.
    """
    try:
        from datetime import datetime, timedelta

        conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        cursor.execute("""
            SELECT
                id,
                street,
                deal_date,
                deal_price,
                price_per_sqm,
                area,
                floor,
                year_build,
                wall_material,
                lat,
                lon,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) as distance_m
            FROM rosreestr_deals
            WHERE lat IS NOT NULL
              AND lon IS NOT NULL
              AND deal_price > 0
              AND area > 0
              AND deal_date >= %s
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                  ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                  %s
              )
            ORDER BY distance_m ASC
            LIMIT %s
        """, (lon, lat, cutoff_date, lon, lat, radius_m, limit * 3))  # Get more for filtering

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Apply building class filtering (similar to knn_searcher._filter_by_building_class)
        filtered = []
        for r in results:
            comp_year = r['year_build']

            comp_area = float(r['area']) if r['area'] else None

            # === Фильтрация по минимальной площади ===
            # Исключаем слишком маленькие объекты (кладовки, машиноместа)
            if comp_area and comp_area < 20:
                continue

            # === Фильтрация по году постройки ===
            if target_year and comp_year:
                # Современный дом (2000+) - исключаем советскую застройку
                if target_year >= 2000:
                    if comp_year < 1990:
                        continue
                # Советский дом (до 1990) - исключаем современные
                elif target_year < 1990:
                    if comp_year >= 2000:
                        continue

            # === Фильтрация по площади (±50%) ===
            # Мягкая фильтрация - исключаем только сильно отличающиеся
            if target_area and comp_area:
                area_ratio = comp_area / target_area
                if area_ratio < 0.5 or area_ratio > 1.5:
                    continue

            filtered.append(r)

        # Если осталось мало - вернуть все (лучше неточные, чем никаких)
        if len(filtered) < 3 and len(results) >= 3:
            filtered = results

        # Limit after filtering
        filtered = filtered[:limit]

        return [
            {
                'id': r['id'],
                'address': r['street'] or 'Адрес не указан',
                'deal_date': r['deal_date'].isoformat() if r['deal_date'] else None,
                'deal_price': float(r['deal_price']),
                'price_per_sqm': float(r['price_per_sqm']) if r['price_per_sqm'] else None,
                'area': float(r['area']),
                'floor': r['floor'],
                'year_build': r['year_build'],
                'wall_material': r['wall_material'],
                'lat': r['lat'],
                'lon': r['lon'],
                'distance_m': int(r['distance_m']),
                'source': 'rosreestr',
                'filtered_by_class': target_year is not None or target_floors is not None
            }
            for r in filtered
        ]

    except Exception as e:
        print(f"Error finding Rosreestr deals: {e}")
        return []

