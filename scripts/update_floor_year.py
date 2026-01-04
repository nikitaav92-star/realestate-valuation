#!/usr/bin/env python3
"""
Script to update floor, total_floors, and house_year for existing listings.

This script re-parses detail pages for listings that are missing this data.
"""
import sys
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from etl.upsert import get_db_connection, update_listing_details
from etl.collector_cian.browser_fetcher import parse_listing_detail
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
LOGGER = logging.getLogger(__name__)


def get_listings_missing_data(conn, limit: int = 100):
    """Get listings that need floor/year data."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, url
            FROM listings
            WHERE (floor IS NULL OR total_floors IS NULL OR house_year IS NULL)
            AND url IS NOT NULL
            AND url LIKE '%%cian.ru%%'
            LIMIT %s;
            """,
            (limit,)
        )
        return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(description='Update floor and year for existing listings')
    parser.add_argument('--limit', type=int, default=50, help='Max listings to process')
    parser.add_argument('--dry-run', action='store_true', help='Don\'t save to DB')
    args = parser.parse_args()

    conn = get_db_connection()
    listings = get_listings_missing_data(conn, args.limit)

    if not listings:
        LOGGER.info("No listings need floor/year update")
        return

    LOGGER.info(f"Found {len(listings)} listings to update")

    storage_path = Path(__file__).parent.parent / 'config' / 'cian_browser_state.json'

    success = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            storage_state=str(storage_path) if storage_path.exists() else None
        )
        page = context.new_page()

        for i, (listing_id, url) in enumerate(listings):
            LOGGER.info(f"[{i+1}/{len(listings)}] Processing {listing_id}: {url}")

            try:
                details = parse_listing_detail(page, url)

                if details:
                    floor = details.get('floor')
                    total_floors = details.get('total_floors')
                    house_year = details.get('house_year')

                    LOGGER.info(f"  -> floor={floor}, total_floors={total_floors}, house_year={house_year}")

                    if not args.dry_run:
                        update_listing_details(conn, listing_id, details)
                        conn.commit()

                    success += 1
                else:
                    LOGGER.warning(f"  -> Failed to parse details")
                    failed += 1

            except Exception as e:
                LOGGER.error(f"  -> Error: {e}")
                failed += 1

        browser.close()

    LOGGER.info(f"\nComplete: {success} success, {failed} failed")

    # Show stats after update
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(floor) as with_floor,
                COUNT(total_floors) as with_total_floors,
                COUNT(house_year) as with_year
            FROM listings;
        """)
        row = cur.fetchone()
        LOGGER.info(f"DB Stats: total={row[0]}, with_floor={row[1]}, with_total_floors={row[2]}, with_year={row[3]}")

    conn.close()


if __name__ == '__main__':
    main()
