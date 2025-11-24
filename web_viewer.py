"""
Simple web viewer for realestate listings
Run: python web_viewer.py
Access: http://51.75.16.178:8000
"""
import os
from typing import Optional
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = FastAPI(title="Realestate Viewer")

def get_db():
    return psycopg2.connect(os.getenv("PG_DSN"))

@app.get("/", response_class=HTMLResponse)
async def index(
    limit: int = Query(50, ge=1, le=500),
    rooms: Optional[str] = Query(None),
    min_price: Optional[str] = Query(None),
    max_price: Optional[str] = Query(None),
    sort: str = Query("price_asc", pattern="^(price_asc|price_desc|area_asc|area_desc|rooms_asc|rooms_desc|recent)$"),
    has_encumbrances: Optional[str] = Query(None),
    is_error: Optional[str] = Query(None)
):
    """Main page with listings table"""
    
    # Parse and validate filter parameters (handle empty strings from form)
    rooms_int = None
    if rooms and rooms.strip():
        try:
            rooms_int = int(rooms.strip())
            if rooms_int < 1 or rooms_int > 5:
                rooms_int = None
        except ValueError:
            rooms_int = None
    
    min_price_int = None
    if min_price and min_price.strip():
        try:
            min_price_int = int(min_price.strip())
            if min_price_int < 0:
                min_price_int = None
        except ValueError:
            min_price_int = None
    
    max_price_int = None
    if max_price and max_price.strip():
        try:
            max_price_int = int(max_price.strip())
            if max_price_int < 0:
                max_price_int = None
        except ValueError:
            max_price_int = None
    
    # Build SQL query
    where_clauses = []
    params = {}
    
    if rooms_int:
        where_clauses.append("l.rooms = %(rooms)s")
        params["rooms"] = rooms_int
    
    if min_price_int:
        where_clauses.append("lp.price >= %(min_price)s")
        params["min_price"] = min_price_int
    
    if max_price_int:
        where_clauses.append("lp.price <= %(max_price)s")
        params["max_price"] = max_price_int
    
    # Encumbrances filter
    if has_encumbrances == "true":
        where_clauses.append("l.has_encumbrances = TRUE")
    elif has_encumbrances == "false":
        where_clauses.append("(l.has_encumbrances = FALSE OR l.has_encumbrances IS NULL)")
    
    # Error filter
    if is_error == "true":
        where_clauses.append("l.is_error = TRUE")
    elif is_error == "false":
        where_clauses.append("(l.is_error = FALSE OR l.is_error IS NULL)")
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # Sorting
    sort_map = {
        "price_asc": "lp.price ASC",
        "price_desc": "lp.price DESC",
        "area_asc": "l.area_total ASC",
        "area_desc": "l.area_total DESC",
        "rooms_asc": "l.rooms ASC",
        "rooms_desc": "l.rooms DESC",
        "recent": "l.first_seen DESC"
    }
    order_by = sort_map.get(sort, "lp.price ASC")
    
    params["limit"] = limit
    
    # Build WHERE clause with is_active check
    final_where_clauses = ["l.is_active = TRUE"]
    if where_clauses:
        final_where_clauses.extend(where_clauses)
    final_where_sql = "WHERE " + " AND ".join(final_where_clauses)
    
    # Fix order_by to use latest_price alias
    fixed_order_by = order_by.replace("lp.price", "latest_price.price").replace("lp.", "latest_price.")
    
    query = f"""
    SELECT 
        l.id,
        l.url,
        l.address,
        COALESCE(l.address_full, l.address) as display_address,
        l.rooms,
        l.area_total,
        l.floor,
        l.total_floors,
        latest_price.price,
        l.description,
        l.first_seen::date as first_seen,
        l.has_encumbrances,
        l.encumbrance_types,
        l.is_error,
        l.error_reason
    FROM listings l
    JOIN LATERAL (
        SELECT price, seen_at
        FROM listing_prices
        WHERE id = l.id
        ORDER BY seen_at DESC
        LIMIT 1
    ) latest_price ON true
    {final_where_sql}
    ORDER BY {fixed_order_by}
    LIMIT %(limit)s
    """
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            listings = cur.fetchall()
            
            # Get stats
            cur.execute("SELECT COUNT(*) FROM listings")
            total_count = cur.fetchone()[0]
            
            cur.execute("SELECT AVG(price)::bigint, MIN(price)::bigint, MAX(price)::bigint FROM listing_prices")
            avg_price, min_price_db, max_price_db = cur.fetchone()
    
    # Generate HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Realestate Listings</title>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background: #f5f5f5;
            }}
            h1 {{
                color: #333;
            }}
            .stats {{
                background: white;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .stats span {{
                margin-right: 30px;
                font-weight: bold;
            }}
            .filters {{
                background: white;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .filters form {{
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                align-items: end;
            }}
            .filters label {{
                display: flex;
                flex-direction: column;
                gap: 5px;
            }}
            .filters input, .filters select {{
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }}
            .filters button {{
                padding: 8px 20px;
                background: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }}
            .filters button:hover {{
                background: #0056b3;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                background: white;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            th {{
                background: #007bff;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: bold;
            }}
            td {{
                padding: 10px 12px;
                border-bottom: 1px solid #eee;
            }}
            tr:hover {{
                background: #f9f9f9;
            }}
            a {{
                color: #007bff;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .price {{
                font-weight: bold;
                color: #28a745;
            }}
            .rooms {{
                color: #6c757d;
            }}
            .description {{
                max-width: 400px;
                word-wrap: break-word;
                font-size: 12px;
                color: #666;
                line-height: 1.4;
            }}
            .full-address {{
                max-width: 300px;
                word-wrap: break-word;
                font-size: 13px;
            }}
        </style>
    </head>
    <body>
        <h1>🏠 Realestate Listings Viewer</h1>
        
        <div class="stats">
            <span>Total: {total_count:,} listings</span>
            <span>Avg: {avg_price:,} ₽</span>
            <span>Min: {min_price_db:,} ₽</span>
            <span>Max: {max_price_db:,} ₽</span>
        </div>
        
        <div class="filters">
            <form method="get">
                <label>
                    Rooms:
                    <input type="number" name="rooms" min="1" max="5" placeholder="Any" value="{rooms or ''}">
                </label>
                <label>
                    Min Price (₽):
                    <input type="number" name="min_price" min="0" step="100000" placeholder="No min" value="{min_price or ''}">
                </label>
                <label>
                    Max Price (₽):
                    <input type="number" name="max_price" min="0" step="100000" placeholder="No max" value="{max_price or ''}">
                </label>
                <label>
                    Sort by:
                    <select name="sort">
                        <option value="price_asc" {"selected" if sort == "price_asc" else ""}>Price ↑</option>
                        <option value="price_desc" {"selected" if sort == "price_desc" else ""}>Price ↓</option>
                        <option value="area_asc" {"selected" if sort == "area_asc" else ""}>Area ↑</option>
                        <option value="area_desc" {"selected" if sort == "area_desc" else ""}>Area ↓</option>
                        <option value="rooms_asc" {"selected" if sort == "rooms_asc" else ""}>Rooms ↑</option>
                        <option value="rooms_desc" {"selected" if sort == "rooms_desc" else ""}>Rooms ↓</option>
                        <option value="recent" {"selected" if sort == "recent" else ""}>Recent</option>
                    </select>
                </label>
                <label>
                    Limit:
                    <input type="number" name="limit" min="10" max="500" value="{limit}">
                </label>
                <label style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
                    <input type="checkbox" name="has_encumbrances" value="true" {"checked" if has_encumbrances == "true" else ""}>
                    С обременениями
                </label>
                <label style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
                    <input type="checkbox" name="is_error" value="true" {"checked" if is_error == "true" else ""}>
                    Помечены как ошибки
                </label>
                <button type="submit">Apply Filters</button>
                <button type="button" onclick="window.location.href='/'">Reset</button>
            </form>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Address</th>
                    <th>Full Address</th>
                    <th>Rooms</th>
                    <th>Area (m²)</th>
                    <th>Floor</th>
                    <th>Price (₽)</th>
                    <th>Price/m² (₽)</th>
                    <th>Description</th>
                    <th>First Seen</th>
                    <th>Link</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for listing in listings:
        id_, url, address, display_address, rooms, area, floor, floor_total, price, description, first_seen, has_encumbrances, encumbrance_types, is_error, error_reason = listing
        price_per_sqm = int(price / area) if area and area > 0 else 0
        floor_str = f"{floor}/{floor_total}" if floor and floor_total else (str(floor) if floor else "—")
        rooms_str = f"{rooms}-room" if rooms else "—"
        
        # Format full address - show if different from short address
        full_addr_display = display_address if display_address and display_address != address else "—"
        
        # Format description - truncate to 200 chars
        desc_display = "—"
        if description:
            desc_clean = description.strip().replace('\n', ' ').replace('\r', ' ')
            if len(desc_clean) > 200:
                desc_display = desc_clean[:200] + "..."
            else:
                desc_display = desc_clean
        
        # Encumbrance indicator
        encumbrance_badge = ""
        if has_encumbrances:
            enc_types = ", ".join(encumbrance_types) if encumbrance_types else "есть"
            encumbrance_badge = f'<span style="background: #ffc107; color: #000; padding: 2px 6px; border-radius: 3px; font-size: 11px; display: inline-block; margin-top: 5px;" title="{enc_types}">⚠️ Обременение</span>'
        
        # Error indicator
        error_badge = ""
        if is_error:
            error_reason_text = error_reason if error_reason else "помечено"
            error_badge = f'<span style="background: #dc3545; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; display: inline-block; margin-top: 5px;" title="{error_reason_text}">❌ Ошибка</span>'
        
        # Mark error button
        mark_error_btn = f'<button onclick="markError({id_})" style="padding: 4px 8px; background: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; margin-bottom: 3px;">❌ Ошибка</button>' if not is_error else f'<button onclick="unmarkError({id_})" style="padding: 4px 8px; background: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; margin-bottom: 3px;">✅ Убрать</button>'
        
        row_style = 'style="background: #ffe6e6;"' if is_error else ('style="background: #fff3cd;"' if has_encumbrances else '')
        
        html += f"""
                <tr {row_style}>
                    <td>{id_}</td>
                    <td>{address}{encumbrance_badge}{error_badge}</td>
                    <td style="max-width: 300px; word-wrap: break-word;">{full_addr_display}</td>
                    <td class="rooms">{rooms_str}</td>
                    <td>{area:.1f}</td>
                    <td>{floor_str}</td>
                    <td class="price">{price:,.0f}</td>
                    <td>{price_per_sqm:,}</td>
                    <td style="max-width: 400px; word-wrap: break-word; font-size: 12px; color: #666;">
                        {desc_display}
                        {f'<br><a href="/listing/{id_}" style="font-size: 11px; color: #007bff;">Читать полностью →</a>' if description and len(description) > 200 else ''}
                    </td>
                    <td>{first_seen}</td>
                    <td><a href="{url}" target="_blank">View</a></td>
                    <td style="text-align: center;">
                        {mark_error_btn}
                    </td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
        
        <script>
            async function markError(listingId) {
                const reason = prompt('Причина пометки как ошибка (опционально):');
                if (reason === null) return; // Cancelled
                
                try {
                    const response = await fetch('/mark_error', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            listing_id: listingId,
                            error_reason: reason || 'manual_review',
                            marked_by: 'user'
                        })
                    });
                    
                    if (response.ok) {
                        alert('Объявление помечено как ошибка');
                        location.reload();
                    } else {
                        alert('Ошибка при сохранении');
                    }
                } catch (e) {
                    alert('Ошибка: ' + e.message);
                }
            }
            
            async function unmarkError(listingId) {
                if (!confirm('Снять пометку ошибки?')) return;
                
                try {
                    const response = await fetch('/unmark_error', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({listing_id: listingId})
                    });
                    
                    if (response.ok) {
                        alert('Пометка снята');
                        location.reload();
                    } else {
                        alert('Ошибка при сохранении');
                    }
                } catch (e) {
                    alert('Ошибка: ' + e.message);
                }
            }
        </script>
    </body>
    </html>
    """
    
    return html

@app.get("/listing/{listing_id}", response_class=HTMLResponse)
async def listing_detail(listing_id: int):
    """Detail page for a single listing with full description"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get listing with latest price
            cur.execute("""
                SELECT 
                    l.id,
                    l.url,
                    l.address,
                    COALESCE(l.address_full, l.address) as display_address,
                    l.rooms,
                    l.area_total,
                    l.area_living,
                    l.area_kitchen,
                    l.floor,
                    l.total_floors,
                    l.balcony,
                    l.loggia,
                    l.renovation,
                    l.rooms_layout,
                    l.building_type,
                    l.property_type,
                    l.house_year,
                    l.house_material,
                    l.house_series,
                    l.house_has_elevator,
                    l.house_has_parking,
                    l.description,
                    l.published_at,
                    l.lat,
                    l.lon,
                    latest_price.price,
                    l.first_seen::date as first_seen
                FROM listings l
                JOIN LATERAL (
                    SELECT price, seen_at
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) latest_price ON true
                WHERE l.id = %s AND l.is_active = TRUE;
            """, (listing_id,))
            
            row = cur.fetchone()
            if not row:
                return HTMLResponse("<h1>Объявление не найдено</h1><p><a href='/'>Вернуться к списку</a></p>", status_code=404)
            
            (id_, url, address, display_address, rooms, area_total, area_living, area_kitchen,
             floor, total_floors, balcony, loggia, renovation, rooms_layout,
             building_type, property_type, house_year, house_material, house_series,
             house_has_elevator, house_has_parking, description, published_at,
             lat, lon, price, first_seen) = row
            
            # Get photos
            cur.execute("""
                SELECT photo_url, photo_order
                FROM listing_photos
                WHERE listing_id = %s
                ORDER BY photo_order ASC;
            """, (listing_id,))
            photos = cur.fetchall()
    
    # Format data
    rooms_str = f"{rooms}-комнатная" if rooms else "Студия" if rooms == 0 else "—"
    floor_str = f"{floor}/{total_floors}" if floor and total_floors else (str(floor) if floor else "—")
    price_per_sqm = int(price / area_total) if area_total and area_total > 0 else 0
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Объявление #{id_}</title>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background: #f5f5f5;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: white;
                padding: 20px;
                border-radius: 5px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .back-link {{
                color: #007bff;
                text-decoration: none;
                margin-bottom: 10px;
                display: inline-block;
            }}
            .back-link:hover {{
                text-decoration: underline;
            }}
            .price {{
                font-size: 28px;
                font-weight: bold;
                color: #28a745;
                margin: 10px 0;
            }}
            .details {{
                background: white;
                padding: 20px;
                border-radius: 5px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .details-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                margin-top: 15px;
            }}
            .detail-item {{
                padding: 10px;
                background: #f9f9f9;
                border-radius: 4px;
            }}
            .detail-label {{
                font-weight: bold;
                color: #666;
                font-size: 12px;
                text-transform: uppercase;
            }}
            .detail-value {{
                font-size: 16px;
                margin-top: 5px;
            }}
            .description {{
                background: white;
                padding: 20px;
                border-radius: 5px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                white-space: pre-wrap;
                line-height: 1.6;
            }}
            .photos {{
                background: white;
                padding: 20px;
                border-radius: 5px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .photo-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 10px;
                margin-top: 15px;
            }}
            .photo-item {{
                position: relative;
                padding-top: 75%;
                overflow: hidden;
                border-radius: 4px;
            }}
            .photo-item img {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}
            h1 {{
                color: #333;
                margin: 0;
            }}
            h2 {{
                color: #333;
                margin-top: 0;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <a href="/" class="back-link">← Вернуться к списку</a>
            <h1>{rooms_str} квартира</h1>
            <div class="price">{price:,.0f} ₽</div>
            <div style="color: #666; margin-top: 5px;">{price_per_sqm:,} ₽/м²</div>
            <div style="margin-top: 10px; font-size: 14px; color: #666;">
                <strong>Адрес:</strong> {display_address or address}
            </div>
            <div style="margin-top: 5px;">
                <a href="{url}" target="_blank" style="color: #007bff;">Открыть на CIAN →</a>
            </div>
        </div>
        
        <div class="details">
            <h2>Характеристики</h2>
            <div class="details-grid">
                <div class="detail-item">
                    <div class="detail-label">Комнат</div>
                    <div class="detail-value">{rooms_str}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Общая площадь</div>
                    <div class="detail-value">{area_total:.1f} м²</div>
                </div>
                {f'<div class="detail-item"><div class="detail-label">Жилая площадь</div><div class="detail-value">{area_living:.1f} м²</div></div>' if area_living else ''}
                {f'<div class="detail-item"><div class="detail-label">Площадь кухни</div><div class="detail-value">{area_kitchen:.1f} м²</div></div>' if area_kitchen else ''}
                <div class="detail-item">
                    <div class="detail-label">Этаж</div>
                    <div class="detail-value">{floor_str}</div>
                </div>
                {f'<div class="detail-item"><div class="detail-label">Балкон</div><div class="detail-value">{"Есть" if balcony else "Нет"}</div></div>' if balcony is not None else ''}
                {f'<div class="detail-item"><div class="detail-label">Лоджия</div><div class="detail-value">{"Есть" if loggia else "Нет"}</div></div>' if loggia is not None else ''}
                {f'<div class="detail-item"><div class="detail-label">Ремонт</div><div class="detail-value">{renovation}</div></div>' if renovation else ''}
                {f'<div class="detail-item"><div class="detail-label">Планировка</div><div class="detail-value">{rooms_layout}</div></div>' if rooms_layout else ''}
                {f'<div class="detail-item"><div class="detail-label">Тип дома</div><div class="detail-value">{building_type}</div></div>' if building_type else ''}
                {f'<div class="detail-item"><div class="detail-label">Год постройки</div><div class="detail-value">{house_year}</div></div>' if house_year else ''}
                {f'<div class="detail-item"><div class="detail-label">Материал стен</div><div class="detail-value">{house_material}</div></div>' if house_material else ''}
                {f'<div class="detail-item"><div class="detail-label">Лифт</div><div class="detail-value">{"Есть" if house_has_elevator else "Нет"}</div></div>' if house_has_elevator is not None else ''}
                {f'<div class="detail-item"><div class="detail-label">Парковка</div><div class="detail-value">{"Есть" if house_has_parking else "Нет"}</div></div>' if house_has_parking is not None else ''}
            </div>
        </div>
        
        {f'<div class="description"><h2>Описание</h2><p>{description}</p></div>' if description else ''}
        
        {f'''<div class="photos">
            <h2>Фотографии ({len(photos)})</h2>
            <div class="photo-grid">
                {''.join([f'<div class="photo-item"><img src="{photo[0]}" alt="Фото {photo[1]}"></div>' for photo in photos])}
            </div>
        </div>''' if photos else ''}
        
        <div style="text-align: center; margin-top: 20px;">
            <a href="/" class="back-link">← Вернуться к списку</a>
        </div>
    </body>
    </html>
    """
    return html

@app.get("/api/stats")
async def stats():
    """API endpoint for statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(rooms) as with_rooms,
                    AVG(area_total)::decimal(10,2) as avg_area,
                    (SELECT AVG(price)::bigint FROM listing_prices) as avg_price,
                    (SELECT COUNT(*) FROM listing_prices) as total_prices
                FROM listings
            """)
            row = cur.fetchone()
            
            return {
                "total_listings": row[0],
                "with_rooms": row[1],
                "avg_area": float(row[2]) if row[2] else None,
                "avg_price": row[3],
                "total_prices": row[4]
            }

@app.post("/mark_error")
async def mark_error(request: Request):
    """Mark listing as error"""
    data = await request.json()
    listing_id = data.get('listing_id')
    error_reason = data.get('error_reason', 'manual_review')
    marked_by = data.get('marked_by', 'user')
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET 
                    is_error = TRUE,
                    error_reason = %s,
                    marked_by = %s,
                    marked_at = NOW()
                WHERE id = %s
            """, (error_reason, marked_by, listing_id))
            conn.commit()
    
    return JSONResponse({"success": True})

@app.post("/unmark_error")
async def unmark_error(request: Request):
    """Remove error mark from listing"""
    data = await request.json()
    listing_id = data.get('listing_id')
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET 
                    is_error = FALSE,
                    error_reason = NULL,
                    marked_by = NULL,
                    marked_at = NULL
                WHERE id = %s
            """, (listing_id,))
            conn.commit()
    
    return JSONResponse({"success": True})

if __name__ == "__main__":
    import uvicorn
    print("Starting web viewer on http://51.75.16.178:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
