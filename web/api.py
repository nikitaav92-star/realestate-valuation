"""
API для управления объявлениями, обременениями и ошибками.
"""
from flask import Flask, jsonify, request, render_template
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import Optional, Dict, List

from web.utils.db import get_db

app = Flask(__name__)


@app.route('/')
def index():
    """Главная страница."""
    return render_template('index.html')


@app.route('/map')
def map_view():
    """Интерактивная карта недвижимости."""
    return render_template('map.html')


@app.route('/api/listings', methods=['GET'])
def get_listings():
    """
    Получить список объявлений с фильтрами.
    
    Query параметры:
    - has_encumbrances: true/false
    - is_error: true/false
    - limit: int (default 50)
    - offset: int (default 0)
    """
    has_encumbrances = request.args.get('has_encumbrances')
    is_error = request.args.get('is_error')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Построить WHERE clause
    where_clauses = ["is_active = TRUE"]
    params = []
    
    if has_encumbrances is not None:
        where_clauses.append("has_encumbrances = %s")
        params.append(has_encumbrances == 'true')
    
    if is_error is not None:
        where_clauses.append("is_error = %s")
        params.append(is_error == 'true')
    
    where_clause = " AND ".join(where_clauses)
    
    # Запрос
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
        ORDER BY l.id DESC
        LIMIT %s OFFSET %s
    """
    
    params.extend([limit, offset])
    
    cur.execute(query, params)
    listings = cur.fetchall()
    
    # Подсчитать общее количество
    count_query = f"SELECT COUNT(*) as total FROM listings WHERE {where_clause}"
    cur.execute(count_query, params[:-2])  # Без limit/offset
    total = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return jsonify({
        'listings': [dict(row) for row in listings],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@app.route('/api/listings/<int:listing_id>', methods=['GET'])
def get_listing(listing_id):
    """Получить детали объявления."""
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


@app.route('/api/listings/<int:listing_id>/mark_error', methods=['POST'])
def mark_listing_error(listing_id):
    """
    Пометить объявление как ошибку.
    
    Body JSON:
    {
        "error_reason": "wrong_property_type | parsing_error | duplicate | other",
        "error_comment": "Комментарий для будущих правок"
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


@app.route('/api/listings/<int:listing_id>/unmark_error', methods=['POST'])
def unmark_listing_error(listing_id):
    """Снять пометку ошибки с объявления."""
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


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Получить статистику."""
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
    
    # Статистика по типам обременений
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


@app.route('/api/encumbrances', methods=['GET'])
def get_encumbrances():
    """Получить список объявлений с обременениями."""
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


# Register map API blueprint
from api_map import map_bp
app.register_blueprint(map_bp)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

