#!/usr/bin/env python3
"""Test script for CIAN anti-bot bypass strategies.

This script tests different approaches to bypass CIAN's anti-bot protection:
1. Direct HTTP request
2. HTTP with residential proxy
3. Playwright with fingerprint painting
4. Playwright with storage state
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from playwright.sync_api import sync_playwright

from etl.antibot import (
    CaptchaSolver,
    ProxyConfig,
    create_stealth_context,
    UserAgentPool,
)
from etl.collector_cian.fetcher import CIAN_URL, load_payload

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("antibot_test.log"),
    ],
)

LOGGER = logging.getLogger(__name__)


class TestResult:
    """Test result container."""
    
    def __init__(self, name: str):
        self.name = name
        self.success = False
        self.status_code = None
        self.response_size = 0
        self.error = None
        self.duration = 0.0
        self.blocked = False
        self.captcha_detected = False
        self.response_headers = {}
        self.response_preview = ""
    
    def log(self):
        """Log test result."""
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        LOGGER.info("=" * 80)
        LOGGER.info(f"{status}: {self.name}")
        LOGGER.info(f"Duration: {self.duration:.2f}s")
        
        if self.status_code:
            LOGGER.info(f"Status Code: {self.status_code}")
        
        if self.response_size:
            LOGGER.info(f"Response Size: {self.response_size} bytes")
        
        if self.blocked:
            LOGGER.warning("🚫 BLOCKED by anti-bot")
        
        if self.captcha_detected:
            LOGGER.warning("🤖 CAPTCHA detected")
        
        if self.error:
            LOGGER.error(f"Error: {self.error}")
        
        if self.response_headers:
            LOGGER.debug("Response Headers:")
            for key, value in self.response_headers.items():
                LOGGER.debug(f"  {key}: {value}")
        
        if self.response_preview:
            LOGGER.debug(f"Response Preview (first 500 chars):\n{self.response_preview[:500]}")
        
        LOGGER.info("=" * 80)


def test_http_direct() -> TestResult:
    """Test 1: Direct HTTP request without proxy."""
    result = TestResult("HTTP Direct (no proxy)")
    start_time = time.time()
    
    try:
        # Load test payload
        payload_path = Path(__file__).parent.parent / "etl/collector_cian/payloads/base.yaml"
        payload = load_payload(payload_path)
        
        # Build request
        request_payload = {**payload, "page": 1}
        
        # User agent
        ua_pool = UserAgentPool()
        headers = {
            "User-Agent": ua_pool.get_random(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "https://www.cian.ru/",
            "Origin": "https://www.cian.ru",
        }
        
        LOGGER.info("Testing HTTP direct request...")
        LOGGER.debug(f"Headers: {headers}")
        
        response = httpx.post(
            CIAN_URL,
            json=request_payload,
            headers=headers,
            timeout=30.0,
        )
        
        result.status_code = response.status_code
        result.response_size = len(response.content)
        result.response_headers = dict(response.headers)
        result.response_preview = response.text
        
        # Check for blocking
        if response.status_code in (403, 404, 429):
            result.blocked = True
            result.error = f"Blocked with status {response.status_code}"
        elif response.status_code == 200:
            # Check if response contains data
            try:
                data = response.json()
                if "data" in data and "offersSerialized" in data["data"]:
                    result.success = True
                    LOGGER.info(f"Found {len(data['data']['offersSerialized'])} offers")
                else:
                    result.error = "Response missing expected data structure"
            except Exception as e:
                result.error = f"Failed to parse JSON: {e}"
        else:
            result.error = f"Unexpected status code: {response.status_code}"
        
    except Exception as e:
        result.error = str(e)
        LOGGER.exception("HTTP direct test failed")
    
    result.duration = time.time() - start_time
    result.log()
    return result


def test_http_with_proxy() -> TestResult:
    """Test 2: HTTP request with residential proxy."""
    result = TestResult("HTTP with Residential Proxy (NodeMaven)")
    start_time = time.time()
    
    try:
        # Load proxy config
        proxy_config = ProxyConfig.from_env()
        if not proxy_config:
            result.error = "No proxy configured (set NODEMAVEN_PROXY_URL)"
            result.log()
            return result
        
        LOGGER.info(f"Using proxy: {proxy_config.server}")
        
        # Load test payload
        payload_path = Path(__file__).parent.parent / "etl/collector_cian/payloads/base.yaml"
        payload = load_payload(payload_path)
        request_payload = {**payload, "page": 1}
        
        # User agent
        ua_pool = UserAgentPool()
        headers = {
            "User-Agent": ua_pool.get_random(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "https://www.cian.ru/",
            "Origin": "https://www.cian.ru",
        }
        
        # Configure httpx client with proxy
        LOGGER.info("Testing HTTP with proxy...")
        LOGGER.debug(f"Proxy: {proxy_config.server}")
        
        with httpx.Client(
            proxies=proxy_config.to_httpx_url(),
            timeout=30.0,
        ) as client:
            response = client.post(
                CIAN_URL,
                json=request_payload,
                headers=headers,
            )
        
        result.status_code = response.status_code
        result.response_size = len(response.content)
        result.response_headers = dict(response.headers)
        result.response_preview = response.text
        
        # Check for blocking
        if response.status_code in (403, 404, 429):
            result.blocked = True
            result.error = f"Blocked with status {response.status_code}"
        elif response.status_code == 200:
            try:
                data = response.json()
                if "data" in data and "offersSerialized" in data["data"]:
                    result.success = True
                    LOGGER.info(f"Found {len(data['data']['offersSerialized'])} offers")
                else:
                    result.error = "Response missing expected data structure"
            except Exception as e:
                result.error = f"Failed to parse JSON: {e}"
        else:
            result.error = f"Unexpected status code: {response.status_code}"
        
    except Exception as e:
        result.error = str(e)
        LOGGER.exception("HTTP with proxy test failed")
    
    result.duration = time.time() - start_time
    result.log()
    return result


def test_playwright_stealth() -> TestResult:
    """Test 3: Playwright with fingerprint painting."""
    result = TestResult("Playwright with Stealth Fingerprint")
    start_time = time.time()
    
    try:
        LOGGER.info("Testing Playwright with fingerprint painting...")
        
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu",
                ],
            )
            
            # Create stealth context with fingerprint
            context = create_stealth_context(browser, prefer_mobile=False)
            
            # Add proxy if available
            proxy_config = ProxyConfig.from_env()
            if proxy_config:
                LOGGER.info(f"Using proxy: {proxy_config.server}")
                context = browser.new_context(
                    proxy=proxy_config.to_playwright_dict(),
                )
            
            page = context.new_page()
            
            # Navigate to CIAN search
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
            LOGGER.info(f"Navigating to: {url}")
            
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            result.status_code = response.status if response else None
            
            # Take screenshot
            screenshot_path = Path(__file__).parent.parent / "logs/playwright_test.png"
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            LOGGER.info(f"Screenshot saved: {screenshot_path}")
            
            # Check for captcha
            captcha_selectors = [
                "[data-sitekey]",
                ".captcha",
                "#captcha",
                "iframe[src*='captcha']",
                "iframe[src*='smartcaptcha']",
            ]
            
            for selector in captcha_selectors:
                try:
                    if page.query_selector(selector):
                        result.captcha_detected = True
                        LOGGER.warning(f"Captcha detected: {selector}")
                        break
                except:
                    pass
            
            # Check for blocking indicators
            page_content = page.content()
            result.response_size = len(page_content)
            result.response_preview = page_content
            
            blocking_keywords = [
                "доступ ограничен",
                "access denied",
                "blocked",
                "captcha",
                "проверка браузера",
            ]
            
            for keyword in blocking_keywords:
                if keyword.lower() in page_content.lower():
                    result.blocked = True
                    result.error = f"Blocking detected: '{keyword}' found in page"
                    break
            
            # Check if we can find offers
            try:
                offers = page.query_selector_all("[data-name='LinkArea']")
                if len(offers) > 0:
                    result.success = True
                    LOGGER.info(f"Found {len(offers)} offer elements on page")
                else:
                    if not result.blocked and not result.captcha_detected:
                        result.error = "No offers found on page"
            except Exception as e:
                result.error = f"Failed to find offers: {e}"
            
            browser.close()
        
    except Exception as e:
        result.error = str(e)
        LOGGER.exception("Playwright stealth test failed")
    
    result.duration = time.time() - start_time
    result.log()
    return result


def test_playwright_with_storage_state() -> TestResult:
    """Test 4: Playwright with storage state (cookies)."""
    result = TestResult("Playwright with Storage State")
    start_time = time.time()
    
    try:
        # Check for storage state
        storage_state_path = os.getenv("CIAN_STORAGE_STATE")
        if not storage_state_path:
            result.error = "No storage state configured (set CIAN_STORAGE_STATE)"
            result.log()
            return result
        
        storage_path = Path(storage_state_path)
        if not storage_path.exists():
            result.error = f"Storage state file not found: {storage_path}"
            result.log()
            return result
        
        LOGGER.info(f"Using storage state: {storage_path}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            
            # Load storage state
            context = browser.new_context(storage_state=str(storage_path))
            
            # Apply fingerprint
            from etl.antibot.fingerprint import FingerprintPainter
            painter = FingerprintPainter()
            fingerprint = painter.get_random_fingerprint()
            painter.paint_context(context, fingerprint)
            
            page = context.new_page()
            
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
            LOGGER.info(f"Navigating to: {url}")
            
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            result.status_code = response.status if response else None
            
            # Screenshot
            screenshot_path = Path(__file__).parent.parent / "logs/playwright_storage_state.png"
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            LOGGER.info(f"Screenshot saved: {screenshot_path}")
            
            # Check for success
            page_content = page.content()
            result.response_size = len(page_content)
            
            offers = page.query_selector_all("[data-name='LinkArea']")
            if len(offers) > 0:
                result.success = True
                LOGGER.info(f"Found {len(offers)} offers with storage state")
            else:
                result.error = "No offers found"
            
            browser.close()
        
    except Exception as e:
        result.error = str(e)
        LOGGER.exception("Playwright with storage state test failed")
    
    result.duration = time.time() - start_time
    result.log()
    return result


def main():
    """Run all tests."""
    LOGGER.info("🚀 Starting CIAN Anti-bot Bypass Tests")
    LOGGER.info("=" * 80)
    
    results = []
    
    # Test 1: Direct HTTP
    results.append(test_http_direct())
    time.sleep(2)
    
    # Test 2: HTTP with proxy
    results.append(test_http_with_proxy())
    time.sleep(2)
    
    # Test 3: Playwright stealth
    results.append(test_playwright_stealth())
    time.sleep(2)
    
    # Test 4: Playwright with storage state
    results.append(test_playwright_with_storage_state())
    
    # Summary
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("📊 TEST SUMMARY")
    LOGGER.info("=" * 80)
    
    for result in results:
        status = "✅" if result.success else "❌"
        blocked = "🚫 BLOCKED" if result.blocked else ""
        captcha = "🤖 CAPTCHA" if result.captcha_detected else ""
        
        LOGGER.info(f"{status} {result.name:50s} {blocked} {captcha}")
        if result.error:
            LOGGER.info(f"   Error: {result.error}")
    
    LOGGER.info("=" * 80)
    
    # Success rate
    success_count = sum(1 for r in results if r.success)
    LOGGER.info(f"Success Rate: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
    
    # Save results to JSON
    results_path = Path(__file__).parent.parent / "logs/antibot_test_results.json"
    results_path.parent.mkdir(exist_ok=True)
    
    with open(results_path, "w") as f:
        json.dump(
            {
                "timestamp": time.time(),
                "results": [
                    {
                        "name": r.name,
                        "success": r.success,
                        "blocked": r.blocked,
                        "captcha_detected": r.captcha_detected,
                        "status_code": r.status_code,
                        "duration": r.duration,
                        "error": r.error,
                    }
                    for r in results
                ],
            },
            f,
            indent=2,
        )
    
    LOGGER.info(f"Results saved to: {results_path}")


if __name__ == "__main__":
    main()

