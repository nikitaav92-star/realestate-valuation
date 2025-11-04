"""CLI entry point for Cursor-friendly data collection tasks."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import orjson
import yaml
from playwright.sync_api import sync_playwright

from etl.collector_cian.fetcher import CianBlockedError, collect, load_payload
from etl.collector_cian.browser_fetcher import collect_with_playwright, parse_listing_detail
from etl.collector_cian.mapper import extract_offers, to_listing, to_price
from etl.upsert import (
    get_db_connection,
    upsert_listing,
    upsert_price_if_changed,
    update_listing_details,
    insert_listing_photos,
)

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
            LOGGER.warning("HTTP access blocked (%s), falling back to Playwright with smart proxy", root_exc)
            responses = collect_with_playwright(payload, pages, use_smart_proxy=False)
        else:
            raise
    count = 0
    for response in responses:
        for offer in extract_offers(response):
            sys.stdout.write(orjson.dumps(offer).decode() + "\n")
            count += 1
    LOGGER.info("pulled_offers=%s", count)


def _process_offers(offers: Iterable[dict], parse_details: bool = False) -> tuple[int, int, int, int]:
    """Process offers: upsert listings and prices, optionally parse details.
    
    Returns:
        Tuple of (listings_count, prices_count, details_count, photos_count)
    """
    conn = get_db_connection()
    listings = prices = details_parsed = photos_inserted = 0
    
    # Collect listing URLs for detail parsing
    listing_urls = []
    
    try:
        for offer in offers:
            listing = to_listing(offer)
            price = to_price(offer)
            upsert_listing(conn, listing)
            if upsert_price_if_changed(conn, listing.id, price.price):
                prices += 1
            listings += 1
            
            # Store URL for detail parsing
            if parse_details and listing.url:
                listing_urls.append((listing.id, listing.url))
        
        conn.commit()
        LOGGER.info("✅ Upserted %d listings, %d new prices", listings, prices)
        
        # Parse details if requested
        if parse_details and listing_urls:
            LOGGER.info("🔍 Starting detailed parsing for %d listings...", len(listing_urls))
            details_parsed, photos_inserted = _parse_listing_details(conn, listing_urls)
            conn.commit()
            
    except Exception as e:
        conn.rollback()
        LOGGER.error("❌ Error processing offers: %s", e)
        raise
    finally:
        conn.close()
    
    return listings, prices, details_parsed, photos_inserted


def _parse_listing_details(conn, listing_urls: list[tuple[int, str]]) -> tuple[int, int]:
    """Parse detailed information for each listing URL using proxy.
    
    Args:
        conn: Database connection
        listing_urls: List of (listing_id, url) tuples
        
    Returns:
        Tuple of (details_parsed_count, photos_inserted_count)
    """
    from etl.collector_cian.proxy_manager import get_random_proxy
    import random
    
    details_count = 0
    photos_count = 0
    
    # Get proxy from pool
    try:
        with open("config/proxy_pool.txt") as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        proxy_url = random.choice(proxies) if proxies else None
    except Exception:
        proxy_url = None
    
    LOGGER.info(f"🔐 Using proxy for detail parsing: {proxy_url[:60] if proxy_url else None}...")
    
    with sync_playwright() as p:
        # Launch browser with proxy
        if proxy_url:
            try:
                # Parse proxy URL: http://user:pass@host:port
                proxy_parts = proxy_url.replace("http://", "").split("@")
                if len(proxy_parts) == 2:
                    auth, server = proxy_parts
                    username, password = auth.split(":")
                    
                    browser = p.chromium.launch(
                        headless=True,
                        proxy={
                            "server": f"http://{server}",
                            "username": username,
                            "password": password
                        }
                    )
                else:
                    LOGGER.warning("Invalid proxy format, launching without proxy")
                    browser = p.chromium.launch(headless=True)
            except Exception as e:
                LOGGER.warning(f"Failed to configure proxy: {e}, launching without proxy")
                browser = p.chromium.launch(headless=True)
        else:
            browser = p.chromium.launch(headless=True)
        
        page = browser.new_page()
        
        try:
            for idx, (listing_id, url) in enumerate(listing_urls, 1):
                try:
                    LOGGER.info(f"[{idx}/{len(listing_urls)}] Parsing details: {url}")
                    
                    # Parse detail page
                    details = parse_listing_detail(page, url)
                    
                    if details:
                        # Update listing with details
                        update_listing_details(conn, listing_id, details)
                        details_count += 1
                        
                        # Insert photos
                        if details.get("photos"):
                            photos = insert_listing_photos(conn, listing_id, details["photos"])
                            photos_count += photos
                            desc_len = len(details.get("description", "")) if details.get("description") else 0
                            photo_count = len(details.get("photos", []))
                            building = details.get("building_type", "N/A")
                            LOGGER.info(f"  ✅ Saved: desc={desc_len} chars, photos={photo_count}, building_type={building}")
                        else:
                            LOGGER.warning(f"  ⚠️ No photos found for listing {listing_id}")
                    else:
                        LOGGER.warning(f"  ❌ Failed to parse details for listing {listing_id}")
                    
                    # Small delay to avoid detection
                    time.sleep(2)
                    
                except Exception as e:
                    LOGGER.error(f"  ❌ Error parsing {url}: {e}")
                    continue
                    
        finally:
            browser.close()
    
    LOGGER.info("✅ Detailed parsing complete: %d listings, %d photos", details_count, photos_count)
    return details_count, photos_count


def command_to_db(payload_path: str, pages: int, parse_details: bool = False) -> None:
    """Fetch offers and load them directly into PostgreSQL.
    
    Args:
        payload_path: Path to YAML payload file
        pages: Number of pages to fetch
        parse_details: If True, parse detailed info (description, photos, dates) for each listing
    """
    payload = _load_payload(payload_path)
    try:
        responses = asyncio.run(collect(payload, pages))
    except Exception as exc:  # pragma: no cover - network dependent
        root_exc = getattr(exc, "__cause__", None) or exc
        if isinstance(root_exc, CianBlockedError):
            LOGGER.warning("HTTP access blocked (%s), falling back to Playwright with smart proxy", root_exc)
            responses = collect_with_playwright(payload, pages, use_smart_proxy=False)
        else:
            raise
    
    offers = (offer for resp in responses for offer in extract_offers(resp))
    listings, prices, details, photos = _process_offers(offers, parse_details=parse_details)
    
    if parse_details:
        LOGGER.info("📊 Summary: listings=%s, new_prices=%s, details_parsed=%s, photos_inserted=%s", 
                   listings, prices, details, photos)
    else:
        LOGGER.info("📊 Summary: listings=%s, new_prices=%s", listings, prices)


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
    to_db_parser.add_argument(
        "--parse-details",
        action="store_true",
        default=True,
        help="Parse detailed information (description, photos, publication date) for each listing (default: True)",
    )
    to_db_parser.add_argument(
        "--no-parse-details",
        action="store_false",
        dest="parse_details",
        help="Skip detailed parsing (faster but less data)",
    )
    
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "pull":
        command_pull(args.payload, args.pages)
    elif args.cmd == "to-db":
        command_to_db(args.payload, args.pages, parse_details=getattr(args, "parse_details", False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
