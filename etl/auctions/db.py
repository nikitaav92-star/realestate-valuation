"""
Database operations for auction lots.
Uses SEPARATE database connection from main realestate DB!
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import asyncpg
from asyncpg import Connection, Pool

from .models import AuctionLot, AuctionMarketComparison

logger = logging.getLogger(__name__)

# IMPORTANT: Separate DSN for auctions database!
AUCTIONS_DSN = os.getenv(
    "AUCTIONS_DATABASE_URL",
    os.getenv("AUCTIONS_PG_DSN", "postgresql://realuser:realpass@localhost:5433/auctionsdb")
)


async def get_pool() -> Pool:
    """Get connection pool for auctions database."""
    return await asyncpg.create_pool(AUCTIONS_DSN, min_size=2, max_size=10)


async def get_connection() -> Connection:
    """Get single connection for auctions database."""
    return await asyncpg.connect(AUCTIONS_DSN)


async def upsert_lot(conn: Connection, lot: AuctionLot) -> int:
    """
    Insert or update auction lot.

    Returns:
        lot_id from database
    """
    # Get platform_id if not set
    platform_id = lot.platform_id
    if not platform_id:
        platform_id = await conn.fetchval(
            """
            SELECT id FROM auction_platforms
            WHERE source_type = $1
            LIMIT 1
            """,
            lot.source_type
        )

    # Prepare data
    photos_json = json.dumps(lot.photos) if lot.photos else '[]'
    documents_json = json.dumps(lot.documents) if lot.documents else '[]'
    raw_data_json = json.dumps(lot.raw_data) if lot.raw_data else None

    # Upsert query
    query = """
        INSERT INTO auction_lots (
            external_id, platform_id, source_type, source_url,
            lot_number, case_number,
            property_type, title, description,
            region, city, district, address, address_normalized, fias_id,
            lat, lon,
            area_total, area_living, area_kitchen, rooms, floor, total_floors, building_year,
            initial_price, current_price, step_price, deposit_amount,
            auction_date, auction_end_date, application_deadline,
            status, is_repeat_auction, repeat_number,
            organizer_name, organizer_inn, organizer_contact,
            debtor_name, debtor_inn, bank_name,
            photos, documents, raw_data,
            published_at, last_seen_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6,
            $7, $8, $9,
            $10, $11, $12, $13, $14, $15,
            $16, $17,
            $18, $19, $20, $21, $22, $23, $24,
            $25, $26, $27, $28,
            $29, $30, $31,
            $32, $33, $34,
            $35, $36, $37,
            $38, $39, $40,
            $41::jsonb, $42::jsonb, $43::jsonb,
            $44, NOW()
        )
        ON CONFLICT (platform_id, external_id) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            lot_number = EXCLUDED.lot_number,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            address = COALESCE(EXCLUDED.address, auction_lots.address),
            address_normalized = COALESCE(EXCLUDED.address_normalized, auction_lots.address_normalized),
            lat = COALESCE(EXCLUDED.lat, auction_lots.lat),
            lon = COALESCE(EXCLUDED.lon, auction_lots.lon),
            area_total = COALESCE(EXCLUDED.area_total, auction_lots.area_total),
            rooms = COALESCE(EXCLUDED.rooms, auction_lots.rooms),
            floor = COALESCE(EXCLUDED.floor, auction_lots.floor),
            total_floors = COALESCE(EXCLUDED.total_floors, auction_lots.total_floors),
            current_price = EXCLUDED.current_price,
            auction_date = EXCLUDED.auction_date,
            status = EXCLUDED.status,
            photos = EXCLUDED.photos,
            raw_data = EXCLUDED.raw_data,
            last_seen_at = NOW(),
            updated_at = NOW()
        RETURNING id
    """

    lot_id = await conn.fetchval(
        query,
        lot.external_id,
        platform_id,
        lot.source_type,
        lot.source_url,
        lot.lot_number,
        lot.case_number,
        lot.property_type,
        lot.title,
        lot.description,
        lot.region,
        lot.city,
        lot.district,
        lot.address,
        lot.address_normalized,
        lot.fias_id,
        float(lot.lat) if lot.lat else None,
        float(lot.lon) if lot.lon else None,
        float(lot.area_total) if lot.area_total else None,
        float(lot.area_living) if lot.area_living else None,
        float(lot.area_kitchen) if lot.area_kitchen else None,
        lot.rooms,
        lot.floor,
        lot.total_floors,
        lot.building_year,
        float(lot.initial_price) if lot.initial_price else None,
        float(lot.current_price) if lot.current_price else None,
        float(lot.step_price) if lot.step_price else None,
        float(lot.deposit_amount) if lot.deposit_amount else None,
        lot.auction_date,
        lot.auction_end_date,
        lot.application_deadline,
        lot.status,
        lot.is_repeat_auction,
        lot.repeat_number,
        lot.organizer_name,
        lot.organizer_inn,
        lot.organizer_contact,
        lot.debtor_name,
        lot.debtor_inn,
        lot.bank_name,
        photos_json,
        documents_json,
        raw_data_json,
        lot.published_at,
    )

    return lot_id


async def record_price_history(conn: Connection, lot_id: int, price: float, price_type: str = "current"):
    """Record price change in history."""
    await conn.execute(
        """
        INSERT INTO auction_price_history (lot_id, price, price_type)
        VALUES ($1, $2, $3)
        """,
        lot_id, price, price_type
    )


async def update_market_comparison(
    conn: Connection,
    lot_id: int,
    comparison: AuctionMarketComparison
):
    """Update market comparison for a lot."""
    await conn.execute(
        """
        INSERT INTO auction_market_comparison (
            lot_id, market_price_estimate, market_price_per_sqm,
            estimation_method, estimation_confidence,
            discount_from_market, comparables_count
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (lot_id) DO UPDATE SET
            market_price_estimate = EXCLUDED.market_price_estimate,
            market_price_per_sqm = EXCLUDED.market_price_per_sqm,
            estimation_method = EXCLUDED.estimation_method,
            estimation_confidence = EXCLUDED.estimation_confidence,
            discount_from_market = EXCLUDED.discount_from_market,
            comparables_count = EXCLUDED.comparables_count,
            calculated_at = NOW()
        """,
        lot_id,
        float(comparison.market_price_estimate) if comparison.market_price_estimate else None,
        float(comparison.market_price_per_sqm) if comparison.market_price_per_sqm else None,
        comparison.estimation_method,
        float(comparison.estimation_confidence) if comparison.estimation_confidence else None,
        float(comparison.discount_from_market) if comparison.discount_from_market else None,
        comparison.comparables_count,
    )


async def get_active_lots(
    conn: Connection,
    source_type: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get active auction lots."""
    query = """
        SELECT
            l.*,
            p.name as platform_name,
            mc.market_price_estimate,
            mc.discount_from_market
        FROM auction_lots l
        LEFT JOIN auction_platforms p ON l.platform_id = p.id
        LEFT JOIN auction_market_comparison mc ON l.id = mc.lot_id
        WHERE l.status IN ('announced', 'active')
    """
    params = []
    param_idx = 1

    if source_type:
        query += f" AND l.source_type = ${param_idx}"
        params.append(source_type)
        param_idx += 1

    if city:
        query += f" AND l.city = ${param_idx}"
        params.append(city)
        param_idx += 1

    query += f" ORDER BY l.auction_date ASC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
    params.extend([limit, offset])

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_lot_by_id(conn: Connection, lot_id: int) -> Optional[dict]:
    """Get lot by ID."""
    row = await conn.fetchrow(
        """
        SELECT
            l.*,
            p.name as platform_name,
            mc.market_price_estimate,
            mc.discount_from_market,
            mc.comparables_count
        FROM auction_lots l
        LEFT JOIN auction_platforms p ON l.platform_id = p.id
        LEFT JOIN auction_market_comparison mc ON l.id = mc.lot_id
        WHERE l.id = $1
        """,
        lot_id
    )
    return dict(row) if row else None


async def get_stats(conn: Connection) -> dict:
    """Get auction statistics."""
    stats = {}

    # By source
    rows = await conn.fetch(
        """
        SELECT source_type, status, COUNT(*) as count
        FROM auction_lots
        GROUP BY source_type, status
        ORDER BY source_type, status
        """
    )
    stats['by_source'] = [dict(r) for r in rows]

    # Total counts
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status IN ('announced', 'active')) as active,
            COUNT(*) FILTER (WHERE status = 'completed') as completed,
            AVG(current_price) FILTER (WHERE status IN ('announced', 'active')) as avg_price,
            AVG(price_per_sqm) FILTER (WHERE status IN ('announced', 'active')) as avg_price_per_sqm
        FROM auction_lots
        """
    )
    stats['totals'] = dict(row)

    return stats


async def record_scrape_stats(
    conn: Connection,
    platform_id: int,
    lots_found: int,
    lots_new: int,
    lots_updated: int,
    lots_closed: int,
    errors: int,
    duration_seconds: int,
):
    """Record scraping statistics."""
    await conn.execute(
        """
        INSERT INTO auction_scrape_stats (
            platform_id, lots_found, lots_new, lots_updated,
            lots_closed, errors, duration_seconds
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        platform_id, lots_found, lots_new, lots_updated,
        lots_closed, errors, duration_seconds
    )
