#!/usr/bin/env python3
"""Test CIAN scraping with human behavior simulation.

This script demonstrates the complete anti-bot bypass strategy:
- Residential proxy (NodeMaven)
- Fingerprint painting
- Human behavior simulation
- Yandex SmartCaptcha bypass
"""
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

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
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

LOGGER = logging.getLogger(__name__)


def test_with_behavior_simulation(behavior_preset: str = "normal"):
    """Test CIAN scraping with full behavior simulation.
    
    Parameters
    ----------
    behavior_preset : str
        Behavior preset: "fast", "normal", "cautious", "paranoid"
    """
    LOGGER.info("=" * 80)
    LOGGER.info(f"Testing with '{behavior_preset}' behavior preset")
    LOGGER.info("=" * 80)
    
    # Configure behavior
    if behavior_preset == "fast":
        behavior_config = BehaviorPresets.fast()
    elif behavior_preset == "cautious":
        behavior_config = BehaviorPresets.cautious()
    elif behavior_preset == "paranoid":
        behavior_config = BehaviorPresets.paranoid()
    else:
        behavior_config = BehaviorPresets.normal()
    
    behavior = HumanBehavior(behavior_config)
    
    # Configure proxy
    proxy_config = ProxyConfig.from_env()
    if proxy_config:
        LOGGER.info(f"Using proxy: {proxy_config.server}")
    else:
        LOGGER.warning("No proxy configured (set NODEMAVEN_PROXY_URL)")
    
    # Configure captcha solver
    captcha_solver = None
    if os.getenv("ANTICAPTCHA_KEY"):
        captcha_solver = CaptchaSolver()
        LOGGER.info("Captcha solver enabled")
    
    start_time = time.time()
    offers_found = 0
    
    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            
            # Create context with proxy
            context_kwargs = {}
            if proxy_config:
                context_kwargs["proxy"] = proxy_config.to_playwright_dict()
            
            context = create_stealth_context(
                browser,
                prefer_mobile=False,
                **context_kwargs,
            )
            
            page = context.new_page()
            
            # Navigate to CIAN
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
            LOGGER.info(f"Navigating to: {url}")
            
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            LOGGER.info(f"Page loaded: {response.status if response else 'unknown'}")
            
            # Check for captcha
            if captcha_solver:
                try:
                    site_key = page.eval_on_selector(
                        "[data-sitekey]",
                        "el => el.getAttribute('data-sitekey')",
                    )
                    
                    if site_key:
                        LOGGER.warning(f"Captcha detected! Site key: {site_key}")
                        
                        # Solve captcha
                        proxy_url = proxy_config.to_httpx_url() if proxy_config else None
                        token, telemetry = captcha_solver.solve(
                            site_key,
                            url,
                            proxy=proxy_url,
                        )
                        
                        LOGGER.info(
                            f"Captcha solved in {telemetry.solve_time_sec:.2f}s "
                            f"(cost: ${telemetry.cost_estimate_usd:.4f})"
                        )
                        
                        # Inject token
                        page.evaluate(
                            """
                            token => {
                                document.cookie = `smartCaptchaToken=${token};path=/;max-age=600`;
                                const input = document.querySelector('input[name="smart-token"]');
                                if (input) input.value = token;
                                window.dispatchEvent(new CustomEvent('smartCaptchaToken', {detail: token}));
                            }
                            """,
                            token,
                        )
                        
                        # Reload page
                        behavior.random_delay(1.0, 2.0)
                        page.reload(wait_until="domcontentloaded")
                        
                except Exception as e:
                    LOGGER.info(f"No captcha detected: {e}")
            
            # Simulate human behavior
            LOGGER.info("Starting human behavior simulation...")
            behavior.page_interaction_sequence(
                page,
                scroll=True,
                mouse_movements=behavior_config.mouse_movements_per_action,
                reading_pause=True,
            )
            
            # Take screenshot
            screenshot_path = Path(__file__).parent.parent / f"logs/cian_with_behavior_{behavior_preset}.png"
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            LOGGER.info(f"Screenshot saved: {screenshot_path}")
            
            # Count offers
            offers = page.query_selector_all("[data-name='LinkArea']")
            offers_found = len(offers)
            LOGGER.info(f"Found {offers_found} offers")
            
            # Simulate viewing first few offers
            for i, offer in enumerate(offers[:3]):
                LOGGER.info(f"Simulating hover on offer {i + 1}")
                behavior.hover_element(page, f"[data-name='LinkArea']:nth-child({i + 1})")
                behavior.random_delay(0.5, 1.0)
            
            # Scroll to bottom
            LOGGER.info("Scrolling to see more offers...")
            behavior.scroll_page(page, "down", distance=1000)
            behavior.random_delay(1.0, 2.0)
            
            # Count offers again
            offers = page.query_selector_all("[data-name='LinkArea']")
            offers_found = len(offers)
            LOGGER.info(f"Total offers visible: {offers_found}")
            
            browser.close()
        
        duration = time.time() - start_time
        
        # Results
        LOGGER.info("=" * 80)
        LOGGER.info("✅ TEST COMPLETED SUCCESSFULLY")
        LOGGER.info("=" * 80)
        LOGGER.info(f"Behavior Preset: {behavior_preset}")
        LOGGER.info(f"Duration: {duration:.2f}s")
        LOGGER.info(f"Offers Found: {offers_found}")
        LOGGER.info(f"Proxy Used: {proxy_config.server if proxy_config else 'None'}")
        LOGGER.info("=" * 80)
        
        return {
            "success": True,
            "offers_found": offers_found,
            "duration": duration,
            "behavior_preset": behavior_preset,
        }
        
    except Exception as e:
        duration = time.time() - start_time
        LOGGER.error(f"Test failed after {duration:.2f}s: {e}", exc_info=True)
        
        return {
            "success": False,
            "error": str(e),
            "duration": duration,
            "behavior_preset": behavior_preset,
        }


def main():
    """Run tests with different behavior presets."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test CIAN with behavior simulation")
    parser.add_argument(
        "--preset",
        choices=["fast", "normal", "cautious", "paranoid"],
        default="normal",
        help="Behavior preset to use",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test all presets",
    )
    
    args = parser.parse_args()
    
    if args.all:
        presets = ["fast", "normal", "cautious"]
        results = []
        
        for preset in presets:
            result = test_with_behavior_simulation(preset)
            results.append(result)
            
            # Wait between tests
            if preset != presets[-1]:
                LOGGER.info("Waiting 30s before next test...")
                time.sleep(30)
        
        # Summary
        LOGGER.info("\n" + "=" * 80)
        LOGGER.info("📊 SUMMARY OF ALL TESTS")
        LOGGER.info("=" * 80)
        
        for result in results:
            status = "✅" if result["success"] else "❌"
            preset = result["behavior_preset"]
            offers = result.get("offers_found", 0)
            duration = result["duration"]
            
            LOGGER.info(
                f"{status} {preset:10s}: {offers:3d} offers in {duration:6.2f}s"
            )
        
        LOGGER.info("=" * 80)
        
    else:
        test_with_behavior_simulation(args.preset)


if __name__ == "__main__":
    main()

