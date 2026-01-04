"""Routes for local data collection and valuation."""
from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from flask import Blueprint, jsonify, render_template_string, request

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from etl.upsert import get_db_connection

LOGGER = logging.getLogger(__name__)
bp = Blueprint('local_valuation', __name__, url_prefix='/local')

# Simple HTML template
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Локальная оценка</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #333; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .btn { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        .btn:hover { background: #0056b3; }
        .btn-success { background: #28a745; }
        .btn-warning { background: #ffc107; color: #333; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f8f9fa; }
        .price { font-weight: bold; color: #28a745; }
        .stats { display: flex; gap: 20px; flex-wrap: wrap; }
        .stat { background: #e9ecef; padding: 15px; border-radius: 8px; min-width: 150px; }
        .stat-value { font-size: 24px; font-weight: bold; color: #333; }
        .stat-label { color: #666; font-size: 14px; }
        .form-group { margin: 10px 0; }
        input, select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .valuation-result { background: #d4edda; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .valuation-price { font-size: 32px; font-weight: bold; color: #155724; }
    </style>
</head>
<body>
<div class="container">
    <h1>🏠 Локальная оценка недвижимости</h1>

    <div class="card">
        <h2>📊 Статистика по Дмитровскому району</h2>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{{ stats.total }}</div>
                <div class="stat-label">Всего листингов</div>
            </div>
            <div class="stat">
                <div class="stat-value">{{ stats.dmitrov }}</div>
                <div class="stat-label">Дмитров</div>
            </div>
            <div class="stat">
                <div class="stat-value">{{ stats.yahroma }}</div>
                <div class="stat-label">Яхрома</div>
            </div>
            <div class="stat">
                <div class="stat-value">{{ "{:,.0f}".format(stats.avg_price_sqm) }} ₽</div>
                <div class="stat-label">Средняя цена за м²</div>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>🔍 Оценка объекта</h2>
        <form method="POST" action="/local/valuate">
            <div class="form-group">
                <label>Город:</label>
                <select name="city">
                    <option value="яхрома">Яхрома</option>
                    <option value="дмитров">Дмитров</option>
                    <option value="икша">Икша</option>
                </select>
            </div>
            <div class="form-group">
                <label>Площадь (м²):</label>
                <input type="number" name="area" value="69" step="0.1" required>
            </div>
            <div class="form-group">
                <label>Комнат:</label>
                <select name="rooms">
                    <option value="1">1</option>
                    <option value="2" selected>2</option>
                    <option value="3">3</option>
                    <option value="4">4+</option>
                </select>
            </div>
            <div class="form-group">
                <label>Этаж:</label>
                <input type="number" name="floor" value="5" min="1" max="30">
                <label>из</label>
                <input type="number" name="total_floors" value="9" min="1" max="30">
            </div>
            <button type="submit" class="btn btn-success">Оценить</button>
        </form>

        {% if valuation %}
        <div class="valuation-result">
            <h3>Результат оценки</h3>
            <div class="valuation-price">{{ "{:,.0f}".format(valuation.price) }} ₽</div>
            <p>Цена за м²: {{ "{:,.0f}".format(valuation.price_sqm) }} ₽</p>
            <p>Аналогов использовано: {{ valuation.comparables }}</p>
            <p>Диапазон: {{ "{:,.0f}".format(valuation.min_price) }} - {{ "{:,.0f}".format(valuation.max_price) }} ₽</p>
        </div>
        {% endif %}
    </div>

    <div class="card">
        <h2>🏘️ Аналоги в базе</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Адрес</th>
                    <th>Комнат</th>
                    <th>Площадь</th>
                    <th>Этаж</th>
                    <th>Цена</th>
                    <th>₽/м²</th>
                </tr>
            </thead>
            <tbody>
            {% for l in listings %}
                <tr>
                    <td><a href="https://cian.ru/sale/flat/{{ l.cian_id }}" target="_blank">{{ l.cian_id }}</a></td>
                    <td>{{ l.address[:50] }}...</td>
                    <td>{{ l.rooms }}</td>
                    <td>{{ l.total_area }} м²</td>
                    <td>{{ l.floor }}/{{ l.floors_total }}</td>
                    <td class="price">{{ "{:,.0f}".format(l.price) }} ₽</td>
                    <td>{{ "{:,.0f}".format(l.price_sqm) }} ₽</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="card">
        <h2>⚙️ Сбор данных</h2>
        <p>Сбор использует cookies (БЕЗ прокси). Cookies должны быть свежими.</p>
        <form method="POST" action="/local/collect">
            <select name="location">
                <option value="dmitrov">Дмитровский район</option>
                <option value="yahroma">Яхрома</option>
            </select>
            <input type="number" name="pages" value="5" min="1" max="20">
            <label>страниц</label>
            <button type="submit" class="btn btn-warning">Собрать данные</button>
        </form>
        <p id="status"></p>
    </div>
</div>
</body>
</html>
"""


def get_dmitrov_stats():
    """Get statistics for Dmitrov district (Moscow Oblast)."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Total listings in DB
        cur.execute("SELECT COUNT(*) FROM listings")
        total = cur.fetchone()[0]

        # Dmitrov (MO only)
        cur.execute("""
            SELECT COUNT(*) FROM listings
            WHERE address ILIKE '%%московская область%%'
              AND address ILIKE '%%дмитров%%'
        """)
        dmitrov = cur.fetchone()[0]

        # Yahroma
        cur.execute("""
            SELECT COUNT(*) FROM listings
            WHERE address ILIKE '%%яхром%%'
        """)
        yahroma = cur.fetchone()[0]

        # Avg price per sqm for Dmitrov area (MO)
        cur.execute("""
            SELECT AVG(p.price / l.area_total)
            FROM listings l
            JOIN listing_prices p ON p.id = l.id
            WHERE l.address ILIKE '%%московская область%%'
              AND (l.address ILIKE '%%дмитров%%' OR l.address ILIKE '%%яхром%%')
              AND l.area_total > 0
              AND p.price > 0
        """)
        avg = cur.fetchone()[0] or 0

        return {
            'total': total,
            'dmitrov': dmitrov,
            'yahroma': yahroma,
            'avg_price_sqm': avg,
        }
    finally:
        cur.close()
        conn.close()


def get_dmitrov_listings(limit=20):
    """Get listings for Dmitrov district (Moscow Oblast)."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                l.id,
                l.address,
                l.rooms,
                l.area_total,
                l.floor,
                l.total_floors,
                p.price,
                CASE WHEN l.area_total > 0 THEN p.price / l.area_total ELSE 0 END as price_sqm
            FROM listings l
            JOIN listing_prices p ON p.id = l.id
            WHERE l.address ILIKE '%%московская область%%'
              AND (l.address ILIKE '%%дмитров%%'
                   OR l.address ILIKE '%%яхром%%'
                   OR l.address ILIKE '%%икша%%')
              AND p.price > 0
            ORDER BY l.last_seen DESC NULLS LAST
            LIMIT %s
        """, (limit,))

        columns = ['cian_id', 'address', 'rooms', 'total_area', 'floor', 'floors_total', 'price', 'price_sqm']
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def valuate_object(city: str, area: float, rooms: int, floor: int, total_floors: int):
    """Simple valuation based on comparables."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Find comparables in Moscow Oblast
        cur.execute("""
            SELECT
                p.price / l.area_total as price_sqm,
                l.area_total,
                l.floor,
                l.total_floors
            FROM listings l
            JOIN listing_prices p ON p.id = l.id
            WHERE l.address ILIKE '%%московская область%%'
              AND l.address ILIKE %s
              AND l.area_total BETWEEN %s AND %s
              AND l.rooms = %s
              AND p.price > 0
              AND l.area_total > 0
            ORDER BY l.last_seen DESC NULLS LAST
            LIMIT 20
        """, (f'%{city}%', area * 0.7, area * 1.3, rooms))

        rows = cur.fetchall()

        if not rows:
            # Fallback: any listings in MO Dmitrov area
            cur.execute("""
                SELECT
                    p.price / l.area_total as price_sqm,
                    l.area_total,
                    l.floor,
                    l.total_floors
                FROM listings l
                JOIN listing_prices p ON p.id = l.id
                WHERE l.address ILIKE '%%московская область%%'
                  AND (l.address ILIKE '%%дмитров%%'
                       OR l.address ILIKE '%%яхром%%')
                  AND p.price > 0
                  AND l.area_total > 0
                ORDER BY l.last_seen DESC NULLS LAST
                LIMIT 20
            """)
            rows = cur.fetchall()

        if not rows:
            return None

        prices_sqm = [r[0] for r in rows]
        median_price_sqm = sorted(prices_sqm)[len(prices_sqm) // 2]

        # Adjustments
        adjustment = 1.0

        # First/last floor discount
        if floor == 1:
            adjustment *= 0.95
        elif floor == total_floors:
            adjustment *= 0.97

        final_price_sqm = median_price_sqm * adjustment
        final_price = final_price_sqm * area

        return {
            'price': final_price,
            'price_sqm': final_price_sqm,
            'comparables': len(rows),
            'min_price': min(prices_sqm) * area * 0.95,
            'max_price': max(prices_sqm) * area * 1.05,
        }
    finally:
        cur.close()
        conn.close()


@bp.route('/')
def index():
    """Main page."""
    stats = get_dmitrov_stats()
    listings = get_dmitrov_listings()
    return render_template_string(TEMPLATE, stats=stats, listings=listings, valuation=None)


@bp.route('/valuate', methods=['POST'])
def valuate():
    """Valuate an object."""
    city = request.form.get('city', 'яхрома')
    area = float(request.form.get('area', 69))
    rooms = int(request.form.get('rooms', 2))
    floor = int(request.form.get('floor', 5))
    total_floors = int(request.form.get('total_floors', 9))

    valuation = valuate_object(city, area, rooms, floor, total_floors)
    stats = get_dmitrov_stats()
    listings = get_dmitrov_listings()

    return render_template_string(TEMPLATE, stats=stats, listings=listings, valuation=valuation)


@bp.route('/collect', methods=['POST'])
def collect():
    """Trigger data collection (in background)."""
    location = request.form.get('location', 'dmitrov')
    pages = int(request.form.get('pages', 5))

    def run_collection():
        from etl.collector_cian.local_parser import collect_local
        collect_local(location_key=location, pages=pages, save=True)

    thread = threading.Thread(target=run_collection)
    thread.start()

    return jsonify({
        'status': 'started',
        'location': location,
        'pages': pages,
        'message': f'Сбор запущен в фоне: {location}, {pages} страниц'
    })


@bp.route('/stats')
def stats():
    """API for stats."""
    return jsonify(get_dmitrov_stats())
