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
    
    newbuildings_skipped = 0
    shares_skipped = 0
    apartments_skipped = 0
    
    try:
        for offer in offers:
            try:
                listing = to_listing(offer)
            except ValueError as e:
                # Skip newbuildings, apartment shares, and apartments
                error_msg = str(e)
                if "Newbuilding" in error_msg:
                    newbuildings_skipped += 1
                    continue
                elif "Apartment share" in error_msg or "share" in error_msg.lower():
                    shares_skipped += 1
                    continue
                elif "Apartment detected" in error_msg or "apartment" in error_msg.lower():
                    apartments_skipped += 1
                    continue
                raise
            
            price = to_price(offer)
            upsert_listing(conn, listing)
            if upsert_price_if_changed(conn, listing.id, price.price):
                prices += 1
            listings += 1
            
            # Store URL for detail parsing
            if parse_details and listing.url:
                listing_urls.append((listing.id, listing.url))
        
        conn.commit()
        skip_info = []
        if newbuildings_skipped > 0:
            skip_info.append(f"{newbuildings_skipped} newbuildings")
        if shares_skipped > 0:
            skip_info.append(f"{shares_skipped} shares")
        if apartments_skipped > 0:
            skip_info.append(f"{apartments_skipped} apartments")
        
        if skip_info:
                LOGGER.info("✅ Upserted %d listings, %d new prices, skipped: %s", 
                    listings, prices, ", ".join(skip_info))
        else:
            LOGGER.info("✅ Upserted %d listings, %d new prices", listings, prices)
        
        # Parse details if requested
        if parse_details and listing_urls:
            LOGGER.info("🔍 Starting detailed parsing for %d listings...", len(listing_urls))
            try:
                details_parsed, photos_inserted = _parse_listing_details(conn, listing_urls)
                # Final commit after all details are parsed
                conn.commit()
                LOGGER.info("✅ All details parsed and committed to database")
            except Exception as e:
                # Commit any partial progress before re-raising
                try:
                    conn.commit()
                    LOGGER.info("✅ Committed partial progress before error")
                except:
                    conn.rollback()
                    LOGGER.warning("⚠️ Rolled back transaction due to commit error")
                # Log error but don't fail completely - partial data is better than no data
                LOGGER.error(f"❌ Error during detailed parsing: {e}")
                # Set defaults if parsing failed
                details_parsed = 0
                photos_inserted = 0
            
    except Exception as e:
        conn.rollback()
        LOGGER.error("❌ Error processing offers: %s", e)
        raise
    finally:
        conn.close()
    
    return listings, prices, details_parsed, photos_inserted


def _create_browser_with_proxy_auto(p, proxy_url: Optional[str], max_retries: int = 3) -> tuple:
    """Create browser with proxy, automatically refreshing proxy on failure.
    
    Returns:
        Tuple of (browser, proxy_url) - browser instance and used proxy URL
    """
    from etl.collector_cian.proxy_manager import get_validated_proxy, ProxyConfig
    
    for attempt in range(max_retries):
        try:
            # Get validated proxy (will auto-refresh if needed)
            if not proxy_url:
                proxy_url = get_validated_proxy(auto_refresh=True)
            
            if not proxy_url:
                LOGGER.warning("No proxy available, launching without proxy")
                return p.chromium.launch(headless=True), None
            
            # Parse proxy URL
            proxy_config = ProxyConfig.from_url(proxy_url)
            
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": proxy_config.server,
                    "username": proxy_config.username,
                    "password": proxy_config.password
                }
            )
            
            LOGGER.info(f"✅ Browser created with proxy: {proxy_config.server}")
            return browser, proxy_url
            
        except Exception as e:
            LOGGER.warning(f"⚠️ Failed to create browser with proxy (attempt {attempt + 1}/{max_retries}): {e}")
            proxy_url = None  # Force refresh on next attempt
            
            if attempt < max_retries - 1:
                LOGGER.info("🔄 Refreshing proxy and retrying...")
                time.sleep(2)
            else:
                LOGGER.error("❌ Failed to create browser with proxy after retries, launching without proxy")
                return p.chromium.launch(headless=True), None
    
    return p.chromium.launch(headless=True), None


def _parse_listing_details(conn, listing_urls: list[tuple[int, str]]) -> tuple[int, int]:
    """Parse detailed information for each listing URL using proxy with auto-refresh.
    
    Args:
        conn: Database connection
        listing_urls: List of (listing_id, url) tuples
        
    Returns:
        Tuple of (details_parsed_count, photos_inserted_count)
    """
    from etl.collector_cian.proxy_manager import get_validated_proxy
    
    details_count = 0
    photos_count = 0
    
    # Get validated proxy (will auto-refresh if needed)
    proxy_url = get_validated_proxy(auto_refresh=True)
    
    if proxy_url:
        LOGGER.info(f"🔐 Using validated proxy for detail parsing: {proxy_url[:60]}...")
    else:
        LOGGER.warning("⚠️ No proxy available, will try without proxy")
    
    consecutive_failures = 0
    max_consecutive_failures = 5  # Refresh proxy after 5 consecutive failures
    
    browser = None
    page = None
    current_proxy = proxy_url
    
    try:
        with sync_playwright() as p:
            browser, current_proxy = _create_browser_with_proxy_auto(p, proxy_url)
            page = browser.new_page()
            
            for idx, (listing_id, url) in enumerate(listing_urls, 1):
                try:
                    LOGGER.info(f"[{idx}/{len(listing_urls)}] Parsing details: {url}")
                    
                    # Parse detail page with EPIPE handling
                    details = None
                    try:
                        details = parse_listing_detail(page, url)
                    except Exception as parse_error:
                        error_str = str(parse_error)
                        # Handle EPIPE error (Playwright pipe closed) - this is non-fatal
                        is_epipe_error = any(keyword in error_str for keyword in [
                            "EPIPE",
                            "write EPIPE",
                            "Broken pipe",
                            "Connection reset by peer",
                            "errno: -32"
                        ])
                        
                        if is_epipe_error:
                            LOGGER.warning(f"  ⚠️ EPIPE error (browser connection lost): {error_str[:100]}")
                            LOGGER.info("  🔄 Recreating browser connection...")
                            try:
                                if browser:
                                    browser.close()
                            except:
                                pass
                            
                            # Recreate browser and page
                            try:
                                browser, current_proxy = _create_browser_with_proxy_auto(p, current_proxy)
                                page = browser.new_page()
                                consecutive_failures = 0
                                LOGGER.info("  ✅ Browser recreated, retrying...")
                                # Retry parsing
                                details = parse_listing_detail(page, url)
                            except Exception as recreate_error:
                                LOGGER.error(f"  ❌ Failed to recreate browser: {recreate_error}")
                                # Commit any partial progress before continuing
                                try:
                                    conn.commit()
                                except:
                                    pass
                                continue
                        else:
                            raise  # Re-raise non-EPIPE errors
                    
                    if details:
                        # Reset failure counter on success
                        consecutive_failures = 0
                        
                        try:
                            # Update listing with details
                            update_listing_details(conn, listing_id, details)
                            details_count += 1
                            
                            # Commit after each successful update to ensure data is saved
                            conn.commit()
                            
                            # Normalize address using FIAS if address_full is available
                            address_full = details.get("address_full")
                            if address_full:
                                try:
                                    from etl.fias_normalizer import normalize_address
                                    from etl.upsert import upsert_fias_data
                                    
                                    fias_data = normalize_address(address_full)
                                    if fias_data:
                                        upsert_fias_data(
                                            conn, listing_id,
                                            fias_address=fias_data.get("fias_address"),
                                            fias_id=fias_data.get("fias_id"),
                                            postal_code=fias_data.get("postal_code"),
                                            quality_code=fias_data.get("quality_code"),
                                        )
                                        conn.commit()  # Commit FIAS data
                                        LOGGER.debug(f"  📍 Address normalized: {fias_data.get('quality_code')}")
                                except Exception as e:
                                    LOGGER.warning(f"  ⚠️ Failed to normalize address: {e}")
                                    # Don't fail the whole process if normalization fails
                            
                            # Insert photos
                            if details.get("photos"):
                                photos = insert_listing_photos(conn, listing_id, details["photos"])
                                conn.commit()  # Commit photos
                                photos_count += photos
                                desc_len = len(details.get("description", "")) if details.get("description") else 0
                                photo_count = len(details.get("photos", []))
                                building = details.get("building_type", "N/A")
                                LOGGER.info(f"  ✅ Saved: desc={desc_len} chars, photos={photo_count}, building_type={building}")
                            else:
                                LOGGER.warning(f"  ⚠️ No photos found for listing {listing_id}")
                        except Exception as save_error:
                            LOGGER.error(f"  ❌ Error saving details for listing {listing_id}: {save_error}")
                            # Try to commit partial progress
                            try:
                                conn.commit()
                            except:
                                conn.rollback()
                            continue
                    else:
                        consecutive_failures += 1
                        error_msg = "Failed to parse details"
                        
                        # Check if it's a proxy error
                        if "ERR_TUNNEL_CONNECTION_FAILED" in str(error_msg) or "proxy" in str(error_msg).lower():
                            LOGGER.warning(f"  ⚠️ Proxy error detected (failures: {consecutive_failures}/{max_consecutive_failures})")
                            
                            # Refresh proxy if too many failures
                            if consecutive_failures >= max_consecutive_failures:
                                LOGGER.info("🔄 Too many proxy failures, refreshing proxy...")
                                try:
                                    browser.close()
                                except:
                                    pass
                                current_proxy = get_validated_proxy(auto_refresh=True)
                                browser, current_proxy = _create_browser_with_proxy_auto(p, current_proxy)
                                page = browser.new_page()
                                consecutive_failures = 0
                                LOGGER.info("✅ Proxy refreshed, continuing...")
                        
                        LOGGER.warning(f"  ❌ Failed to parse details for listing {listing_id}")
                    
                    # Small delay to avoid detection
                    time.sleep(2)
                    
                except Exception as e:
                    consecutive_failures += 1
                    error_str = str(e)
                    
                    # Handle EPIPE error at exception level
                    is_epipe_error = any(keyword in error_str for keyword in [
                        "EPIPE",
                        "write EPIPE",
                        "Broken pipe",
                        "Connection reset by peer",
                        "errno: -32"
                    ])
                    
                    if is_epipe_error:
                        LOGGER.warning(f"  ⚠️ EPIPE error: {error_str[:100]} (failures: {consecutive_failures}/{max_consecutive_failures})")
                        LOGGER.info("  🔄 Recreating browser connection...")
                        try:
                            if browser:
                                browser.close()
                        except:
                            pass
                        
                        # Recreate browser and page
                        try:
                            browser, current_proxy = _create_browser_with_proxy_auto(p, current_proxy)
                            page = browser.new_page()
                            consecutive_failures = 0
                            LOGGER.info("  ✅ Browser recreated, continuing...")
                        except Exception as recreate_error:
                            LOGGER.error(f"  ❌ Failed to recreate browser: {recreate_error}")
                            # Commit any partial progress before continuing
                            try:
                                conn.commit()
                            except:
                                pass
                        continue
                    
                    # Check if it's a proxy/tunnel error
                    is_proxy_error = any(keyword in error_str for keyword in [
                        "ERR_TUNNEL_CONNECTION_FAILED",
                        "ERR_PROXY_CONNECTION_FAILED",
                        "net::ERR_",
                        "proxy",
                        "tunnel"
                    ])
                    
                    if is_proxy_error:
                        LOGGER.warning(f"  ⚠️ Proxy error: {error_str[:100]} (failures: {consecutive_failures}/{max_consecutive_failures})")
                        
                        # Refresh proxy if too many failures
                        if consecutive_failures >= max_consecutive_failures:
                            LOGGER.info("🔄 Too many proxy failures, refreshing proxy and retrying...")
                            try:
                                browser.close()
                            except:
                                pass
                            
                            current_proxy = get_validated_proxy(auto_refresh=True)
                            browser, current_proxy = _create_browser_with_proxy_auto(p, current_proxy)
                            page = browser.new_page()
                            consecutive_failures = 0
                            LOGGER.info("✅ Proxy refreshed, continuing...")
                    else:
                        LOGGER.error(f"  ❌ Error parsing {url}: {e}")
                    
                    # Commit partial progress even on error
                    try:
                        conn.commit()
                    except:
                        pass
                    
                    continue
                    
    except Exception as e:
        error_str = str(e)
        # Handle EPIPE at top level
        is_epipe_error = any(keyword in error_str for keyword in [
            "EPIPE",
            "write EPIPE",
            "Broken pipe",
            "Connection reset by peer",
            "errno: -32"
        ])
        
        if is_epipe_error:
            LOGGER.warning(f"⚠️ EPIPE error at top level: {error_str[:100]}")
            LOGGER.info("Attempting to continue with remaining listings...")
        else:
            LOGGER.error(f"❌ Fatal error in _parse_listing_details: {e}")
    finally:
        # Ensure browser is closed
        try:
            if browser:
                browser.close()
        except Exception as e:
            # Ignore errors when closing browser (EPIPE is common here)
            if "EPIPE" not in str(e):
                LOGGER.debug(f"Error closing browser: {e}")
    
    LOGGER.info("✅ Detailed parsing complete: %d listings, %d photos", details_count, photos_count)
    return details_count, photos_count


def command_to_db(payload_path: str, pages: int, parse_details: bool = False, unlimited: bool = False) -> None:
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
    
    # TASK-005: Log data quality metrics
    try:
        from etl.upsert import get_db_connection
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_rooms,
                        COUNT(*) FILTER (WHERE area_total IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_area,
                        COUNT(*) FILTER (WHERE address IS NOT NULL AND address != '') * 100.0 / NULLIF(COUNT(*), 0) as pct_address
                    FROM listings
                    WHERE is_active = TRUE
                """)
                row = cur.fetchone()
                if row:
                    total, pct_rooms, pct_area, pct_address = row
                    LOGGER.info("📈 Data Quality: total=%s, rooms=%.1f%%, area=%.1f%%, address=%.1f%%", 
                               total, pct_rooms or 0, pct_area or 0, pct_address or 0)
    except Exception as e:
        LOGGER.warning("Failed to log data quality metrics: %s", e)
    
    # Log execution history
    import datetime
    execution_time = datetime.datetime.now().isoformat()
    
    if parse_details:
        LOGGER.info("📊 Summary: listings=%s, new_prices=%s, details_parsed=%s, photos_inserted=%s", 
                   listings, prices, details, photos)
        LOGGER.info("📝 Execution history: time=%s, pages=%s, parse_details=True, completed=True", 
                   execution_time, pages)
    else:
        LOGGER.info("📊 Summary: listings=%s, new_prices=%s", listings, prices)
        LOGGER.info("📝 Execution history: time=%s, pages=%s, parse_details=False, completed=True", 
                   execution_time, pages)
    
    LOGGER.info("✅ Parser cycle completed successfully. Stopping. (No auto-restart)")


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
