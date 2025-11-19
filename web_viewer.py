"""
Simple web viewer for realestate listings
Run: python web_viewer.py
Access: http://51.75.16.178:8000
"""
import os
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import psycopg2
from dotenv import load_dotenv

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
    sort: str = Query("price_asc", pattern="^(price_asc|price_desc|area_asc|area_desc|rooms_asc|rooms_desc|recent)$")
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
    
    query = f"""
    SELECT 
        l.id,
        l.url,
        l.address,
        l.rooms,
        l.area_total,
        l.floor,
        l.total_floors,
        lp.price,
        l.first_seen::date as first_seen
    FROM listings l
    JOIN listing_prices lp ON l.id = lp.id
    {where_sql}
    ORDER BY {order_by}
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
                <button type="submit">Apply Filters</button>
                <button type="button" onclick="window.location.href='/'">Reset</button>
            </form>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Address</th>
                    <th>Rooms</th>
                    <th>Area (m²)</th>
                    <th>Floor</th>
                    <th>Price (₽)</th>
                    <th>Price/m² (₽)</th>
                    <th>First Seen</th>
                    <th>Link</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for listing in listings:
        id_, url, address, rooms, area, floor, floor_total, price, first_seen = listing
        price_per_sqm = int(price / area) if area and area > 0 else 0
        floor_str = f"{floor}/{floor_total}" if floor and floor_total else (str(floor) if floor else "—")
        rooms_str = f"{rooms}-room" if rooms else "—"
        
        html += f"""
                <tr>
                    <td>{id_}</td>
                    <td>{address}</td>
                    <td class="rooms">{rooms_str}</td>
                    <td>{area:.1f}</td>
                    <td>{floor_str}</td>
                    <td class="price">{price:,.0f}</td>
                    <td>{price_per_sqm:,}</td>
                    <td>{first_seen}</td>
                    <td><a href="{url}" target="_blank">View</a></td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
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

if __name__ == "__main__":
    import uvicorn
    print("Starting web viewer on http://51.75.16.178:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
