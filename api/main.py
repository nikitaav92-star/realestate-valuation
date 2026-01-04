"""FastAPI service providing aggregated metrics from the warehouse."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, List

import psycopg2
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection as PGConnection
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="RealEstate Metrics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_conn() -> Generator[PGConnection, None, None]:
    dsn = os.getenv("PG_DSN")
    if not dsn:
        raise HTTPException(status_code=500, detail="PG_DSN is not configured")
    conn = psycopg2.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


class MedianPriceItem(BaseModel):
    region: int
    rooms: int
    deal_type: str
    median_price_per_sqm: float


class DomItem(BaseModel):
    id: int
    dom_days: float


class PriceDropItem(BaseModel):
    id: int
    seen_at: str
    price: float
    prev_price: float
    drop_percent: float


@app.get("/health", response_class=Response)
def health() -> Response:
    return Response(content="ok", media_type="text/plain")


@app.get("/metrics/median-price", response_model=List[MedianPriceItem])
def median_price() -> List[MedianPriceItem]:
    query = """
        SELECT
            l.region,
            l.rooms,
            l.deal_type,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.price / NULLIF(l.area_total, 0))
                AS median_price_per_sqm
        FROM listings AS l
        JOIN listing_prices AS p ON p.id = l.id
        GROUP BY l.region, l.rooms, l.deal_type
        ORDER BY l.region, l.rooms, l.deal_type;
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        rows = cur.fetchall()
    items: List[MedianPriceItem] = []
    for row in rows:
        median_value = row["median_price_per_sqm"]
        items.append(
            MedianPriceItem(
                region=row["region"],
                rooms=row["rooms"],
                deal_type=row["deal_type"],
                median_price_per_sqm=float(median_value) if median_value is not None else 0.0,
            )
        )
    return items


@app.get("/metrics/dom", response_model=List[DomItem])
def dom_metrics() -> List[DomItem]:
    query = """
        SELECT
            id,
            EXTRACT(EPOCH FROM (DATE_TRUNC('day', last_seen) - DATE_TRUNC('day', first_seen))) / 86400
                AS dom_days
        FROM listings
        WHERE is_active = FALSE
        ORDER BY dom_days DESC NULLS LAST
        LIMIT 500;
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        rows = cur.fetchall()
    return [
        DomItem(id=row["id"], dom_days=float(row["dom_days"]) if row["dom_days"] is not None else 0.0)
        for row in rows
    ]


@app.get("/metrics/price-drops", response_model=List[PriceDropItem])
def price_drops(threshold: float = 0.05) -> List[PriceDropItem]:
    if threshold <= 0 or threshold >= 1:
        raise HTTPException(status_code=400, detail="threshold must be between 0 and 1")
    query = """
        WITH history AS (
            SELECT
                id,
                seen_at,
                price,
                LAG(price) OVER (PARTITION BY id ORDER BY seen_at) AS prev_price
            FROM listing_prices
        )
        SELECT
            id,
            seen_at,
            price,
            prev_price,
            CASE
                WHEN prev_price IS NULL THEN 0
                ELSE (prev_price - price) / prev_price
            END AS drop_ratio
        FROM history
        WHERE prev_price IS NOT NULL AND price <= (1 - %(threshold)s) * prev_price
        ORDER BY seen_at DESC
        LIMIT 500;
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, {"threshold": threshold})
        rows = cur.fetchall()
    return [
        PriceDropItem(
            id=row["id"],
            seen_at=row["seen_at"].isoformat(),
            price=float(row["price"]),
            prev_price=float(row["prev_price"]),
            drop_percent=float(row["drop_ratio"] * 100),
        )
        for row in rows
    ]
