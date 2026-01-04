"""
Simple web viewer for realestate listings
Run: python web_viewer.py
Access: http://51.75.16.178:8000
"""
import os
import re
from typing import Optional
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import html

load_dotenv()

# Паттерны для подсветки обременений (синхронизированы с encumbrance_analyzer.py)
# ВАЖНО: Арендаторы УДАЛЕНЫ - это НЕ обременение для торга
ENCUMBRANCE_HIGHLIGHT_PATTERNS = [
    # Зарегистрированные люди (только если НЕ выпишутся до сделки)
    r'зарегистриров\w+\s+\d+\s+чел',
    r'прописан\w+\s+\d+\s+чел',
    r'зарегистриров\w+\s+дети',
    r'прописан\w+\s+дети',
    # Убрали: "с жильц" - жильцы часто означает арендаторов
    r'есть прописанные',
    r'есть зарегистрированные',
    r'\d+\s+зарегистриров\w*',
    r'\d+\s+прописан\w*',
    r'проживают люди',
    r'живут люди',
    r'не выписан\w*',
    # Выселение (только принудительное)
    r'требуется выселение',
    r'нужно выселение',
    r'необходимо выселение',
    r'выселение через суд',
    r'выселение по суду',
    r'принудительное выселение',
    r'судебное выселение',
    # Убрали: "снятие с учета", "снятие с регистр", "требуется снятие", "нужно снятие" - часто добровольное
    # Ипотека/залог
    r'квартира в ипотеке',
    r'объект в залоге',
    r'под залогом',
    r'обременение ипотекой',
    r'ипотечное обременение',
    r'залог банка',
    r'не снято обременение',
    r'с обременением',
    r'банк залогодержатель',
    r'кредит на квартиру',
    r'ипотечный кредит на объект',
    # Юридические проблемы
    r'судебное разбирательство',
    r'судебный спор',
    r'находится в суде',
    r'под арестом',
    r'находится под арестом',
    r'наследственное дело',
    r'споры о наследстве',
    r'оспаривается',
    r'судебное производство',
]

def highlight_encumbrances(text: str) -> str:
    """Подсветить ключевые слова обременений в тексте."""
    if not text:
        return text

    # Escape HTML
    text = html.escape(text)

    # Применить все паттерны
    for pattern in ENCUMBRANCE_HIGHLIGHT_PATTERNS:
        text = re.sub(
            f'({pattern})',
            r'<mark style="background: #fbbf24; color: #000; padding: 1px 3px; border-radius: 2px; font-weight: bold;">\1</mark>',
            text,
            flags=re.IGNORECASE
        )

    return text

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
    is_error: Optional[str] = Query(None),
    period: Optional[str] = Query(None)
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

    # Period filter (for encumbrances)
    if period == "today":
        where_clauses.append("l.first_seen >= CURRENT_DATE")
    elif period == "week":
        where_clauses.append("l.first_seen >= CURRENT_DATE - INTERVAL '7 days'")
    elif period == "month":
        where_clauses.append("l.first_seen >= CURRENT_DATE - INTERVAL '30 days'")

    # For encumbrances, default to sorting by date (newest first)
    if has_encumbrances == "true" and sort == "price_asc":
        sort = "recent"

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
        l.error_reason,
        l.contacted,
        l.sent_to_tg
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
                    <input type="checkbox" name="has_encumbrances" value="true" {"checked" if has_encumbrances == "true" else ""} id="enc_checkbox" onchange="togglePeriod()">
                    С обременениями
                </label>
                <label style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
                    <input type="checkbox" name="is_error" value="true" {"checked" if is_error == "true" else ""}>
                    Помечены как ошибки
                </label>
                <button type="submit">Apply Filters</button>
                <button type="button" onclick="window.location.href='/'">Reset</button>
                <div id="period_filters" style="display: {'flex' if has_encumbrances == 'true' else 'none'}; gap: 10px; align-items: center; margin-left: 20px;">
                    <span style="color: #666; font-weight: bold;">Период:</span>
                    <label style="cursor: pointer;"><input type="radio" name="period" value="" {"checked" if not period else ""}> Все</label>
                    <label style="cursor: pointer;"><input type="radio" name="period" value="today" {"checked" if period == 'today' else ""}> Сегодня</label>
                    <label style="cursor: pointer;"><input type="radio" name="period" value="week" {"checked" if period == 'week' else ""}> Неделя</label>
                    <label style="cursor: pointer;"><input type="radio" name="period" value="month" {"checked" if period == 'month' else ""}> Месяц</label>
                </div>
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
        id_, url, address, display_address, rooms, area, floor, floor_total, price, description, first_seen, has_encumbrances, encumbrance_types, is_error, error_reason, contacted, sent_to_tg = listing
        price_per_sqm = int(price / area) if area and area > 0 else 0
        floor_str = f"{floor}/{floor_total}" if floor and floor_total else (str(floor) if floor else "—")
        rooms_str = f"{rooms}-room" if rooms else "—"
        
        # Format full address - show if different from short address
        full_addr_display = display_address if display_address and display_address != address else "—"
        
        # Format description - truncate and highlight encumbrances
        desc_display = "—"
        if description:
            desc_clean = description.strip().replace('\n', ' ').replace('\r', ' ')

            # Для объявлений с обременениями - показать контекст вокруг ключевого слова
            if has_encumbrances:
                # Найти первое ключевое слово
                keyword_pos = None
                for pattern in ENCUMBRANCE_HIGHLIGHT_PATTERNS:
                    match = re.search(pattern, desc_clean, re.IGNORECASE)
                    if match:
                        keyword_pos = match.start()
                        break

                if keyword_pos and keyword_pos > 150:
                    # Показать контекст вокруг ключевого слова
                    start = max(0, keyword_pos - 80)
                    end = min(len(desc_clean), keyword_pos + 150)
                    desc_display = ("..." if start > 0 else "") + desc_clean[start:end] + ("..." if end < len(desc_clean) else "")
                elif len(desc_clean) > 300:
                    desc_display = desc_clean[:300] + "..."
                else:
                    desc_display = desc_clean

                desc_display = highlight_encumbrances(desc_display)
            else:
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
        
        # Mark error button (white bg with colored border for contrast)
        mark_error_btn = f'<button onclick="markError({id_})" style="padding: 4px 8px; background: white; color: #dc3545; border: 2px solid #dc3545; border-radius: 3px; cursor: pointer; font-size: 11px; margin-bottom: 3px; font-weight: bold;">⚠️ Ошибка</button>' if not is_error else f'<button onclick="unmarkError({id_})" style="padding: 4px 8px; background: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; margin-bottom: 3px;">✅ Ок</button>'

        # Contacted button (called, no deal)
        contacted_btn = f'<span style="padding: 4px 8px; background: #6c757d; color: white; border-radius: 3px; font-size: 11px; margin-bottom: 3px; display: inline-block;">📞 Звонили</span>' if contacted else f'<button onclick="markContacted({id_})" style="padding: 4px 8px; background: #17a2b8; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px; margin-bottom: 3px;">📞 Нет</button>'

        # Send to TG button
        tg_btn = f'<span style="padding: 4px 8px; background: #6c757d; color: white; border-radius: 3px; font-size: 11px; display: inline-block;">📤 В TG</span>' if sent_to_tg else f'<button onclick="sendToTelegram({id_})" style="padding: 4px 8px; background: #0088cc; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 11px;">📤 В TG</button>'

        # Remove encumbrance button (white bg with colored border for contrast)
        remove_enc_btn = f'<button onclick="removeEncumbrance({id_})" style="padding: 4px 8px; background: white; color: #856404; border: 2px solid #856404; border-radius: 3px; cursor: pointer; font-size: 11px; margin-top: 3px; font-weight: bold;">✖️ Снять</button>' if has_encumbrances else ''

        # Row colors: error (red) > sent to TG (blue) > encumbrance (yellow)
        if is_error:
            row_style = 'style="background: #ffe6e6;"'
        elif sent_to_tg:
            row_style = 'style="background: #d4edfc;"'  # Light blue for TG
        elif has_encumbrances:
            row_style = 'style="background: #fff3cd;"'
        else:
            row_style = ''
        
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
                    <td style="text-align: center; white-space: nowrap;">
                        {mark_error_btn}<br>
                        {contacted_btn}<br>
                        {tg_btn}
                        {('<br>' + remove_enc_btn) if remove_enc_btn else ''}
                    </td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
        
        <script>
            function togglePeriod() {
                const checkbox = document.getElementById('enc_checkbox');
                const periodDiv = document.getElementById('period_filters');
                periodDiv.style.display = checkbox.checked ? 'flex' : 'none';
            }

            // Auto-submit on period change
            document.querySelectorAll('input[name="period"]').forEach(radio => {
                radio.addEventListener('change', () => document.querySelector('form').submit());
            });

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

            async function markContacted(listingId) {
                if (!confirm('Пометить как "Позвонили - нет"?')) return;

                try {
                    const response = await fetch('/mark_contacted', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({listing_id: listingId})
                    });

                    if (response.ok) {
                        alert('Помечено как обработанное');
                        location.reload();
                    } else {
                        alert('Ошибка при сохранении');
                    }
                } catch (e) {
                    alert('Ошибка: ' + e.message);
                }
            }

            async function sendToTelegram(listingId) {
                const comment = prompt('Комментарий для Telegram (опционально):');
                if (comment === null) return; // Cancelled

                try {
                    const response = await fetch('/send_to_telegram', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({listing_id: listingId, comment: comment})
                    });

                    if (response.ok) {
                        alert('Отправлено в Telegram!');
                        location.reload();
                    } else {
                        const data = await response.json();
                        alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                    }
                } catch (e) {
                    alert('Ошибка: ' + e.message);
                }
            }

            async function removeEncumbrance(listingId) {
                if (!confirm('Снять флаг обременения с этого объявления?')) return;

                try {
                    const response = await fetch('/remove_encumbrance', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({listing_id: listingId})
                    });

                    if (response.ok) {
                        alert('Обременение снято');
                        location.reload();
                    } else {
                        const data = await response.json();
                        alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
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
                    l.first_seen::date as first_seen,
                    l.has_encumbrances
                FROM listings l
                JOIN LATERAL (
                    SELECT price, seen_at
                    FROM listing_prices
                    WHERE id = l.id
                    ORDER BY seen_at DESC
                    LIMIT 1
                ) latest_price ON true
                WHERE l.id = %s;
            """, (listing_id,))
            
            row = cur.fetchone()
            if not row:
                return HTMLResponse("<h1>Объявление не найдено</h1><p><a href='/'>Вернуться к списку</a></p>", status_code=404)
            
            (id_, url, address, display_address, rooms, area_total, area_living, area_kitchen,
             floor, total_floors, balcony, loggia, renovation, rooms_layout,
             building_type, property_type, house_year, house_material, house_series,
             house_has_elevator, house_has_parking, description, published_at,
             lat, lon, price, first_seen, has_encumbrances) = row
            
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

    # Подсветить ключевые слова в описании для объявлений с обременениями
    description_display = ""
    if description:
        if has_encumbrances:
            description_display = highlight_encumbrances(description)
        else:
            description_display = html.escape(description)

    page_html = f"""
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
        
        {f'<div class="description"><h2>Описание</h2><p>{description_display}</p></div>' if description else ''}
        
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
    return page_html

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

@app.post("/mark_contacted")
async def mark_contacted(request: Request):
    """Mark listing as contacted (called, no deal)"""
    data = await request.json()
    listing_id = data.get('listing_id')

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET contacted = TRUE, contacted_at = NOW()
                WHERE id = %s
            """, (listing_id,))
            conn.commit()

    return JSONResponse({"success": True})

@app.post("/remove_encumbrance")
async def remove_encumbrance(request: Request):
    """Remove encumbrance flag from listing"""
    data = await request.json()
    listing_id = data.get('listing_id')

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE listings
                SET has_encumbrances = FALSE,
                    is_error = FALSE,
                    encumbrance_types = NULL
                WHERE id = %s
            """, (listing_id,))
            conn.commit()

    return JSONResponse({"success": True})

@app.post("/send_to_telegram")
async def send_to_telegram(request: Request):
    """Send listing to Telegram for review"""
    import httpx

    data = await request.json()
    listing_id = data.get('listing_id')
    comment = data.get('comment', '')

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    thread_id = os.getenv('TELEGRAM_THREAD_ID')

    if not bot_token or not chat_id:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=500)

    # Get listing data
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    l.id, l.url, l.address, l.address_full,
                    l.rooms, l.area_total, l.floor, l.total_floors,
                    l.has_encumbrances, l.encumbrance_types, l.description,
                    lp.price
                FROM listings l
                JOIN LATERAL (
                    SELECT price FROM listing_prices WHERE id = l.id ORDER BY seen_at DESC LIMIT 1
                ) lp ON true
                WHERE l.id = %s
            """, (listing_id,))
            row = cur.fetchone()

            if not row:
                return JSONResponse({"success": False, "error": "Listing not found"}, status_code=404)

            id_, url, address, address_full, rooms, area, floor, floor_total, has_enc, enc_types, description, price = row

            # Format message
            price_per_sqm = int(price / area) if area and area > 0 else 0
            rooms_str = f"{rooms}-комн" if rooms else "Студия"
            floor_str = f"{floor}/{floor_total}" if floor and floor_total else str(floor or "—")
            enc_str = ", ".join(enc_types) if enc_types else "есть"

            # Extract encumbrance context from description
            enc_context = ""
            if description and has_enc:
                for pattern in ENCUMBRANCE_HIGHLIGHT_PATTERNS:
                    match = re.search(pattern, description, re.IGNORECASE)
                    if match:
                        start = max(0, match.start() - 30)
                        end = min(len(description), match.end() + 50)
                        enc_context = f'...{description[start:end]}...'
                        break

            message = f"""🏠 <b>Квартира с обременением</b>

📍 {address_full or address}
💰 {price:,.0f} ₽ ({price_per_sqm:,} ₽/м²)
📐 {area:.0f} м² | {rooms_str} | {floor_str} этаж

⚠️ <b>Обременение:</b> {enc_str}
{f'📝 "{enc_context}"' if enc_context else ''}
{f'💬 <i>{comment}</i>' if comment else ''}

🔗 {url}"""

            # Send to Telegram
            async with httpx.AsyncClient() as client:
                payload = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                if thread_id:
                    payload["message_thread_id"] = int(thread_id)

                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload
                )

                if response.status_code == 200:
                    # Mark as sent
                    cur.execute("""
                        UPDATE listings SET sent_to_tg = TRUE, sent_to_tg_at = NOW() WHERE id = %s
                    """, (listing_id,))
                    conn.commit()
                    return JSONResponse({"success": True})
                else:
                    return JSONResponse({"success": False, "error": response.text}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    print("Starting web viewer on http://51.75.16.178:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
