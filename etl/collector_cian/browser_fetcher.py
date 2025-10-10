"""Playwright-based fallback collector for CIAN."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import orjson
from playwright.sync_api import sync_playwright
from urllib.parse import urlencode

from .fetcher import CIAN_URL, build_request_payload
from .captcha_solver import CaptchaSolver


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _build_search_url(payload: Dict[str, Any]) -> str:
    query: Dict[str, Any] = {}
    q = payload.get("jsonQuery", {})
    region = (q.get("region") or {}).get("value")
    if region:
        query["region"] = region[0] if isinstance(region, list) else region
    engine_version = (q.get("engine_version") or {}).get("value")
    if engine_version:
        query["engine_version"] = engine_version
    deal_type = (q.get("deal_type") or {}).get("value")
    if deal_type:
        query["deal_type"] = deal_type
    offer_type = (q.get("offer_type") or {}).get("value")
    if offer_type:
        query["offer_type"] = offer_type
    price = (q.get("price") or {}).get("value") or {}
    if price.get("gte"):
        query["minprice"] = price["gte"]
    if price.get("lte"):
        query["maxprice"] = price["lte"]
    area = (q.get("area") or {}).get("value") or {}
    if area.get("gte"):
        query["minarea"] = area["gte"]
    if area.get("lte"):
        query["maxarea"] = area["lte"]
    room_values = (q.get("room") or {}).get("value") or []
    for val in room_values:
        query.setdefault(f"room{val}", 1)
    params = urlencode(query, doseq=True)
    return f"https://www.cian.ru/cat.php?{params}" if params else "https://www.cian.ru/cat.php"


def collect_with_playwright(
    payload: Dict[str, Any],
    pages: int,
    *,
    headless: bool | None = None,
    slow_mo: int | None = None,
) -> List[Dict[str, Any]]:
    """Fetch pages via a real Chromium session using Playwright.

    Parameters
    ----------
    payload: dict
        Base payload (jsonQuery, limit, etc.)
    pages: int
        Number of pages to fetch sequentially.
    headless: bool
        Launch browser in headless mode; set False for manual captcha solving.
    slow_mo: int
        Optional delay (ms) for troubleshooting.
    """
    if headless is None:
        headless = _env_bool("CIAN_HEADLESS", True)
    if slow_mo is None:
        slow_mo = int(os.getenv("CIAN_SLOW_MO", "0") or 0)

    results: List[Dict[str, Any]] = []
    solver: CaptchaSolver | None = None
    if os.getenv("ANTICAPTCHA_KEY"):
        solver = CaptchaSolver()
    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
        ]
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo, args=launch_args)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = context.new_page()
        search_url = _build_search_url(payload)
        page.goto(search_url, wait_until="networkidle")
        if solver:
            try:
                site_key = page.eval_on_selector("[data-sitekey]", "el => el.getAttribute('data-sitekey')")
            except Exception:
                site_key = None
            if site_key:
                token = solver.solve(site_key, search_url)
                page.evaluate(
                    """
                    token => {
                        document.cookie = `smartCaptchaToken=${token};path=/;max-age=600`;
                        const input = document.querySelector('input[name="smart-token"], input[name="smartCaptchaToken"]');
                        if (input) {
                            input.value = token;
                        }
                        window.dispatchEvent(new CustomEvent('smartCaptchaToken', { detail: token }));
                    }
                    """,
                    token,
                )
                page.wait_for_timeout(2000)
        api_request_context = context.request
        for page_number in range(1, pages + 1):
            request_payload = build_request_payload(payload, page_number)
            response = api_request_context.post(
                CIAN_URL,
                headers={
                    "content-type": "application/json",
                    "accept": "application/json",
                    "origin": "https://www.cian.ru",
                    "referer": "https://www.cian.ru/",
                },
                data=orjson.dumps(request_payload),
            )
            if not response.ok:
                raise RuntimeError(f"Playwright request failed: {response.status} {response.text()}" )
            results.append(response.json())
            time.sleep(0.6)
        browser.close()
    return results
