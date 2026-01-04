"""Routes for viewing CIAN listings."""
from flask import Blueprint, render_template, jsonify, request
import psycopg2
from psycopg2.extras import DictCursor

from web.utils.db import get_db_connection

bp = Blueprint('listings', __name__, url_prefix='/listings')


@bp.route('/')
def index():
    """Listings browser page."""
    return render_template('listings.html')


@bp.route('/api/list')
def api_list():
    """Get listings with filters."""
    # Parse filters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    rooms = request.args.get('rooms', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_area = request.args.get('min_area', type=float)
    max_area = request.args.get('max_area', type=float)
    has_encumbrances = request.args.get('has_encumbrances')

    offset = (page - 1) * per_page

    # Build query
    where_clauses = ["l.is_active = TRUE"]
    params = {}
    
    if rooms is not None:
        where_clauses.append("l.rooms = %(rooms)s")
        params['rooms'] = rooms
    
    if min_price is not None:
        where_clauses.append("lp.price >= %(min_price)s")
        params['min_price'] = min_price
    
    if max_price is not None:
        where_clauses.append("lp.price <= %(max_price)s")
        params['max_price'] = max_price
    
    if min_area is not None:
        where_clauses.append("l.area_total >= %(min_area)s")
        params['min_area'] = min_area
    
    if max_area is not None:
        where_clauses.append("l.area_total <= %(max_area)s")
        params['max_area'] = max_area

    if has_encumbrances == 'true':
        where_clauses.append("l.has_encumbrances = TRUE")

    where_sql = " AND ".join(where_clauses)
    
    query = f"""
        SELECT
            l.id,
            l.url,
            l.rooms,
            l.area_total,
            l.floor,
            l.address,
            l.seller_type,
            l.lat,
            l.lon,
            lp.price,
            CASE
                WHEN l.area_total > 0 THEN ROUND(lp.price / l.area_total, 0)
                ELSE NULL
            END AS price_per_sqm,
            l.last_seen,
            l.has_encumbrances,
            l.encumbrance_types,
            l.encumbrance_confidence
        FROM listings l
        JOIN LATERAL (
            SELECT price
            FROM listing_prices
            WHERE id = l.id
            ORDER BY seen_at DESC
            LIMIT 1
        ) lp ON true
        WHERE {where_sql}
        ORDER BY l.last_seen DESC
        LIMIT %(per_page)s OFFSET %(offset)s
    """
    
    params['per_page'] = per_page
    params['offset'] = offset
    
    # Execute query
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(query, params)
            listings = [dict(row) for row in cur.fetchall()]
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*)
                FROM listings l
                JOIN LATERAL (
                    SELECT price
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) lp ON true
                WHERE {where_sql}
            """
            cur.execute(count_query, params)
            total = cur.fetchone()[0]
        
        return jsonify({
            'listings': listings,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page,
        })
    finally:
        conn.close()


@bp.route('/api/stats')
def api_stats():
    """Get statistics."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Overall stats
            cur.execute("""
                SELECT
                    COUNT(*) AS total_listings,
                    COUNT(*) FILTER (WHERE is_active = TRUE) AS active_listings,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND has_encumbrances = TRUE) AS with_encumbrances,
                    MIN(first_seen) AS first_scrape,
                    MAX(last_seen) AS last_scrape
                FROM listings
            """)
            overall = dict(cur.fetchone())
            
            # By rooms
            cur.execute("""
                SELECT 
                    rooms,
                    COUNT(*) AS count,
                    ROUND(AVG(area_total), 1) AS avg_area,
                    ROUND(AVG(lp.price), 0) AS avg_price
                FROM listings l
                JOIN LATERAL (
                    SELECT price
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) lp ON true
                WHERE l.is_active = TRUE
                    AND l.area_total > 0
                GROUP BY rooms
                ORDER BY rooms
            """)
            by_rooms = [dict(row) for row in cur.fetchall()]
            
            return jsonify({
                'overall': overall,
                'by_rooms': by_rooms,
            })
    finally:
        conn.close()

