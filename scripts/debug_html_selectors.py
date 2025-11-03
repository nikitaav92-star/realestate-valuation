#!/usr/bin/env python3
"""Debug script to inspect CIAN HTML structure and test selectors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
import logging

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def debug_selectors():
    """Open CIAN page and inspect HTML structure."""
    # Use proxy from pool
    from etl.collector_cian.proxy_manager import get_validated_proxy, ProxyConfig

    proxy_url = get_validated_proxy(auto_refresh=True)
    if not proxy_url:
        LOGGER.error("No valid proxy available")
        return

    proxy_config = ProxyConfig.from_url(proxy_url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # Headless for server
            proxy={
                "server": proxy_config.server,
                "username": proxy_config.username,
                "password": proxy_config.password,
            },
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page = context.new_page()

        # Go to search page
        url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&building_status=secondary&maxprice=30000000&minfloor=2&room0=1&room1=1&room2=1&room3=1&sort=price_object_order_asc"

        LOGGER.info(f"Opening {url}")
        page.goto(url, wait_until="load", timeout=60000)

        # Wait for offers to load
        page.wait_for_timeout(3000)

        # Find all offer cards
        offer_elements = page.query_selector_all("[data-name='LinkArea']")
        LOGGER.info(f"Found {len(offer_elements)} offer cards")

        if offer_elements:
            # Inspect first offer
            first_offer = offer_elements[0]

            LOGGER.info("\n" + "="*80)
            LOGGER.info("FIRST OFFER HTML STRUCTURE:")
            LOGGER.info("="*80)

            # Get full HTML
            html = first_offer.inner_html()
            LOGGER.info(f"\nFull HTML (first 500 chars):\n{html[:500]}\n")

            # Test different selectors
            test_selectors = [
                # Price
                ("Price (data-mark='MainPrice')", "[data-mark='MainPrice']"),
                ("Price (data-testid)", "[data-testid*='price']"),
                ("Price (class)", "[class*='price']"),

                # Address
                ("Address (data-mark='GeoLabel')", "[data-mark='GeoLabel']"),
                ("Address (geo)", "[data-testid*='geo']"),
                ("Address (address)", "[data-testid*='address']"),

                # Title
                ("Title (data-mark='OfferTitle')", "[data-mark='OfferTitle']"),
                ("Title (title)", "[data-testid*='title']"),

                # Info (area, floor, rooms)
                ("Info (data-mark='OfferInfo')", "[data-mark='OfferInfo']"),
                ("Info (params)", "[data-testid*='object-summary']"),

                # All data-mark attributes
                ("All data-mark", "[data-mark]"),

                # All data-testid attributes
                ("All data-testid", "[data-testid]"),
            ]

            for label, selector in test_selectors:
                try:
                    elements = first_offer.query_selector_all(selector)
                    if elements:
                        LOGGER.info(f"\n{label}: {selector}")
                        for idx, elem in enumerate(elements[:3]):  # Show first 3
                            text = elem.inner_text().strip()
                            LOGGER.info(f"  [{idx}] {text[:100]}")
                except Exception as e:
                    LOGGER.warning(f"{label} ERROR: {e}")

            # Save screenshot
            screenshot_path = Path(__file__).parent.parent / "logs/debug_cian_page.png"
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            LOGGER.info(f"\n📸 Screenshot saved: {screenshot_path}")

            # Save HTML
            html_path = Path(__file__).parent.parent / "logs/debug_cian_offer.html"
            html_path.write_text(first_offer.inner_html(), encoding='utf-8')
            LOGGER.info(f"💾 HTML saved: {html_path}")

        browser.close()


if __name__ == "__main__":
    debug_selectors()
