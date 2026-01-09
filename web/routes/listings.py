"""Routes for viewing CIAN listings."""
from flask import Blueprint, render_template, jsonify, request
import psycopg2
from psycopg2.extras import DictCursor

from utils.db import get_db_connection

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
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 500)  # Max 500
    rooms = request.args.get('rooms', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_area = request.args.get('min_area', type=float)
    max_area = request.args.get('max_area', type=float)
    has_encumbrances = request.args.get('has_encumbrances')
    is_hot_lead = request.args.get('is_hot_lead')
    sort = request.args.get('sort', 'date_desc')

    offset = (page - 1) * per_page

    # Build query
    where_clauses = ["l.is_active = TRUE"]
    params = {}
    join_hot_leads = ""

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

    has_errors = request.args.get('has_errors')
    if has_errors == 'true':
        where_clauses.append("l.is_error = TRUE")

    if is_hot_lead == 'true':
        join_hot_leads = "JOIN hot_leads hl ON hl.listing_id = l.id"
        where_clauses.append("hl.status != 'closed'")

    where_sql = " AND ".join(where_clauses)

    # Sort options - date_desc sorts by first_seen (when added), newest first
    sort_options = {
        'price_asc': 'lp.price ASC',
        'price_desc': 'lp.price DESC',
        'area_asc': 'l.area_total ASC',
        'area_desc': 'l.area_total DESC',
        'date_desc': 'l.first_seen DESC',
        'date_asc': 'l.first_seen ASC',
    }
    order_by = sort_options.get(sort, 'l.first_seen DESC')

    # Hot leads fields for SELECT
    hot_leads_select = ""
    if is_hot_lead == 'true':
        hot_leads_select = """,
            hl.alert_level,
            hl.lead_score,
            hl.deviation_from_median_pct,
            hl.status as lead_status"""

    query = f"""
        SELECT
            l.id,
            l.url,
            l.rooms,
            l.area_total,
            l.floor,
            l.address,
            l.description,
            l.seller_type,
            l.lat,
            l.lon,
            l.first_seen,
            lp.price,
            CASE
                WHEN l.area_total > 0 THEN ROUND(lp.price / l.area_total, 0)
                ELSE NULL
            END AS price_per_sqm,
            l.last_seen,
            l.has_encumbrances,
            l.encumbrance_types,
            l.encumbrance_confidence
            {hot_leads_select}
        FROM listings l
        {join_hot_leads}
        JOIN LATERAL (
            SELECT price
            FROM listing_prices
            WHERE id = l.id
            ORDER BY seen_at DESC
            LIMIT 1
        ) lp ON true
        WHERE {where_sql}
        ORDER BY {order_by}
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
                {join_hot_leads}
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

            # Price stats for active listings
            cur.execute("""
                SELECT
                    ROUND(AVG(lp.price), 0) AS avg,
                    MIN(lp.price) AS min,
                    MAX(lp.price) AS max
                FROM listings l
                JOIN LATERAL (
                    SELECT price
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) lp ON true
                WHERE l.is_active = TRUE
            """)
            price_stats = dict(cur.fetchone())

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
                'price_stats': price_stats,
                'by_rooms': by_rooms,
            })
    finally:
        conn.close()


@bp.route('/api/detail/<int:listing_id>')
def api_detail(listing_id):
    """Get detailed listing information with photos."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Get listing details
            cur.execute("""
                SELECT
                    l.*,
                    lp.price,
                    CASE
                        WHEN l.area_total > 0 THEN ROUND(lp.price / l.area_total, 0)
                        ELSE NULL
                    END AS price_per_sqm
                FROM listings l
                JOIN LATERAL (
                    SELECT price
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) lp ON true
                WHERE l.id = %s
            """, (listing_id,))

            row = cur.fetchone()
            if not row:
                return jsonify({'error': 'Listing not found'}), 404

            listing = dict(row)

            # Get photos
            cur.execute("""
                SELECT photo_url, photo_order, width, height
                FROM listing_photos
                WHERE listing_id = %s
                ORDER BY photo_order
            """, (listing_id,))
            photos = [dict(row) for row in cur.fetchall()]

            return jsonify({
                'listing': listing,
                'photos': photos
            })
    finally:
        conn.close()


@bp.route('/api/mark_error', methods=['POST'])
def api_mark_error():
    """Mark listing as error."""
    data = request.get_json()
    listing_id = data.get('listing_id')
    error_reason = data.get('error_reason', '')

    if not listing_id:
        return jsonify({'error': 'listing_id required'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET is_error = TRUE, error_reason = %s
                WHERE id = %s
            """, (error_reason, listing_id))
            conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@bp.route('/api/mark_contacted', methods=['POST'])
def api_mark_contacted():
    """Mark listing as contacted."""
    data = request.get_json()
    listing_id = data.get('listing_id')

    if not listing_id:
        return jsonify({'error': 'listing_id required'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET is_contacted = TRUE, contacted_at = NOW()
                WHERE id = %s
            """, (listing_id,))
            conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@bp.route('/api/send_to_telegram', methods=['POST'])
def api_send_to_telegram():
    """Send listing to Telegram."""
    data = request.get_json()
    listing_id = data.get('listing_id')
    comment = data.get('comment', '')

    if not listing_id:
        return jsonify({'error': 'listing_id required'}), 400

    # TODO: Implement actual Telegram sending
    # For now, just mark as sent
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET sent_to_telegram = TRUE, telegram_sent_at = NOW()
                WHERE id = %s
            """, (listing_id,))
            conn.commit()
        return jsonify({'success': True, 'message': 'Marked as sent to Telegram'})
    finally:
        conn.close()
