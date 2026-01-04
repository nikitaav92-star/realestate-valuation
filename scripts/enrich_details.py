#!/usr/bin/env python3
"""Enrich existing listings with detailed information (description, photos, etc.)

This script fetches listings from the database that don't have descriptions
and parses their detail pages to add missing information.
"""
import os
import sys
import logging
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from etl.upsert import get_db_connection, update_listing_details, insert_listing_photos
from etl.collector_cian.browser_fetcher import parse_listing_detail, RateLimitError, setup_route_blocking
# ВАЖНО: Прокси НЕ используется для парсинга! Только куки + задержки.
# Прокси только для обновления кук (отдельный скрипт)
from playwright.sync_api import sync_playwright
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)
LOGGER = logging.getLogger(__name__)


def get_listings_without_description(conn, limit: int = 500, rooms: int = None):
    """Get listings that need enrichment (no description)."""
    with conn.cursor() as cur:
        if rooms is not None:
            cur.execute("""
                SELECT id, url FROM listings
                WHERE description IS NULL AND rooms = %s
                ORDER BY first_seen DESC
                LIMIT %s
            """, (rooms, limit))
        else:
            cur.execute("""
                SELECT id, url FROM listings
                WHERE description IS NULL
                ORDER BY first_seen DESC
                LIMIT %s
            """, (limit,))
        return cur.fetchall()


def enrich_listings(limit: int = 500, rooms: int = None):
    """Enrich listings with detailed information."""

    conn = get_db_connection()
    listings = get_listings_without_description(conn, limit, rooms)

    if not listings:
        LOGGER.info("✅ No listings to enrich")
        return

    LOGGER.info(f"📋 Found {len(listings)} listings to enrich")

    # Storage path for cookies
    storage_path = Path(os.getenv("CIAN_STORAGE_STATE", "config/cian_browser_state.json"))

    # NO PROXY! Only cookies + delays
    rate_limit_count = 0
    max_rate_limits = 3  # Stop after 3 rate limits (cookies likely expired)
    base_delay = 10  # Base delay between requests

    enriched = 0
    failed = 0

    try:
        with sync_playwright() as p:
            # Start WITHOUT proxy - use cookies and longer delays
            LOGGER.info("🌐 Starting without proxy (using cookies + delays)")
            browser = p.chromium.launch(headless=True)

            context_kwargs = {
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            if storage_path.exists():
                context_kwargs["storage_state"] = str(storage_path)

            context = browser.new_context(**context_kwargs)
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            page = context.new_page()

            for idx, (listing_id, url) in enumerate(listings, 1):
                try:
                    LOGGER.info(f"[{idx}/{len(listings)}] Enriching: {url}")

                    details = None
                    try:
                        details = parse_listing_detail(page, url, max_duration=60)
                    except RateLimitError:
                        rate_limit_count += 1
                        LOGGER.warning(f"🚫 Rate limited! Count: {rate_limit_count}/{max_rate_limits}")

                        if rate_limit_count >= max_rate_limits:
                            LOGGER.error("❌ Too many rate limits - cookies likely expired!")
                            LOGGER.error("💡 Run: python config/get_cookies_with_proxy.py --force")
                            break

                        # Wait longer with exponential backoff (NO PROXY!)
                        wait_time = base_delay * (2 ** rate_limit_count)
                        LOGGER.info(f"⏳ Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)

                        # Retry once
                        try:
                            details = parse_listing_detail(page, url, max_duration=60)
                        except RateLimitError:
                            LOGGER.warning("🚫 Still rate limited, skipping this listing")
                            failed += 1
                            continue
                    except Exception as e:
                        LOGGER.error(f"❌ Error: {e}")
                        failed += 1
                        continue

                    if details:
                        # Skip shares, rooms, newbuildings
                        property_type = details.get("property_type", "").lower() if details.get("property_type") else ""
                        if property_type in ("newbuilding", "share", "room"):
                            LOGGER.info(f"  ⏭️ Skipping {property_type}")
                            continue

                        description = details.get("description")

                        # Update database
                        update_listing_details(conn, listing_id, details)
                        conn.commit()

                        # Insert photos
                        if details.get("photos"):
                            insert_listing_photos(conn, listing_id, details["photos"])
                            conn.commit()

                        enriched += 1
                        LOGGER.info(f"  ✅ Enriched: desc={len(description or '')} chars, photos={len(details.get('photos', []))}")
                    else:
                        failed += 1

                    time.sleep(base_delay)  # Delay between requests to avoid rate limiting

                except Exception as e:
                    LOGGER.error(f"❌ Error enriching {url}: {e}")
                    failed += 1
                    continue

            browser.close()

    except Exception as e:
        LOGGER.error(f"❌ Fatal error: {e}")

    finally:
        conn.close()

    LOGGER.info(f"✅ Done: enriched={enriched}, failed={failed}, rate_limits={rate_limit_count}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500, help="Max listings to enrich")
    parser.add_argument("--rooms", type=int, help="Only enrich specific room count")
    args = parser.parse_args()

    enrich_listings(limit=args.limit, rooms=args.rooms)
