#!/usr/bin/env python3
"""Test captcha-solving strategy for cost-effective mass scraping.

Strategy:
1. Use proxy for first page only
2. Solve captcha if appears
3. Save cookies after each page
4. Continue without proxy using cookies
5. If blocked → solve captcha → update cookies → continue
6. Track: session lifetime, captcha frequency, cost

Goal: Maximize pages per proxy connection.
"""
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright, Page, BrowserContext

from etl.antibot import (
    HumanBehavior,
    BehaviorPresets,
    ProxyConfig,
    CaptchaSolver,
    create_stealth_context,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/captcha_strategy.log"),
    ],
)

LOGGER = logging.getLogger(__name__)


@dataclass
class SessionMetrics:
    """Metrics for scraping session."""
    
    start_time: float = field(default_factory=time.time)
    pages_scraped: int = 0
    offers_collected: int = 0
    captchas_solved: int = 0
    captcha_cost_usd: float = 0.0
    proxy_used_pages: int = 0
    no_proxy_pages: int = 0
    cookie_refreshes: int = 0
    blocks_encountered: int = 0
    errors: List[str] = field(default_factory=list)
    
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    def offers_per_minute(self) -> float:
        elapsed_min = self.elapsed_time() / 60
        return self.offers_collected / elapsed_min if elapsed_min > 0 else 0
    
    def avg_cost_per_page(self) -> float:
        return self.captcha_cost_usd / self.pages_scraped if self.pages_scraped > 0 else 0
    
    def to_dict(self):
        return {
            **asdict(self),
            "elapsed_time": self.elapsed_time(),
            "offers_per_minute": self.offers_per_minute(),
            "avg_cost_per_page": self.avg_cost_per_page(),
        }


def load_proxy_pool() -> List[ProxyConfig]:
    """Load proxy pool from config/proxy_pool.txt file."""
    proxies = []
    proxy_file = Path(__file__).parent.parent / "config/proxy_pool.txt"
    
    if not proxy_file.exists():
        LOGGER.warning(f"No proxy pool file found: {proxy_file}")
        return proxies
    
    with open(proxy_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            
            # Parse: http://username:password@host:port
            try:
                proxies.append(ProxyConfig.from_url(line))
            except Exception as e:
                LOGGER.warning(f"Failed to parse proxy: {line} - {e}")
    
    LOGGER.info(f"Loaded {len(proxies)} proxies from pool")
    return proxies


def detect_and_solve_captcha(
    page: Page,
    solver: Optional[CaptchaSolver],
    page_url: str,
) -> tuple[bool, float]:
    """Detect and solve captcha if present.
    
    Returns
    -------
    tuple[bool, float]
        (captcha_solved, cost_usd)
    """
    if not solver:
        return False, 0.0
    
    try:
        # Check for captcha
        site_key = page.eval_on_selector(
            "[data-sitekey]",
            "el => el.getAttribute('data-sitekey')",
            timeout=2000,
        )
        
        if site_key:
            LOGGER.warning(f"🤖 Captcha detected! Site key: {site_key}")
            
            # Solve captcha
            start_solve = time.time()
            token, telemetry = solver.solve(site_key, page_url)
            solve_time = time.time() - start_solve
            
            LOGGER.info(
                f"✅ Captcha solved in {solve_time:.2f}s "
                f"(cost: ${telemetry.cost_estimate_usd:.4f})"
            )
            
            # Inject token
            page.evaluate(
                """
                token => {
                    document.cookie = `smartCaptchaToken=${token};path=/;max-age=600`;
                    const input = document.querySelector('input[name="smart-token"], input[name="smartCaptchaToken"]');
                    if (input) input.value = token;
                    window.dispatchEvent(new CustomEvent('smartCaptchaToken', {detail: token}));
                }
                """,
                token,
            )
            
            # Wait and reload
            time.sleep(2)
            page.reload(wait_until="domcontentloaded", timeout=30000)
            
            return True, telemetry.cost_estimate_usd
            
    except Exception as e:
        LOGGER.debug(f"No captcha detected or solve failed: {e}")
    
    return False, 0.0


def save_cookies(context: BrowserContext, filepath: Path) -> None:
    """Save browser cookies to file."""
    cookies = context.cookies()
    
    storage_state = {
        "cookies": cookies,
        "origins": []
    }
    
    filepath.parent.mkdir(exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(storage_state, f, indent=2)
    
    LOGGER.debug(f"Saved {len(cookies)} cookies")


def test_captcha_strategy(
    target_pages: int = 10,
    use_proxy_for_first: bool = True,
) -> SessionMetrics:
    """Test captcha-solving strategy.
    
    Parameters
    ----------
    target_pages : int
        Number of pages to scrape
    use_proxy_for_first : bool
        Use proxy for first page only
        
    Returns
    -------
    SessionMetrics
        Session metrics
    """
    metrics = SessionMetrics()
    
    # Load proxy pool
    proxy_pool = load_proxy_pool()
    if not proxy_pool:
        LOGGER.error("No proxies available!")
        return metrics
    
    LOGGER.info(f"Proxy pool: {len(proxy_pool)} proxies available")
    
    # Configure captcha solver
    captcha_solver = None
    if os.getenv("ANTICAPTCHA_KEY"):
        captcha_solver = CaptchaSolver()
        LOGGER.info("✅ Captcha solver enabled")
    else:
        LOGGER.warning("⚠️ No captcha solver (set ANTICAPTCHA_KEY)")
    
    # Configure behavior (fast)
    behavior = HumanBehavior(BehaviorPresets.fast())
    
    cookies_file = Path(__file__).parent.parent / "logs/session_cookies.json"
    base_url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
    
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
            
            # Use first proxy from pool
            current_proxy = proxy_pool[0]
            LOGGER.info(f"Using proxy: {current_proxy.server}")
            
            context = None
            page = None
            
            for page_number in range(1, target_pages + 1):
                page_start = time.time()
                
                # Determine if we should use proxy
                use_proxy = (page_number == 1 and use_proxy_for_first)
                
                # Create/recreate context if needed
                if context is None or page_number == 1:
                    if context:
                        context.close()
                    
                    context_kwargs = {}
                    
                    if use_proxy:
                        context_kwargs["proxy"] = current_proxy.to_playwright_dict()
                        LOGGER.info(f"📡 Page {page_number}: WITH PROXY")
                        metrics.proxy_used_pages += 1
                    else:
                        LOGGER.info(f"🔓 Page {page_number}: WITHOUT PROXY (using cookies)")
                        metrics.no_proxy_pages += 1
                        
                        # Load saved cookies if available
                        if cookies_file.exists():
                            context_kwargs["storage_state"] = str(cookies_file)
                    
                    context = create_stealth_context(browser, **context_kwargs)
                    page = context.new_page()
                
                # Build URL
                page_url = f"{base_url}&p={page_number}" if page_number > 1 else base_url
                
                try:
                    LOGGER.info(f"Scraping page {page_number}...")
                    
                    # Navigate
                    response = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    
                    if not response or response.status != 200:
                        LOGGER.error(f"Bad response: {response.status if response else 'None'}")
                        metrics.blocks_encountered += 1
                        continue
                    
                    # Check for captcha and solve
                    captcha_solved, captcha_cost = detect_and_solve_captcha(
                        page,
                        captcha_solver,
                        page_url,
                    )
                    
                    if captcha_solved:
                        metrics.captchas_solved += 1
                        metrics.captcha_cost_usd += captcha_cost
                    
                    # Small behavior simulation
                    behavior.random_delay(0.3, 0.8)
                    
                    # Count offers
                    offers = page.query_selector_all("[data-name='LinkArea']")
                    offers_count = len(offers)
                    
                    if offers_count == 0:
                        LOGGER.warning(f"⚠️ No offers found on page {page_number}")
                        
                        # Take screenshot for debugging
                        screenshot_path = Path(__file__).parent.parent / f"logs/no_offers_page_{page_number}.png"
                        page.screenshot(path=str(screenshot_path))
                        
                        # Check if we need to solve captcha again
                        if "captcha" in page.content().lower() or "smartcaptcha" in page.content().lower():
                            LOGGER.warning("Captcha detected in content, attempting solve...")
                            captcha_solved, captcha_cost = detect_and_solve_captcha(
                                page,
                                captcha_solver,
                                page_url,
                            )
                            if captcha_solved:
                                metrics.captchas_solved += 1
                                metrics.captcha_cost_usd += captcha_cost
                                
                                # Try again
                                offers = page.query_selector_all("[data-name='LinkArea']")
                                offers_count = len(offers)
                        
                        if offers_count == 0:
                            metrics.blocks_encountered += 1
                            continue
                    
                    metrics.offers_collected += offers_count
                    metrics.pages_scraped += 1
                    
                    # Save cookies after successful page
                    save_cookies(context, cookies_file)
                    metrics.cookie_refreshes += 1
                    
                    page_duration = time.time() - page_start
                    
                    LOGGER.info(
                        f"✅ Page {page_number}: {offers_count} offers | "
                        f"Total: {metrics.offers_collected} | "
                        f"Captchas: {metrics.captchas_solved} | "
                        f"Cost: ${metrics.captcha_cost_usd:.4f} | "
                        f"Time: {page_duration:.1f}s"
                    )
                    
                    # Small delay before next page
                    behavior.random_delay(0.5, 1.0)
                    
                except Exception as e:
                    LOGGER.error(f"Error on page {page_number}: {e}")
                    metrics.errors.append(f"Page {page_number}: {e}")
                    
                    # Take screenshot
                    try:
                        screenshot_path = Path(__file__).parent.parent / f"logs/error_page_{page_number}.png"
                        page.screenshot(path=str(screenshot_path))
                    except:
                        pass
                    
                    continue
            
            if browser:
                browser.close()
        
        return metrics
        
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}", exc_info=True)
        metrics.errors.append(f"Fatal: {e}")
        return metrics


def main():
    """Run captcha strategy test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test captcha-solving strategy")
    parser.add_argument(
        "--pages",
        type=int,
        default=10,
        help="Number of pages to scrape (default: 10)",
    )
    parser.add_argument(
        "--proxy-first-only",
        action="store_true",
        help="Use proxy only for first page",
    )
    
    args = parser.parse_args()
    
    LOGGER.info("=" * 80)
    LOGGER.info("🚀 CAPTCHA-SOLVING STRATEGY TEST")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Target Pages: {args.pages}")
    LOGGER.info(f"Proxy Strategy: {'First page only' if args.proxy_first_only else 'All pages'}")
    LOGGER.info("=" * 80)
    
    # Run test
    metrics = test_captcha_strategy(
        target_pages=args.pages,
        use_proxy_for_first=args.proxy_first_only,
    )
    
    # Print results
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("📊 FINAL RESULTS")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Pages Scraped: {metrics.pages_scraped}/{args.pages}")
    LOGGER.info(f"Offers Collected: {metrics.offers_collected:,}")
    LOGGER.info(f"Captchas Solved: {metrics.captchas_solved}")
    LOGGER.info(f"Captcha Cost: ${metrics.captcha_cost_usd:.4f}")
    LOGGER.info(f"Proxy Used: {metrics.proxy_used_pages} pages")
    LOGGER.info(f"No Proxy: {metrics.no_proxy_pages} pages")
    LOGGER.info(f"Cookie Refreshes: {metrics.cookie_refreshes}")
    LOGGER.info(f"Blocks: {metrics.blocks_encountered}")
    LOGGER.info(f"Total Time: {metrics.elapsed_time():.0f}s ({metrics.elapsed_time()/60:.1f} min)")
    LOGGER.info(f"Speed: {metrics.offers_per_minute():.0f} offers/min")
    LOGGER.info(f"Avg Cost/Page: ${metrics.avg_cost_per_page():.4f}")
    
    # Calculate projections for 100k offers
    if metrics.offers_collected > 0:
        LOGGER.info("=" * 80)
        LOGGER.info("📈 PROJECTIONS FOR 100,000 OFFERS")
        LOGGER.info("=" * 80)
        
        pages_needed = 100000 / (metrics.offers_collected / metrics.pages_scraped)
        time_needed = pages_needed * (metrics.elapsed_time() / metrics.pages_scraped) / 60
        captcha_cost = pages_needed * metrics.avg_cost_per_page()
        
        LOGGER.info(f"Estimated Pages: {pages_needed:.0f}")
        LOGGER.info(f"Estimated Time: {time_needed:.0f} minutes ({time_needed/60:.1f} hours)")
        LOGGER.info(f"Estimated Captcha Cost: ${captcha_cost:.2f}")
        
        # Compare with proxy cost
        proxy_traffic_gb = pages_needed * 4.6 / 1024  # 4.6 MB per page
        proxy_cost = proxy_traffic_gb * 20  # $20/GB
        
        LOGGER.info(f"Proxy Cost (if used): ${proxy_cost:.2f}")
        LOGGER.info(f"Savings: ${proxy_cost - captcha_cost:.2f} ({(1 - captcha_cost/proxy_cost)*100:.1f}%)")
    
    LOGGER.info("=" * 80)
    
    # Save metrics
    metrics_file = Path(__file__).parent.parent / "logs/captcha_strategy_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(metrics.to_dict(), f, indent=2)
    
    LOGGER.info(f"Metrics saved to: {metrics_file}")


if __name__ == "__main__":
    main()

