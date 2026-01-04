#!/usr/bin/env python3
"""Update detailed information (area_living, area_kitchen, etc.) for existing listings.

This script fetches listings that are missing detailed info and parses their detail pages.
"""

import os
import sys
import time
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from playwright.sync_api import sync_playwright

from etl.collector_cian.browser_fetcher import parse_listing_detail, RateLimitError, setup_route_blocking
from etl.collector_cian.proxy_manager import ProxyRotator, ProxyConfig
from etl.upsert import update_listing_details

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection from environment."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        dbname=os.getenv("POSTGRES_DB", "realdb"),
        user=os.getenv("POSTGRES_USER", "realuser"),
        password=os.getenv("POSTGRES_PASSWORD", "strongpass123"),
    )


def get_listings_without_details(conn, limit: int = 1000) -> list[tuple[int, str]]:
    """Get listings that are missing area_living."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, url
            FROM listings
            WHERE area_living IS NULL
              AND url IS NOT NULL
              AND is_active = true
            ORDER BY last_seen DESC
            LIMIT %s
        """, (limit,))
        return cur.fetchall()


def update_details_batch(listing_urls: list[tuple[int, str]], batch_size: int = 100) -> tuple[int, int]:
    """Update details for a batch of listings.

    Returns:
        Tuple of (success_count, failure_count)
    """
    success_count = 0
    failure_count = 0

    storage_path = Path(os.getenv("CIAN_STORAGE_STATE", "config/cian_browser_state.json"))
    proxy_rotator = ProxyRotator()
    using_proxy = False
    current_proxy_url = None
    consecutive_failures = 0
    max_consecutive_failures = 20  # Increased tolerance
    network_errors = 0
    max_network_errors = 5

    conn = get_db_connection()

    def create_browser_context(p, with_proxy=False, proxy_url=None):
        """Helper to create browser and context."""
        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if storage_path.exists():
            context_kwargs["storage_state"] = str(storage_path)

        if with_proxy and proxy_url:
            proxy_config = ProxyConfig.from_url(proxy_url)
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": proxy_config.server,
                    "username": proxy_config.username,
                    "password": proxy_config.password,
                }
            )
        else:
            browser = p.chromium.launch(headless=True)

        context = browser.new_context(**context_kwargs)
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        # ВАЖНО: блокируем CDN, картинки, аналитику - экономим прокси трафик!
        setup_route_blocking(context)
        page = context.new_page()
        return browser, context, page

    try:
        with sync_playwright() as p:
            # Start without proxy
            LOGGER.info(f"📂 Loading cookies from {storage_path}")
            browser, context, page = create_browser_context(p, with_proxy=False)

            for idx, (listing_id, url) in enumerate(listing_urls, 1):
                try:
                    LOGGER.info(f"[{idx}/{len(listing_urls)}] Parsing: {url}")

                    details = None
                    try:
                        details = parse_listing_detail(page, url, max_duration=60)
                        network_errors = 0  # Reset on success
                    except RateLimitError:
                        LOGGER.warning("  🚫 Rate limited! Switching to proxy...")

                        if current_proxy_url:
                            proxy_rotator.mark_failure(current_proxy_url, "rate_limit")

                        current_proxy_url = proxy_rotator.get_next_proxy()
                        if not current_proxy_url:
                            LOGGER.error("  ❌ No proxies available!")
                            break

                        # Recreate browser with proxy
                        try:
                            page.close()
                            context.close()
                            browser.close()
                        except:
                            pass

                        browser, context, page = create_browser_context(p, with_proxy=True, proxy_url=current_proxy_url)
                        using_proxy = True

                        LOGGER.info(f"  🔄 Retrying with proxy...")
                        time.sleep(2)
                        details = parse_listing_detail(page, url, max_duration=60)

                    except Exception as parse_error:
                        error_str = str(parse_error).lower()
                        if 'tunnel' in error_str or 'connection' in error_str or 'network' in error_str:
                            network_errors += 1
                            LOGGER.warning(f"  🔌 Network error ({network_errors}/{max_network_errors}): {parse_error}")

                            if network_errors >= max_network_errors:
                                LOGGER.warning("  🔄 Too many network errors, recreating browser...")
                                try:
                                    page.close()
                                    context.close()
                                    browser.close()
                                except:
                                    pass

                                # Try without proxy first
                                using_proxy = False
                                browser, context, page = create_browser_context(p, with_proxy=False)
                                network_errors = 0
                                time.sleep(3)
                                continue
                        else:
                            raise

                    if details:
                        # Update database
                        update_listing_details(conn, listing_id, details)
                        conn.commit()

                        area_living = details.get("area_living")
                        area_kitchen = details.get("area_kitchen")
                        LOGGER.info(f"  ✅ Updated: living={area_living}, kitchen={area_kitchen}")

                        success_count += 1
                        consecutive_failures = 0

                        if using_proxy and current_proxy_url:
                            proxy_rotator.mark_success(current_proxy_url)
                    else:
                        LOGGER.warning(f"  ⚠️ No details extracted")
                        failure_count += 1
                        consecutive_failures += 1

                    # Small delay between requests
                    time.sleep(1.5)

                except Exception as e:
                    LOGGER.error(f"  ❌ Error: {e}")
                    failure_count += 1
                    consecutive_failures += 1
                    try:
                        conn.rollback()
                    except:
                        pass

                if consecutive_failures >= max_consecutive_failures:
                    LOGGER.error(f"❌ Too many consecutive failures ({max_consecutive_failures}). Stopping.")
                    break

                # Commit every batch_size items
                if idx % batch_size == 0:
                    conn.commit()
                    LOGGER.info(f"📊 Progress: {idx}/{len(listing_urls)}, success={success_count}, fail={failure_count}")

            try:
                browser.close()
            except:
                pass

    finally:
        conn.commit()
        conn.close()

    return success_count, failure_count


def main():
    parser = argparse.ArgumentParser(description="Update listing details")
    parser.add_argument("--limit", type=int, default=1000, help="Max listings to process")
    parser.add_argument("--batch", type=int, default=100, help="Commit every N items")
    args = parser.parse_args()

    conn = get_db_connection()

    # Get listings without details
    LOGGER.info(f"🔍 Finding listings without area_living (limit={args.limit})...")
    listings = get_listings_without_details(conn, limit=args.limit)
    conn.close()

    if not listings:
        LOGGER.info("✅ All listings have details!")
        return

    LOGGER.info(f"📋 Found {len(listings)} listings to update")

    # Update details
    success, failure = update_details_batch(listings, batch_size=args.batch)

    LOGGER.info(f"""
=== РЕЗУЛЬТАТЫ ===
Обработано: {len(listings)}
Успешно: {success}
Ошибок: {failure}
""")


if __name__ == "__main__":
    main()
