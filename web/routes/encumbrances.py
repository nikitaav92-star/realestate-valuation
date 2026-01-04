"""
Routes for encumbrance management (обременения).

This module provides endpoints for viewing and managing listings with encumbrances
(registered people, mortgages, evictions, etc.)
"""
from flask import Blueprint, render_template, jsonify, request
import psycopg2
import psycopg2.extras

from web.utils.db import get_db

bp = Blueprint('encumbrances', __name__, url_prefix='/encumbrances')


@bp.route('/')
def index():
    """Encumbrance management page."""
    return render_template('encumbrances.html')


@bp.route('/api/listings', methods=['GET'])
def get_listings():
    """
    Get listings with filters for encumbrances and errors.

    Query parameters:
    - has_encumbrances: true/false
    - is_error: true/false
    - sort_by: date (default) | price | confidence
    - period: all | today | week | month
    - limit: int (default 50)
    - offset: int (default 0)
    """
    has_encumbrances = request.args.get('has_encumbrances')
    is_error = request.args.get('is_error')
    sort_by = request.args.get('sort_by', 'date')
    period = request.args.get('period', 'all')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build WHERE clause
    where_clauses = ["is_active = TRUE"]
    params = []

    if has_encumbrances is not None:
        where_clauses.append("has_encumbrances = %s")
        params.append(has_encumbrances == 'true')

    if is_error is not None:
        where_clauses.append("is_error = %s")
        params.append(is_error == 'true')

    # Period filter
    if period == 'today':
        where_clauses.append("first_seen >= CURRENT_DATE")
    elif period == 'week':
        where_clauses.append("first_seen >= CURRENT_DATE - INTERVAL '7 days'")
    elif period == 'month':
        where_clauses.append("first_seen >= CURRENT_DATE - INTERVAL '30 days'")

    where_clause = " AND ".join(where_clauses)

    # Sort order - for encumbrances sort by date (newest first)
    if sort_by == 'price':
        order_clause = "price_current DESC NULLS LAST"
    elif sort_by == 'confidence':
        order_clause = "l.encumbrance_confidence DESC NULLS LAST, l.first_seen DESC"
    else:  # date (default)
        order_clause = "l.first_seen DESC"

    # Query
    query = f"""
        SELECT
            l.id,
            l.url,
            l.address,
            l.address_full,
            l.description,
            (SELECT price FROM listing_prices WHERE id = l.id ORDER BY seen_at DESC LIMIT 1) as price_current,
            l.rooms,
            l.area_total,
            l.floor,
            l.has_encumbrances,
            l.encumbrance_types,
            l.encumbrance_confidence,
            l.is_error,
            l.error_reason,
            l.error_comment,
            l.marked_by,
            l.marked_at,
            l.first_seen,
            l.last_seen,
            (SELECT COUNT(*) FROM listing_photos WHERE listing_id = l.id) as photos_count
        FROM listings l
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT %s OFFSET %s
    """
    
    params.extend([limit, offset])
    
    cur.execute(query, params)
    listings = cur.fetchall()
    
    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM listings WHERE {where_clause}"
    cur.execute(count_query, params[:-2])  # Without limit/offset
    total = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return jsonify({
        'listings': [dict(row) for row in listings],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@bp.route('/api/listings/<int:listing_id>', methods=['GET'])
def get_listing(listing_id):
    """Get listing details."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute(
        """
        SELECT l.*,
            (SELECT price FROM listing_prices WHERE id = l.id ORDER BY seen_at DESC LIMIT 1) as price_current,
            (SELECT json_agg(json_build_object(
                'url', photo_url,
                'order', photo_order,
                'width', width,
                'height', height
            ) ORDER BY photo_order)
            FROM listing_photos
            WHERE listing_id = l.id) as photos
        FROM listings l
        WHERE l.id = %s
        """,
        (listing_id,)
    )
    
    listing = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if not listing:
        return jsonify({'error': 'Listing not found'}), 404
    
    return jsonify(dict(listing))


@bp.route('/api/listings/<int:listing_id>/mark_error', methods=['POST'])
def mark_listing_error(listing_id):
    """
    Mark listing as error.
    
    Body JSON:
    {
        "error_reason": "wrong_property_type | parsing_error | duplicate | other",
        "error_comment": "Comment for future fixes"
    }
    """
    data = request.json
    
    if not data or 'error_reason' not in data:
        return jsonify({'error': 'error_reason is required'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE listings
        SET
            is_error = TRUE,
            error_reason = %s,
            error_comment = %s,
            marked_by = 'user',
            marked_at = NOW()
        WHERE id = %s
        """,
        (
            data['error_reason'],
            data.get('error_comment'),
            listing_id
        )
    )
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Listing marked as error'})


@bp.route('/api/listings/<int:listing_id>/unmark_error', methods=['POST'])
def unmark_listing_error(listing_id):
    """Remove error mark from listing."""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE listings
        SET
            is_error = FALSE,
            error_reason = NULL,
            error_comment = NULL,
            marked_by = NULL,
            marked_at = NULL
        WHERE id = %s
        """,
        (listing_id,)
    )
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Error mark removed'})


@bp.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute(
        """
        SELECT
            COUNT(*) as total_listings,
            COUNT(*) FILTER (WHERE is_active = TRUE) as active_listings,
            COUNT(*) FILTER (WHERE has_encumbrances = TRUE) as with_encumbrances,
            COUNT(*) FILTER (WHERE is_error = TRUE) as marked_as_error,
            COUNT(*) FILTER (WHERE address_full IS NOT NULL) as with_full_address,
            COUNT(*) FILTER (WHERE description IS NOT NULL AND LENGTH(description) > 50) as with_description,
            (SELECT COUNT(*) FROM listing_photos) as total_photos
        FROM listings
        WHERE is_active = TRUE
        """
    )
    
    stats = cur.fetchone()
    
    # Statistics by encumbrance types
    cur.execute(
        """
        SELECT
            UNNEST(encumbrance_types) as encumbrance_type,
            COUNT(*) as count
        FROM listings
        WHERE is_active = TRUE AND has_encumbrances = TRUE
        GROUP BY encumbrance_type
        ORDER BY count DESC
        """
    )
    
    encumbrance_stats = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return jsonify({
        'overview': dict(stats),
        'encumbrance_types': [dict(row) for row in encumbrance_stats],
    })


@bp.route('/api/encumbrances/list', methods=['GET'])
def get_encumbrances():
    """Get list of listings with encumbrances."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    
    cur.execute(
        """
        SELECT 
            l.id,
            l.url,
            l.address_full,
            l.description,
            l.encumbrance_types,
            l.encumbrance_confidence,
            l.encumbrance_details,
            (SELECT price FROM listing_prices WHERE id = l.id ORDER BY seen_at DESC LIMIT 1) as price_current,
            l.first_seen
        FROM listings l
        WHERE l.is_active = TRUE AND l.has_encumbrances = TRUE
        ORDER BY l.encumbrance_confidence DESC, l.id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset)
    )
    
    listings = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return jsonify({
        'listings': [dict(row) for row in listings],
    })

