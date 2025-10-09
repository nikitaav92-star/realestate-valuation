"""Async helpers for fetching offer pages from the official CIAN grouped endpoint."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

import httpx
import yaml
from tenacity import retry, stop_after_attempt, wait_random

CIAN_URL = "https://www.cian.ru/site/v1/offers/search/grouped/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = httpx.Timeout(20.0)
LOGGER = logging.getLogger(__name__)


def load_payload(path: str | Path) -> Dict[str, Any]:
    """Read YAML payload that defines jsonQuery filters."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("payload must be a dictionary")
    if "jsonQuery" not in data:
        raise ValueError("payload must contain jsonQuery section")
    return data


def build_request_payload(base: Dict[str, Any], page: int) -> Dict[str, Any]:
    """Prepare request payload for selected page."""
    payload = dict(base)
    payload.setdefault("limit", 20)
    payload["page"] = page
    return payload


@retry(stop=stop_after_attempt(3), wait=wait_random(1, 3))
async def fetch_page(
    session: httpx.AsyncClient,
    base_payload: Dict[str, Any],
    page: int,
) -> Dict[str, Any]:
    """Fetch a single page of offers, retrying on transient errors."""
    payload = build_request_payload(base_payload, page)
    response = await session.post(CIAN_URL, json=payload)
    response.raise_for_status()
    LOGGER.debug("Fetched page %s (status=%s)", page, response.status_code)
    return response.json()


async def collect(payload: Dict[str, Any], pages: int) -> list[Dict[str, Any]]:
    """Collect multiple pages sequentially with RPS ≤ 2."""
    results: list[Dict[str, Any]] = []
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://www.cian.ru/",
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as session:
        for page in range(1, pages + 1):
            results.append(await fetch_page(session, payload, page))
            await asyncio.sleep(0.6)  # ~1.6 RPS
    return results


if __name__ == "__main__":  # pragma: no cover - manual smoke helper
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    payload = load_payload("etl/collector_cian/payloads/base.yaml")
    pages = asyncio.run(collect(payload, pages=1))
    LOGGER.info("Fetched %d page(s)", len(pages))
