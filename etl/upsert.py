import os
import psycopg2
from etl.models import Listing

def get_db_connection():
    dsn = os.getenv("PG_DSN")
    if not dsn:
        raise RuntimeError("PG_DSN is not set")
    return psycopg2.connect(dsn)

def upsert_listing(conn, listing: Listing):
    with conn.cursor() as cur:
        sql = ("INSERT INTO listings (id, url, region, deal_type, rooms, area_total, floor, address, seller_type, first_seen, last_seen, is_active) "
               "VALUES (, , , , , , , , , NOW(), NOW(), TRUE) "
               "ON CONFLICT (id) DO UPDATE SET "
               "url=EXCLUDED.url, region=EXCLUDED.region, deal_type=EXCLUDED.deal_type, rooms=EXCLUDED.rooms, "
               "area_total=EXCLUDED.area_total, floor=EXCLUDED.floor, address=EXCLUDED.address, seller_type=EXCLUDED.seller_type, "
               "last_seen=NOW(), is_active=TRUE;")
        cur.execute(sql, (listing.id, listing.url, listing.region, listing.deal_type, listing.rooms,
                          listing.area_total, listing.floor, listing.address, listing.seller_type))
        conn.commit()

def upsert_price_if_changed(conn, listing_id: int, new_price: float):
    with conn.cursor() as cur:
        cur.execute("SELECT price FROM listing_prices WHERE id =  ORDER BY seen_at DESC LIMIT 1;", (listing_id,))
        row = cur.fetchone()
        if row is None or row[0] != new_price:
            cur.execute("INSERT INTO listing_prices (id, seen_at, price) VALUES (, NOW(), );", (listing_id, new_price))
        conn.commit()
