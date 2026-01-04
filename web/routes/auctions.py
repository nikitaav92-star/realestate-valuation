"""
Routes for auction lots management (торги).

This module provides endpoints for viewing auction lots from:
- FSSP (Federal Bailiff Service) - enforcement auctions
- Bankruptcy (Fedresurs) - bankruptcy sales
- Bank Pledges - bank collateral sales
- DGI Moscow - city property auctions

IMPORTANT: Uses SEPARATE database from main realestate DB!
"""

import os
from flask import Blueprint, render_template, jsonify, request
import psycopg2
import psycopg2.extras

bp = Blueprint('auctions', __name__, url_prefix='/auctions')


def get_auctions_db():
    """
    Get database connection for AUCTIONS database.
    SEPARATE from main realestate DB!
    """
    dsn = os.getenv("AUCTIONS_DATABASE_URL") or os.getenv("AUCTIONS_PG_DSN") or (
        f"postgresql://{os.getenv('PG_USER', 'realuser')}:"
        f"{os.getenv('PG_PASS', 'strongpass123')}@"
        f"{os.getenv('PG_HOST', 'localhost')}:"
        f"{os.getenv('AUCTIONS_PG_PORT', '5433')}/"  # Different port!
        f"{os.getenv('AUCTIONS_PG_DB', 'auctionsdb')}"
    )
    return psycopg2.connect(dsn)


@bp.route('/')
def index():
    """Auctions management page."""
    return render_template('auctions.html')


@bp.route('/api/lots', methods=['GET'])
def get_lots():
    """
    Get auction lots with filters.

    Query parameters:
    - source: fssp | bankrupt | bank_pledge | dgi_moscow | all
    - status: announced | active | completed | all
    - city: string
    - min_discount: float (minimum discount from market)
    - sort_by: date | price | discount
    - limit: int (default 50)
    - offset: int (default 0)
    """
    source = request.args.get('source', 'all')
    status = request.args.get('status', 'all')
    city = request.args.get('city')
    min_discount = request.args.get('min_discount', type=float)
    sort_by = request.args.get('sort_by', 'date')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    conn = get_auctions_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build WHERE clause
    where_clauses = []
    params = []
    param_idx = 1

    if source != 'all':
        where_clauses.append(f"l.source_type = ${param_idx}")
        params.append(source)
        param_idx += 1

    if status != 'all':
        if status == 'active':
            where_clauses.append("l.status IN ('announced', 'active')")
        else:
            where_clauses.append(f"l.status = ${param_idx}")
            params.append(status)
            param_idx += 1

    if city:
        where_clauses.append(f"l.city ILIKE ${param_idx}")
        params.append(f"%{city}%")
        param_idx += 1

    if min_discount:
        where_clauses.append(f"mc.discount_from_market >= ${param_idx}")
        params.append(min_discount)
        param_idx += 1

    where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

    # Sort order
    order_map = {
        'date': 'l.auction_date ASC NULLS LAST',
        'price': 'l.current_price ASC NULLS LAST',
        'discount': 'mc.discount_from_market DESC NULLS LAST',
    }
    order_clause = order_map.get(sort_by, order_map['date'])

    # Query
    query = f"""
        SELECT
            l.id,
            l.external_id,
            l.source_type,
            l.source_url,
            l.lot_number,
            l.property_type,
            l.title,
            l.address,
            l.city,
            l.district,
            l.area_total,
            l.rooms,
            l.floor,
            l.total_floors,
            l.initial_price,
            l.current_price,
            l.price_per_sqm,
            l.auction_date,
            l.application_deadline,
            l.status,
            l.is_repeat_auction,
            l.repeat_number,
            l.organizer_name,
            l.debtor_name,
            l.bank_name,
            l.photos,
            l.first_seen_at,
            p.name as platform_name,
            mc.market_price_estimate,
            mc.discount_from_market,
            mc.comparables_count
        FROM auction_lots l
        LEFT JOIN auction_platforms p ON l.platform_id = p.id
        LEFT JOIN auction_market_comparison mc ON l.id = mc.lot_id
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """

    params.extend([limit, offset])

    cur.execute(query, params)
    lots = cur.fetchall()

    # Get total count
    count_query = f"""
        SELECT COUNT(*) as total
        FROM auction_lots l
        LEFT JOIN auction_market_comparison mc ON l.id = mc.lot_id
        WHERE {where_clause}
    """
    cur.execute(count_query, params[:-2])
    total = cur.fetchone()['total']

    cur.close()
    conn.close()

    return jsonify({
        'lots': [dict(row) for row in lots],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@bp.route('/api/lots/<int:lot_id>', methods=['GET'])
def get_lot(lot_id):
    """Get lot details."""
    conn = get_auctions_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT
            l.*,
            p.name as platform_name,
            mc.market_price_estimate,
            mc.market_price_per_sqm,
            mc.discount_from_market,
            mc.estimation_method,
            mc.estimation_confidence,
            mc.comparables_count
        FROM auction_lots l
        LEFT JOIN auction_platforms p ON l.platform_id = p.id
        LEFT JOIN auction_market_comparison mc ON l.id = mc.lot_id
        WHERE l.id = %s
        """,
        (lot_id,)
    )

    lot = cur.fetchone()

    if lot:
        # Get price history
        cur.execute(
            """
            SELECT price, price_type, recorded_at
            FROM auction_price_history
            WHERE lot_id = %s
            ORDER BY recorded_at DESC
            LIMIT 20
            """,
            (lot_id,)
        )
        lot['price_history'] = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    if not lot:
        return jsonify({'error': 'Lot not found'}), 404

    return jsonify(dict(lot))


@bp.route('/api/stats', methods=['GET'])
def get_stats():
    """Get auction statistics."""
    conn = get_auctions_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Overall stats
    cur.execute(
        """
        SELECT
            COUNT(*) as total_lots,
            COUNT(*) FILTER (WHERE status IN ('announced', 'active')) as active_lots,
            COUNT(*) FILTER (WHERE status = 'completed') as completed_lots,
            AVG(current_price) FILTER (WHERE status IN ('announced', 'active')) as avg_price,
            AVG(price_per_sqm) FILTER (WHERE status IN ('announced', 'active')) as avg_price_per_sqm,
            AVG(area_total) FILTER (WHERE status IN ('announced', 'active')) as avg_area
        FROM auction_lots
        """
    )
    overview = cur.fetchone()

    # By source
    cur.execute(
        """
        SELECT
            source_type,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status IN ('announced', 'active')) as active,
            AVG(current_price) FILTER (WHERE status IN ('announced', 'active')) as avg_price
        FROM auction_lots
        GROUP BY source_type
        ORDER BY source_type
        """
    )
    by_source = cur.fetchall()

    # Discount stats
    cur.execute(
        """
        SELECT
            COUNT(*) as total_with_comparison,
            AVG(discount_from_market) as avg_discount,
            COUNT(*) FILTER (WHERE discount_from_market >= 20) as discount_20_plus,
            COUNT(*) FILTER (WHERE discount_from_market >= 30) as discount_30_plus
        FROM auction_market_comparison mc
        JOIN auction_lots l ON mc.lot_id = l.id
        WHERE l.status IN ('announced', 'active')
        """
    )
    discount_stats = cur.fetchone()

    # Upcoming auctions (next 7 days)
    cur.execute(
        """
        SELECT COUNT(*) as upcoming_auctions
        FROM auction_lots
        WHERE status IN ('announced', 'active')
          AND auction_date >= NOW()
          AND auction_date <= NOW() + INTERVAL '7 days'
        """
    )
    upcoming = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({
        'overview': dict(overview) if overview else {},
        'by_source': [dict(row) for row in by_source],
        'discount_stats': dict(discount_stats) if discount_stats else {},
        'upcoming_auctions': upcoming['upcoming_auctions'] if upcoming else 0,
    })


@bp.route('/api/sources', methods=['GET'])
def get_sources():
    """Get list of auction sources/platforms."""
    conn = get_auctions_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT
            id,
            source_type,
            name,
            url,
            is_active,
            (SELECT COUNT(*) FROM auction_lots WHERE platform_id = auction_platforms.id) as lots_count
        FROM auction_platforms
        ORDER BY source_type, name
        """
    )

    sources = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({'sources': [dict(row) for row in sources]})


@bp.route('/api/compare/<int:lot_id>', methods=['POST'])
def compare_with_market(lot_id):
    """
    Compare lot price with market value.
    Triggers valuation API to estimate market price.
    """
    conn = get_auctions_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get lot data
    cur.execute(
        "SELECT lat, lon, area_total, rooms, floor, total_floors FROM auction_lots WHERE id = %s",
        (lot_id,)
    )
    lot = cur.fetchone()

    if not lot:
        cur.close()
        conn.close()
        return jsonify({'error': 'Lot not found'}), 404

    if not lot['lat'] or not lot['lon'] or not lot['area_total']:
        cur.close()
        conn.close()
        return jsonify({'error': 'Lot missing required data for valuation'}), 400

    # Call valuation API
    try:
        import httpx
        valuation_url = os.getenv('VALUATION_API_URL', 'http://localhost:8000')
        response = httpx.post(
            f"{valuation_url}/estimate",
            json={
                'lat': float(lot['lat']),
                'lon': float(lot['lon']),
                'area_total': float(lot['area_total']),
                'rooms': lot['rooms'] or 1,
                'floor': lot['floor'],
                'total_floors': lot['total_floors'],
            },
            timeout=30.0
        )
        response.raise_for_status()
        valuation = response.json()

        # Save comparison
        market_price = valuation.get('estimated_price')
        if market_price:
            # Get current auction price
            cur.execute("SELECT current_price FROM auction_lots WHERE id = %s", (lot_id,))
            lot_price = cur.fetchone()

            if lot_price and lot_price['current_price']:
                discount = ((market_price - float(lot_price['current_price'])) / market_price) * 100

                cur.execute(
                    """
                    INSERT INTO auction_market_comparison (
                        lot_id, market_price_estimate, market_price_per_sqm,
                        estimation_method, estimation_confidence,
                        discount_from_market, comparables_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (lot_id) DO UPDATE SET
                        market_price_estimate = EXCLUDED.market_price_estimate,
                        market_price_per_sqm = EXCLUDED.market_price_per_sqm,
                        estimation_method = EXCLUDED.estimation_method,
                        estimation_confidence = EXCLUDED.estimation_confidence,
                        discount_from_market = EXCLUDED.discount_from_market,
                        comparables_count = EXCLUDED.comparables_count,
                        calculated_at = NOW()
                    """,
                    (
                        lot_id,
                        market_price,
                        valuation.get('estimated_price_per_sqm'),
                        valuation.get('method_used'),
                        valuation.get('confidence'),
                        discount,
                        valuation.get('comparables_count'),
                    )
                )
                conn.commit()

                cur.close()
                conn.close()

                return jsonify({
                    'success': True,
                    'market_price': market_price,
                    'auction_price': float(lot_price['current_price']),
                    'discount': round(discount, 1),
                })

        cur.close()
        conn.close()
        return jsonify({'error': 'Could not calculate comparison'}), 500

    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500
