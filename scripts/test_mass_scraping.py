#!/usr/bin/env python3
"""Test mass scraping with proxy rotation and cookie refresh.

Strategy:
1. Use residential proxy for all requests
2. Refresh cookies every N pages (storage state)
3. Track metrics: speed, success rate, blocking
4. Goal: Scrape 100,000 offers

This is the production-ready approach for mass scraping.
"""
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from etl.antibot import (
    HumanBehavior,
    BehaviorPresets,
    ProxyConfig,
    create_stealth_context,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/mass_scraping.log"),
    ],
)

LOGGER = logging.getLogger(__name__)


@dataclass
class ScrapingSession:
    """Metrics for scraping session."""
    
    start_time: float = field(default_factory=time.time)
    pages_scraped: int = 0
    offers_collected: int = 0
    blocks_encountered: int = 0
    captchas_encountered: int = 0
    cookie_refreshes: int = 0
    errors: List[str] = field(default_factory=list)
    
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time
    
    def offers_per_minute(self) -> float:
        """Calculate offers per minute."""
        elapsed_min = self.elapsed_time() / 60
        return self.offers_collected / elapsed_min if elapsed_min > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            **asdict(self),
            "elapsed_time": self.elapsed_time(),
            "offers_per_minute": self.offers_per_minute(),
        }


def is_blocked(page) -> tuple[bool, str]:
    """Check if page is blocked.
    
    Returns
    -------
    tuple[bool, str]
        (is_blocked, reason)
    """
    try:
        content = page.content().lower()
        
        # Check for captcha
        if "captcha" in content or "smartcaptcha" in content:
            return True, "captcha"
        
        # Check for blocking messages
        if "доступ ограничен" in content or "access denied" in content:
            return True, "access_denied"
        
        # Check if we can find offers
        offers = page.query_selector_all("[data-name='LinkArea']")
        if len(offers) == 0:
            return True, "no_offers"
        
        return False, ""
        
    except Exception as e:
        return True, f"error: {e}"


def scrape_page(page, page_number: int, url: str) -> tuple[int, bool, str]:
    """Scrape a single page.
    
    Returns
    -------
    tuple[int, bool, str]
        (offers_count, is_blocked, block_reason)
    """
    page_url = f"{url}&p={page_number}" if page_number > 1 else url
    
    try:
        response = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
        
        if not response or response.status != 200:
            return 0, True, f"http_{response.status if response else 'unknown'}"
        
        # Check for blocking
        blocked, reason = is_blocked(page)
        if blocked:
            return 0, True, reason
        
        # Count offers
        offers = page.query_selector_all("[data-name='LinkArea']")
        return len(offers), False, ""
        
    except Exception as e:
        LOGGER.error(f"Error scraping page {page_number}: {e}")
        return 0, True, str(e)


def test_mass_scraping(
    target_offers: int = 100000,
    max_pages: int = 2000,
    cookie_refresh_interval: int = 100,
    use_fast_behavior: bool = True,
) -> ScrapingSession:
    """Test mass scraping with proxy.
    
    Parameters
    ----------
    target_offers : int
        Target number of offers to collect
    max_pages : int
        Maximum pages to scrape
    cookie_refresh_interval : int
        Refresh cookies every N pages
    use_fast_behavior : bool
        Use fast behavior simulation (small delays)
        
    Returns
    -------
    ScrapingSession
        Scraping session metrics
    """
    session = ScrapingSession()
    
    # Configure proxy
    proxy_config = ProxyConfig.from_env()
    if not proxy_config:
        LOGGER.error("No proxy configured!")
        session.errors.append("No proxy configured")
        return session
    
    LOGGER.info(f"Using proxy: {proxy_config.server}")
    
    # Configure behavior
    behavior = None
    if use_fast_behavior:
        behavior = HumanBehavior(BehaviorPresets.fast())
    
    url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
    page_number = 1
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            
            # Create context with proxy
            context = create_stealth_context(
                browser,
                proxy=proxy_config.to_playwright_dict(),
            )
            
            page = context.new_page()
            
            LOGGER.info("=" * 80)
            LOGGER.info(f"🚀 Starting mass scraping")
            LOGGER.info(f"Target: {target_offers:,} offers")
            LOGGER.info(f"Max pages: {max_pages}")
            LOGGER.info(f"Cookie refresh: every {cookie_refresh_interval} pages")
            LOGGER.info("=" * 80)
            
            while page_number <= max_pages and session.offers_collected < target_offers:
                page_start = time.time()
                
                # Refresh cookies periodically
                if page_number % cookie_refresh_interval == 0 and page_number > 1:
                    LOGGER.info(f"🔄 Refreshing cookies at page {page_number}")
                    
                    # Save and reload storage state
                    cookies = context.cookies()
                    
                    # Close old context
                    context.close()
                    
                    # Create new context with saved cookies
                    context = browser.new_context(
                        proxy=proxy_config.to_playwright_dict(),
                        storage_state={
                            "cookies": cookies,
                            "origins": []
                        },
                    )
                    
                    # Apply fingerprint
                    from etl.antibot.fingerprint import FingerprintPainter
                    painter = FingerprintPainter()
                    painter.paint_context(context)
                    
                    page = context.new_page()
                    session.cookie_refreshes += 1
                
                # Scrape page
                offers_count, blocked, block_reason = scrape_page(page, page_number, url)
                
                if blocked:
                    if "captcha" in block_reason:
                        session.captchas_encountered += 1
                        LOGGER.warning(f"🤖 Captcha at page {page_number}")
                    else:
                        session.blocks_encountered += 1
                        LOGGER.warning(f"🚫 Blocked at page {page_number}: {block_reason}")
                    
                    # Try to continue (captcha might be temporary)
                    if session.blocks_encountered >= 3:
                        LOGGER.error("Too many consecutive blocks, stopping")
                        break
                    
                    # Wait and retry
                    time.sleep(5)
                    continue
                else:
                    # Reset block counter on success
                    session.blocks_encountered = 0
                
                session.offers_collected += offers_count
                session.pages_scraped += 1
                
                page_duration = time.time() - page_start
                
                # Log progress
                if page_number % 10 == 0 or page_number <= 5:
                    elapsed = session.elapsed_time()
                    offers_per_min = session.offers_per_minute()
                    eta_minutes = (target_offers - session.offers_collected) / offers_per_min if offers_per_min > 0 else 0
                    
                    LOGGER.info(
                        f"✅ Page {page_number}: {offers_count} offers | "
                        f"Total: {session.offers_collected:,}/{target_offers:,} | "
                        f"Speed: {offers_per_min:.0f}/min | "
                        f"ETA: {eta_minutes:.0f}min | "
                        f"Time: {page_duration:.1f}s"
                    )
                else:
                    LOGGER.debug(f"Page {page_number}: {offers_count} offers")
                
                # Small delay
                if behavior:
                    behavior.random_delay(0.2, 0.5)
                else:
                    time.sleep(0.3)
                
                page_number += 1
            
            browser.close()
        
        return session
        
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}", exc_info=True)
        session.errors.append(str(e))
        return session


def main():
    """Run mass scraping test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Mass scraping test")
    parser.add_argument(
        "--offers",
        type=int,
        default=100000,
        help="Target offers (default: 100,000)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=2000,
        help="Max pages (default: 2,000)",
    )
    parser.add_argument(
        "--cookie-refresh",
        type=int,
        default=100,
        help="Cookie refresh interval in pages (default: 100)",
    )
    parser.add_argument(
        "--no-behavior",
        action="store_true",
        help="Disable behavior simulation",
    )
    
    args = parser.parse_args()
    
    # Run test
    session = test_mass_scraping(
        target_offers=args.offers,
        max_pages=args.pages,
        cookie_refresh_interval=args.cookie_refresh,
        use_fast_behavior=not args.no_behavior,
    )
    
    # Print results
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("📊 FINAL RESULTS")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Pages Scraped: {session.pages_scraped}")
    LOGGER.info(f"Offers Collected: {session.offers_collected:,}/{args.offers:,}")
    LOGGER.info(f"Success Rate: {session.pages_scraped - session.blocks_encountered}/{session.pages_scraped} pages")
    LOGGER.info(f"Blocks Encountered: {session.blocks_encountered}")
    LOGGER.info(f"Captchas Encountered: {session.captchas_encountered}")
    LOGGER.info(f"Cookie Refreshes: {session.cookie_refreshes}")
    LOGGER.info(f"Total Time: {session.elapsed_time():.0f}s ({session.elapsed_time()/60:.1f} min)")
    LOGGER.info(f"Avg Speed: {session.offers_per_minute():.0f} offers/min")
    
    # Projected time for 100k
    if session.offers_per_minute() > 0:
        projected_time = 100000 / session.offers_per_minute()
        LOGGER.info(f"Projected time for 100k: {projected_time:.0f} min ({projected_time/60:.1f} hours)")
    
    LOGGER.info("=" * 80)
    
    # Save metrics
    metrics_file = Path(__file__).parent.parent / "logs/mass_scraping_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(session.to_dict(), f, indent=2)
    
    LOGGER.info(f"Metrics saved to: {metrics_file}")


if __name__ == "__main__":
    main()

