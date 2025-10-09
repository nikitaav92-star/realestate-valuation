"""Prefect flow wiring for daily ingestion."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from etl.collector_cian.fetcher import collect, load_payload
from etl.collector_cian.mapper import extract_offers, to_listing, to_price
from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


@task(retries=3, retry_delay_seconds=30)
def collect_task(payload_path: str, pages: int) -> List[Dict[str, Any]]:
    """Download raw JSON pages using the HTTP collector."""
    logger = get_run_logger()
    payload = load_payload(payload_path)
    responses = asyncio.run(collect(payload, pages))
    offers: List[Dict[str, Any]] = []
    for resp in responses:
        offers.extend(extract_offers(resp))
    logger.info("collect_task pages=%s offers=%s", pages, len(offers))
    return offers


def _persist_offers(offers: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    conn = get_db_connection()
    listings = prices = 0
    try:
        for offer in offers:
            listing = to_listing(offer)
            price = to_price(offer)
            upsert_listing(conn, listing)
            if upsert_price_if_changed(conn, listing.id, price.price):
                prices += 1
            listings += 1
        conn.commit()
    finally:
        conn.close()
    return listings, prices


@task
def load_task(offers: List[Dict[str, Any]]) -> Dict[str, int]:
    """Upsert offers and price history into PostgreSQL."""
    logger = get_run_logger()
    listings, prices = _persist_offers(offers)
    logger.info("load_task listings=%s inserted_prices=%s", listings, prices)
    return {"listings_processed": listings, "inserted_prices": prices}


@task
def deactivate_task() -> int:
    """Deactivate listings that were not seen today."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE listings
                SET is_active = FALSE
                WHERE last_seen::date < NOW()::date;
                """
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    get_run_logger().info("deactivate_task affected=%s", affected)
    return affected


@flow(name="daily-flow")
def daily_flow(
    payload_path: str = "etl/collector_cian/payloads/base.yaml",
    pages: int = 1,
) -> Dict[str, Any]:
    """Daily collect → load → deactivate routine."""
    offers_future = collect_task(payload_path, pages)
    load_summary = load_task(offers_future)
    deactivated = deactivate_task.submit(wait_for=[load_summary])

    summary = {
        "pages": pages,
        "collected_offers": len(offers_future.result()),
        **load_summary.result(),
        "deactivated": deactivated.result(),
    }
    get_run_logger().info("daily_flow summary=%s", json.dumps(summary))
    return summary
