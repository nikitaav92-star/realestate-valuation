"""Smart proxy management with validation and auto-refresh."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import subprocess
import sys

import httpx

LOGGER = logging.getLogger(__name__)
PROXY_POOL_FILE = Path(__file__).parent.parent.parent / "config/proxy_pool.txt"
REFRESH_SCRIPT = Path(__file__).parent.parent.parent / "config/refresh_proxies.py"


@dataclass
class ProxyConfig:
    """Configuration for a single proxy."""
    url: str
    server: str
    username: str
    password: str

    @classmethod
    def from_url(cls, url: str) -> ProxyConfig:
        """Parse proxy URL format: http://username:password@host:port"""
        url_clean = url.replace("http://", "").replace("https://", "")
        credentials, server = url_clean.split("@")
        username, password = credentials.split(":")
        return cls(
            url=url,
            server=f"http://{server}",
            username=username,
            password=password,
        )


def load_proxy_pool() -> List[str]:
    """Load proxy pool from config/proxy_pool.txt file.

    Returns
    -------
    List[str]
        List of proxy URLs in format: http://username:password@host:port
    """
    proxies = []

    if not PROXY_POOL_FILE.exists():
        LOGGER.warning(f"❌ No proxy pool file found: {PROXY_POOL_FILE}")
        return proxies

    with open(PROXY_POOL_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            proxies.append(line)

    LOGGER.info(f"📋 Loaded {len(proxies)} proxies from pool")
    return proxies


def get_random_proxy(proxy_pool: List[str]) -> Optional[str]:
    """Get a random proxy from the pool."""
    import random
    return random.choice(proxy_pool) if proxy_pool else None


def validate_proxy(proxy_url: str, timeout: float = 10.0) -> tuple[bool, Optional[str], Optional[str]]:
    """Validate proxy by making test request to ipify.org.

    NOTE: We don't check CIAN API because it's blocked for ALL proxies.
    We use HTML parsing instead, which works fine through proxy.

    Parameters
    ----------
    proxy_url : str
        Proxy URL in format: http://username:password@host:port
    timeout : float
        Request timeout in seconds

    Returns
    -------
    tuple[bool, Optional[str], Optional[str]]
        (is_valid, detected_ip, error_message)
    """
    LOGGER.info(f"🔍 Validating proxy...")

    try:
        # Parse proxy
        proxy_config = ProxyConfig.from_url(proxy_url)

        # Make test request to verify proxy is working
        # httpx uses 'proxy' parameter (not 'proxies')
        with httpx.Client(proxy=proxy_url, timeout=timeout) as client:
            response = client.get("https://api.ipify.org?format=json")
            response.raise_for_status()

            detected_ip = response.json().get("ip")
            LOGGER.info(f"✅ Proxy is active! Detected IP: {detected_ip}")

            # Note: CIAN API is blocked for all proxies (404),
            # but HTML parsing works fine. So we only check proxy connectivity.
            return True, detected_ip, None

    except httpx.TimeoutException as e:
        error = f"Timeout after {timeout}s"
        LOGGER.error(f"❌ Proxy validation failed: {error}")
        return False, None, error
    except Exception as e:
        error = str(e)
        LOGGER.error(f"❌ Proxy validation failed: {error}")
        return False, None, error


def refresh_proxy_pool() -> bool:
    """Refresh proxy pool by running refresh_proxies.py script.

    Returns
    -------
    bool
        True if refresh was successful, False otherwise
    """
    LOGGER.info(f"🔄 Refreshing proxy pool...")

    if not REFRESH_SCRIPT.exists():
        LOGGER.error(f"❌ Refresh script not found: {REFRESH_SCRIPT}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(REFRESH_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            LOGGER.info(f"✅ Proxy pool refreshed successfully")
            LOGGER.debug(result.stdout)
            return True
        else:
            LOGGER.error(f"❌ Failed to refresh proxy pool: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        LOGGER.error(f"❌ Proxy refresh timed out after 30s")
        return False
    except Exception as e:
        LOGGER.error(f"❌ Failed to refresh proxy pool: {e}")
        return False


def get_validated_proxy(auto_refresh: bool = True) -> Optional[str]:
    """Get a validated proxy, optionally refreshing pool if validation fails.

    This function implements step 1 and 2 from the strategy:
    1. Check if proxy is valid and active
    2. If not, refresh proxy pool

    Parameters
    ----------
    auto_refresh : bool
        If True, automatically refresh proxy pool if validation fails

    Returns
    -------
    Optional[str]
        Valid proxy URL or None if no valid proxy available
    """
    # Load proxy pool
    proxy_pool = load_proxy_pool()

    if not proxy_pool:
        LOGGER.warning("📭 Proxy pool is empty")

        if auto_refresh:
            LOGGER.info("🔄 Auto-refreshing proxy pool...")
            if refresh_proxy_pool():
                proxy_pool = load_proxy_pool()
            else:
                return None
        else:
            return None

    # Try to find valid proxy
    for proxy_url in proxy_pool:
        is_valid, detected_ip, error = validate_proxy(proxy_url)

        if is_valid:
            return proxy_url

    # No valid proxy found
    LOGGER.warning("⚠️  No valid proxy found in pool")

    if auto_refresh:
        LOGGER.info("🔄 Auto-refreshing proxy pool and retrying...")
        if refresh_proxy_pool():
            # Try again with fresh proxies
            proxy_pool = load_proxy_pool()
            for proxy_url in proxy_pool:
                is_valid, detected_ip, error = validate_proxy(proxy_url)
                if is_valid:
                    return proxy_url

    return None
