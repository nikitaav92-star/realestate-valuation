"""
Map API endpoints for interactive district map.

Provides district boundaries and aggregated statistics for visualization.
"""
from flask import Blueprint, jsonify, request
import psycopg2
import psycopg2.extras
import json

from web.utils.db import get_db

map_bp = Blueprint('map', __name__, url_prefix='/api/map')


@map_bp.route('/districts', methods=['GET'])
def get_districts_with_aggregates():
    """
    Get all districts with aggregated statistics for the map.

    Query parameters:
    - date: Date for aggregates (default: today)

    Response:
    {
        "districts": [
            {
                "district_id": 1,
                "name": "Пресненский",
                "full_name": "Москва, ЦАО, р-н Пресненский",
                "avg_price_per_sqm": 350000,
                "median_price_per_sqm": 320000,
                "total_listings": 150,
                "min_price": 5000000,
                "max_price": 50000000,
                "center": [55.76, 37.58],
                "coordinates": [[[lat, lon], ...]]  # GeoJSON format
            },
            ...
        ]
    }
    """
    target_date = request.args.get('date', 'CURRENT_DATE')

    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Use parameter binding safely
        if target_date == 'CURRENT_DATE':
            date_condition = "a.date = CURRENT_DATE"
            params = []
        else:
            date_condition = "a.date = %s"
            params = [target_date]

        query = f"""
            SELECT
                d.district_id,
                d.name,
                d.full_name,
                d.center_lat,
                d.center_lon,
                ST_AsGeoJSON(d.geometry) as geometry,
                a.avg_price_per_sqm,
                a.median_price_per_sqm,
                a.total_listings,
                a.min_price,
                a.max_price,
                a.avg_area,
                a.avg_rooms
            FROM districts d
            LEFT JOIN district_aggregates a
                ON d.district_id = a.district_id
                AND {date_condition}
            WHERE d.geometry IS NOT NULL
            ORDER BY d.name
        """

        cursor.execute(query, params)

        districts = []
        for row in cursor.fetchall():
            geometry = json.loads(row['geometry']) if row['geometry'] else None

            districts.append({
                'district_id': row['district_id'],
                'name': row['name'],
                'full_name': row['full_name'],
                'center': [row['center_lat'], row['center_lon']] if row['center_lat'] and row['center_lon'] else None,
                'coordinates': geometry['coordinates'] if geometry else None,
                'avg_price_per_sqm': float(row['avg_price_per_sqm']) if row['avg_price_per_sqm'] else None,
                'median_price_per_sqm': float(row['median_price_per_sqm']) if row['median_price_per_sqm'] else None,
                'total_listings': row['total_listings'],
                'min_price': float(row['min_price']) if row['min_price'] else None,
                'max_price': float(row['max_price']) if row['max_price'] else None,
                'avg_area': float(row['avg_area']) if row['avg_area'] else None,
                'avg_rooms': float(row['avg_rooms']) if row['avg_rooms'] else None,
            })

        cursor.close()
        conn.close()

        return jsonify({
            'districts': districts,
            'total': len(districts)
        })

    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'error': str(e)}), 500


@map_bp.route('/districts/<int:district_id>/listings', methods=['GET'])
def get_district_listings(district_id):
    """
    Get listings for a specific district.

    Query parameters:
    - limit: Maximum number of listings (default: 50)
    - sort: Sort field (price_per_sqm, price, area) (default: price_per_sqm)
    - order: Sort order (asc, desc) (default: asc)

    Response:
    {
        "listings": [
            {
                "id": 123,
                "url": "https://...",
                "address": "...",
                "price": 5000000,
                "area": 45.0,
                "rooms": 2,
                "price_per_sqm": 111111,
                "lat": 55.76,
                "lon": 37.58
            },
            ...
        ]
    }
    """
    limit = int(request.args.get('limit', 50))
    sort = request.args.get('sort', 'price_per_sqm')
    order = request.args.get('order', 'asc')

    # Validate parameters
    if sort not in ['price_per_sqm', 'price', 'area']:
        sort = 'price_per_sqm'
    if order not in ['asc', 'desc']:
        order = 'asc'

    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Construct sort clause
        if sort == 'price_per_sqm':
            sort_clause = f"(p.price / NULLIF(l.area_total, 0)) {order.upper()}"
        elif sort == 'price':
            sort_clause = f"p.price {order.upper()}"
        else:
            sort_clause = f"l.area_total {order.upper()}"

        query = f"""
            WITH latest_prices AS (
                SELECT DISTINCT ON (lp.id)
                    lp.id,
                    lp.price
                FROM listing_prices lp
                ORDER BY lp.id, lp.seen_at DESC
            )
            SELECT
                l.id,
                l.url,
                l.address_full,
                p.price,
                l.area_total,
                l.rooms,
                l.lat,
                l.lon,
                l.floor,
                l.total_floors,
                ROUND((p.price / NULLIF(l.area_total, 0))::numeric, 2) as price_per_sqm
            FROM listings l
            JOIN latest_prices p ON p.id = l.id
            WHERE l.district_id = %s
              AND l.is_active = TRUE
              AND p.price > 0
              AND l.area_total > 0
            ORDER BY {sort_clause}
            LIMIT %s
        """

        cursor.execute(query, (district_id, limit))

        listings = []
        for row in cursor.fetchall():
            listings.append({
                'id': row['id'],
                'url': row['url'],
                'address': row['address_full'],
                'price': float(row['price']) if row['price'] else None,
                'area': float(row['area_total']) if row['area_total'] else None,
                'rooms': row['rooms'],
                'lat': row['lat'],
                'lon': row['lon'],
                'floor': row['floor'],
                'total_floors': row['total_floors'],
                'price_per_sqm': float(row['price_per_sqm']) if row['price_per_sqm'] else None,
            })

        cursor.close()
        conn.close()

        return jsonify({
            'listings': listings,
            'total': len(listings)
        })

    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'error': str(e)}), 500


@map_bp.route('/stats', methods=['GET'])
def get_map_stats():
    """
    Get overall map statistics.

    Response:
    {
        "total_districts": 132,
        "districts_with_data": 12,
        "total_listings": 100,
        "avg_price_per_sqm": 265454,
        "price_range": [141221, 576087]
    }
    """
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM districts) as total_districts,
                COUNT(DISTINCT a.district_id) as districts_with_data,
                SUM(a.total_listings) as total_listings,
                ROUND(AVG(a.avg_price_per_sqm)::numeric, 0) as avg_price_per_sqm,
                ROUND(MIN(a.avg_price_per_sqm)::numeric, 0) as min_price_per_sqm,
                ROUND(MAX(a.avg_price_per_sqm)::numeric, 0) as max_price_per_sqm
            FROM district_aggregates a
            WHERE a.date = CURRENT_DATE
        """)

        stats = cursor.fetchone()
        cursor.close()
        conn.close()

        return jsonify({
            'total_districts': stats['total_districts'],
            'districts_with_data': stats['districts_with_data'],
            'total_listings': stats['total_listings'],
            'avg_price_per_sqm': float(stats['avg_price_per_sqm']) if stats['avg_price_per_sqm'] else None,
            'price_range': [
                float(stats['min_price_per_sqm']) if stats['min_price_per_sqm'] else None,
                float(stats['max_price_per_sqm']) if stats['max_price_per_sqm'] else None
            ]
        })

    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'error': str(e)}), 500


@map_bp.route('/district/<int:district_id>', methods=['GET'])
def get_district_info(district_id):
    """
    Get detailed information about a specific district.

    Response:
    {
        "district_id": 1,
        "name": "Пресненский",
        "full_name": "Москва, ЦАО, р-н Пресненский",
        "statistics": {
            "avg_price_per_sqm": 350000,
            "total_listings": 150,
            ...
        }
    }
    """
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT
                d.district_id,
                d.name,
                d.full_name,
                d.center_lat,
                d.center_lon,
                a.avg_price_per_sqm,
                a.median_price_per_sqm,
                a.total_listings,
                a.min_price,
                a.max_price,
                a.avg_area,
                a.avg_rooms
            FROM districts d
            LEFT JOIN district_aggregates a
                ON d.district_id = a.district_id
                AND a.date = CURRENT_DATE
            WHERE d.district_id = %s
        """, (district_id,))

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return jsonify({'error': 'District not found'}), 404

        return jsonify({
            'district_id': row['district_id'],
            'name': row['name'],
            'full_name': row['full_name'],
            'center': [row['center_lat'], row['center_lon']] if row['center_lat'] else None,
            'statistics': {
                'avg_price_per_sqm': float(row['avg_price_per_sqm']) if row['avg_price_per_sqm'] else None,
                'median_price_per_sqm': float(row['median_price_per_sqm']) if row['median_price_per_sqm'] else None,
                'total_listings': row['total_listings'],
                'min_price': float(row['min_price']) if row['min_price'] else None,
                'max_price': float(row['max_price']) if row['max_price'] else None,
                'avg_area': float(row['avg_area']) if row['avg_area'] else None,
                'avg_rooms': float(row['avg_rooms']) if row['avg_rooms'] else None,
            }
        })

    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'error': str(e)}), 500
