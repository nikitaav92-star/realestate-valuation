"""CLI entry point for Cursor-friendly data collection tasks."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

import orjson
import yaml

from etl.collector_cian.fetcher import CianBlockedError, collect, load_payload
from etl.collector_cian.browser_fetcher import collect_with_playwright
from etl.collector_cian.mapper import extract_offers, to_listing, to_price
from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed

LOGGER = logging.getLogger(__name__)


def _load_payload(path: str) -> dict:
    return load_payload(path)


def command_pull(payload_path: str, pages: int) -> None:
    """Fetch offers and emit raw JSON lines to stdout."""
    payload = _load_payload(payload_path)
    try:
        responses = asyncio.run(collect(payload, pages))
    except Exception as exc:  # pragma: no cover - network dependent
        root_exc = getattr(exc, "__cause__", None) or exc
        if isinstance(root_exc, CianBlockedError):
            LOGGER.warning("HTTP access blocked (%s), falling back to Playwright", root_exc)
            responses = collect_with_playwright(payload, pages)
        else:
            raise
    count = 0
    for response in responses:
        for offer in extract_offers(response):
            sys.stdout.write(orjson.dumps(offer).decode() + "\n")
            count += 1
    LOGGER.info("pulled_offers=%s", count)


def _process_offers(offers: Iterable[dict]) -> tuple[int, int]:
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


def command_to_db(payload_path: str, pages: int) -> None:
    """Fetch offers and load them directly into PostgreSQL."""
    payload = _load_payload(payload_path)
    try:
        responses = asyncio.run(collect(payload, pages))
    except Exception as exc:  # pragma: no cover - network dependent
        root_exc = getattr(exc, "__cause__", None) or exc
        if isinstance(root_exc, CianBlockedError):
            LOGGER.warning("HTTP access blocked (%s), falling back to Playwright", root_exc)
            responses = collect_with_playwright(payload, pages)
        else:
            raise
    offers = (offer for resp in responses for offer in extract_offers(resp))
    listings, prices = _process_offers(offers)
    LOGGER.info("upserted_listings=%s inserted_prices=%s", listings, prices)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CIAN collector CLI")
    sub = parser.add_subparsers(dest="cmd")

    def add_common_arguments(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--payload",
            default="etl/collector_cian/payloads/base.yaml",
            help="Path to YAML payload describing the search filters",
        )
        subparser.add_argument("--pages", type=int, default=1, help="Number of pages to fetch")

    pull_parser = sub.add_parser("pull", help="Fetch data and print JSONL to stdout")
    add_common_arguments(pull_parser)

    to_db_parser = sub.add_parser("to-db", help="Fetch data and upsert into PostgreSQL")
    add_common_arguments(to_db_parser)
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "pull":
        command_pull(args.payload, args.pages)
    elif args.cmd == "to-db":
        command_to_db(args.payload, args.pages)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
