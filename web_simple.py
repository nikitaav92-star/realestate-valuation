"""Simple web viewer"""
import os; import psycopg2
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def index(limit: int = Query(50), rooms: Optional[int] = None, min_price: Optional[int] = None, max_price: Optional[int] = None, sort: str = "price_asc"):
    conn = psycopg2.connect(os.getenv("PG_DSN"))
    cur = conn.cursor()
    
    where = []
    params = {"limit": limit}
    if rooms:
        where.append("l.rooms = %(rooms)s")
        params["rooms"] = rooms
    if min_price:
        where.append("lp.price >= %(min_price)s")
        params["min_price"] = min_price
    if max_price:
        where.append("lp.price <= %(max_price)s")
        params["max_price"] = max_price
    
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    sort_sql = {"price_asc": "lp.price", "price_desc": "lp.price DESC", "area_asc": "l.area_total", "recent": "l.first_seen DESC"}.get(sort, "lp.price")
    
    cur.execute(f"SELECT l.id, l.url, l.address, l.rooms, l.area_total, l.floor, l.total_floors, lp.price, l.first_seen::date FROM listings l JOIN listing_prices lp ON l.id = lp.id {where_sql} ORDER BY {sort_sql} LIMIT %(limit)s", params)
    listings = cur.fetchall()
    cur.execute("SELECT COUNT(*), AVG(price)::bigint, MIN(price)::bigint, MAX(price)::bigint FROM listing_prices")
    total, avg, min_p, max_p = cur.fetchone()
    conn.close()
    
    html = f'<html><head><meta charset="utf-8"><title>Realestate</title><style>body{{font-family:Arial;margin:20px;background:#f5f5f5}}table{{width:100%;border-collapse:collapse;background:white}}th{{background:#007bff;color:white;padding:12px}}td{{padding:10px;border-bottom:1px solid #eee}}tr:hover{{background:#f9f9f9}}a{{color:#007bff;text-decoration:none}}.price{{color:#28a745;font-weight:bold}}</style></head><body><h1>🏠 Realestate Listings</h1><p>Total: {total:,} | Avg: {avg:,} ₽ | Range: {min_p:,} - {max_p:,} ₽</p><form><input name="rooms" placeholder="Rooms" value="{rooms or ""}" style="padding:8px"> <input name="min_price" placeholder="Min Price" value="{min_price or ""}" style="padding:8px"> <input name="max_price" placeholder="Max Price" value="{max_price or ""}" style="padding:8px"> <select name="sort" style="padding:8px"><option value="price_asc">Price ↑</option><option value="price_desc">Price ↓</option><option value="area_asc">Area ↑</option><option value="recent">Recent</option></select> <input name="limit" value="{limit}" style="padding:8px;width:60px"> <button type="submit" style="padding:8px 20px;background:#007bff;color:white;border:none;cursor:pointer">Filter</button> <button type="button" onclick="location=\'/\'" style="padding:8px 20px;background:#6c757d;color:white;border:none;cursor:pointer">Reset</button></form><br><table><tr><th>ID</th><th>Address</th><th>Rooms</th><th>Area</th><th>Floor</th><th>Price</th><th>₽/m²</th><th>Date</th><th>Link</th></tr>'
    
    for id_, url, addr, r, area, fl, flt, price, date in listings:
        psqm = int(price/area) if area else 0
        fstr = f"{fl}/{flt}" if fl and flt else (str(fl) if fl else "—")
        rstr = f"{r}" if r else "—"
        html += f'<tr><td>{id_}</td><td>{addr}</td><td>{rstr}</td><td>{area:.1f}</td><td>{fstr}</td><td class="price">{price:,.0f}</td><td>{psqm:,}</td><td>{date}</td><td><a href="{url}" target="_blank">View</a></td></tr>'
    
    html += '</table></body></html>'
    return html

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
