#!/usr/bin/env python3
"""Test hybrid proxy strategy for mass scraping.

Strategy:
1. Use proxy for first request (authorization)
2. Save cookies
3. Continue without proxy until blocked
4. Track: pages scraped, offers collected, time to block

Goal: Scrape 100,000 offers efficiently.
"""
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
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
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/hybrid_strategy_test.log"),
    ],
)

LOGGER = logging.getLogger(__name__)


@dataclass
class ScrapeMetrics:
    """Metrics for scraping session."""
    
    pages_scraped: int = 0
    offers_collected: int = 0
    requests_with_proxy: int = 0
    requests_without_proxy: int = 0
    blocked_at_page: int = 0
    total_duration: float = 0.0
    avg_page_duration: float = 0.0
    cookies_saved: bool = False
    block_detected: bool = False
    error_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


def is_blocked(page) -> bool:
    """Check if page is blocked.
    
    Parameters
    ----------
    page : Page
        Playwright page
        
    Returns
    -------
    bool
        True if blocked
    """
    content = page.content().lower()
    
    # Check for blocking indicators
    blocking_keywords = [
        "доступ ограничен",
        "access denied",
        "403 forbidden",
        "404 not found",
        "captcha",
        "проверка браузера",
        "browser check",
    ]
    
    for keyword in blocking_keywords:
        if keyword in content:
            LOGGER.warning(f"Block detected: '{keyword}' found in page")
            return True
    
    # Check if we can find offers
    try:
        offers = page.query_selector_all("[data-name='LinkArea']")
        if len(offers) == 0:
            LOGGER.warning("Block detected: No offers found on page")
            return True
    except:
        return True
    
    return False


def save_cookies_to_file(context, filepath: Path) -> None:
    """Save browser cookies to file.
    
    Parameters
    ----------
    context : BrowserContext
        Playwright context
    filepath : Path
        Path to save cookies
    """
    cookies = context.cookies()
    
    storage_state = {
        "cookies": cookies,
        "origins": []  # Can add localStorage data if needed
    }
    
    filepath.parent.mkdir(exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(storage_state, f, indent=2)
    
    LOGGER.info(f"Saved {len(cookies)} cookies to {filepath}")


def test_hybrid_strategy(
    target_pages: int = 100,
    target_offers: int = 100000,
    use_behavior: bool = False,
) -> ScrapeMetrics:
    """Test hybrid proxy strategy.
    
    Parameters
    ----------
    target_pages : int
        Target number of pages to scrape
    target_offers : int
        Target number of offers to collect
    use_behavior : bool
        Whether to use behavior simulation (slower but stealthier)
        
    Returns
    -------
    ScrapeMetrics
        Scraping metrics
    """
    metrics = ScrapeMetrics()
    start_time = time.time()
    
    # Configure proxy
    proxy_config = ProxyConfig.from_env()
    if not proxy_config:
        LOGGER.error("No proxy configured (set NODEMAVEN_PROXY_URL)")
        metrics.error_message = "No proxy configured"
        return metrics
    
    # Configure behavior (fast preset if enabled)
    behavior = None
    if use_behavior:
        behavior = HumanBehavior(BehaviorPresets.fast())
        LOGGER.info("Behavior simulation enabled (fast preset)")
    
    cookies_file = Path(__file__).parent.parent / "logs/hybrid_cookies.json"
    
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
            
            # ========================================
            # PHASE 1: First request WITH PROXY
            # ========================================
            LOGGER.info("=" * 80)
            LOGGER.info("PHASE 1: First request WITH PROXY (authorization)")
            LOGGER.info("=" * 80)
            
            context_with_proxy = create_stealth_context(
                browser,
                proxy=proxy_config.to_playwright_dict(),
            )
            
            page = context_with_proxy.new_page()
            
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
            LOGGER.info(f"Navigating to: {url}")
            
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            LOGGER.info(f"Page loaded: {response.status if response else 'unknown'}")
            
            metrics.requests_with_proxy += 1
            
            # Check if blocked
            if is_blocked(page):
                metrics.block_detected = True
                metrics.blocked_at_page = 1
                metrics.error_message = "Blocked on first request with proxy"
                return metrics
            
            # Count offers
            offers = page.query_selector_all("[data-name='LinkArea']")
            metrics.offers_collected += len(offers)
            metrics.pages_scraped += 1
            
            LOGGER.info(f"✅ Page 1: {len(offers)} offers (WITH PROXY)")
            
            # Simulate behavior if enabled
            if behavior:
                behavior.random_delay(0.5, 1.0)
            
            # Save cookies
            save_cookies_to_file(context_with_proxy, cookies_file)
            metrics.cookies_saved = True
            
            # Close context with proxy
            context_with_proxy.close()
            
            # ========================================
            # PHASE 2: Continue WITHOUT PROXY
            # ========================================
            LOGGER.info("=" * 80)
            LOGGER.info("PHASE 2: Continue WITHOUT PROXY (using cookies)")
            LOGGER.info("=" * 80)
            
            # Create new context WITHOUT proxy but WITH cookies
            context_without_proxy = browser.new_context(
                storage_state=str(cookies_file),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            
            # Apply fingerprint painting
            from etl.antibot.fingerprint import FingerprintPainter
            painter = FingerprintPainter()
            painter.paint_context(context_without_proxy)
            
            page = context_without_proxy.new_page()
            
            # Continue scraping pages
            page_number = 2
            
            while page_number <= target_pages and metrics.offers_collected < target_offers:
                page_start = time.time()
                
                # Build URL with pagination
                page_url = f"{url}&p={page_number}"
                
                try:
                    LOGGER.info(f"Scraping page {page_number} WITHOUT PROXY...")
                    
                    response = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    
                    metrics.requests_without_proxy += 1
                    
                    # Check if blocked
                    if is_blocked(page):
                        metrics.block_detected = True
                        metrics.blocked_at_page = page_number
                        LOGGER.warning(f"🚫 BLOCKED at page {page_number}")
                        break
                    
                    # Count offers
                    offers = page.query_selector_all("[data-name='LinkArea']")
                    offers_count = len(offers)
                    
                    if offers_count == 0:
                        LOGGER.warning(f"No offers found on page {page_number}, stopping")
                        metrics.block_detected = True
                        metrics.blocked_at_page = page_number
                        break
                    
                    metrics.offers_collected += offers_count
                    metrics.pages_scraped += 1
                    
                    page_duration = time.time() - page_start
                    
                    LOGGER.info(
                        f"✅ Page {page_number}: {offers_count} offers "
                        f"(total: {metrics.offers_collected}, "
                        f"time: {page_duration:.2f}s)"
                    )
                    
                    # Simulate behavior if enabled
                    if behavior:
                        behavior.random_delay(0.3, 0.8)
                    else:
                        time.sleep(0.5)  # Small delay
                    
                    page_number += 1
                    
                except Exception as e:
                    LOGGER.error(f"Error on page {page_number}: {e}")
                    metrics.block_detected = True
                    metrics.blocked_at_page = page_number
                    metrics.error_message = str(e)
                    break
            
            browser.close()
        
        metrics.total_duration = time.time() - start_time
        metrics.avg_page_duration = (
            metrics.total_duration / metrics.pages_scraped
            if metrics.pages_scraped > 0
            else 0
        )
        
        return metrics
        
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}", exc_info=True)
        metrics.error_message = str(e)
        metrics.total_duration = time.time() - start_time
        return metrics


def main():
    """Run hybrid strategy test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test hybrid proxy strategy")
    parser.add_argument(
        "--pages",
        type=int,
        default=100,
        help="Target number of pages (default: 100)",
    )
    parser.add_argument(
        "--offers",
        type=int,
        default=100000,
        help="Target number of offers (default: 100,000)",
    )
    parser.add_argument(
        "--behavior",
        action="store_true",
        help="Enable behavior simulation (slower but stealthier)",
    )
    
    args = parser.parse_args()
    
    LOGGER.info("=" * 80)
    LOGGER.info("🚀 HYBRID PROXY STRATEGY TEST")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Target Pages: {args.pages}")
    LOGGER.info(f"Target Offers: {args.offers}")
    LOGGER.info(f"Behavior Simulation: {'Enabled' if args.behavior else 'Disabled'}")
    LOGGER.info("=" * 80)
    
    # Run test
    metrics = test_hybrid_strategy(
        target_pages=args.pages,
        target_offers=args.offers,
        use_behavior=args.behavior,
    )
    
    # Print results
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("📊 FINAL RESULTS")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Pages Scraped: {metrics.pages_scraped}/{args.pages}")
    LOGGER.info(f"Offers Collected: {metrics.offers_collected:,}/{args.offers:,}")
    LOGGER.info(f"Requests with Proxy: {metrics.requests_with_proxy}")
    LOGGER.info(f"Requests without Proxy: {metrics.requests_without_proxy}")
    LOGGER.info(f"Total Duration: {metrics.total_duration:.2f}s ({metrics.total_duration/60:.1f} min)")
    LOGGER.info(f"Avg Page Duration: {metrics.avg_page_duration:.2f}s")
    
    if metrics.block_detected:
        LOGGER.warning(f"🚫 Blocked at page: {metrics.blocked_at_page}")
        LOGGER.warning(f"Cookies lasted for: {metrics.blocked_at_page - 1} pages")
    else:
        LOGGER.info("✅ No blocking detected!")
    
    # Calculate efficiency
    if metrics.total_duration > 0:
        offers_per_second = metrics.offers_collected / metrics.total_duration
        offers_per_minute = offers_per_second * 60
        estimated_time_100k = 100000 / offers_per_second / 60  # minutes
        
        LOGGER.info("=" * 80)
        LOGGER.info("📈 EFFICIENCY METRICS")
        LOGGER.info("=" * 80)
        LOGGER.info(f"Offers per second: {offers_per_second:.2f}")
        LOGGER.info(f"Offers per minute: {offers_per_minute:.2f}")
        LOGGER.info(f"Estimated time for 100k offers: {estimated_time_100k:.1f} minutes")
        
        # Proxy cost analysis
        proxy_requests_percent = (
            metrics.requests_with_proxy / 
            (metrics.requests_with_proxy + metrics.requests_without_proxy) * 100
            if metrics.requests_without_proxy > 0 else 100
        )
        
        LOGGER.info("=" * 80)
        LOGGER.info("💰 COST ANALYSIS")
        LOGGER.info("=" * 80)
        LOGGER.info(f"Proxy usage: {proxy_requests_percent:.1f}% of requests")
        LOGGER.info(f"Cost savings vs full proxy: ~{100 - proxy_requests_percent:.1f}%")
    
    LOGGER.info("=" * 80)
    
    # Save metrics
    metrics_file = Path(__file__).parent.parent / "logs/hybrid_strategy_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(metrics.to_dict(), f, indent=2)
    
    LOGGER.info(f"Metrics saved to: {metrics_file}")
    
    return metrics


if __name__ == "__main__":
    main()

