"""Smart proxy management with validation and auto-refresh."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set
import subprocess
import sys
import random

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


def get_validated_proxy(auto_refresh: bool = True, max_attempts: int = 3, exclude_proxies: Optional[Set[str]] = None) -> Optional[str]:
    """Get a validated proxy, optionally refreshing pool if validation fails.

    This function implements step 1 and 2 from the strategy:
    1. Check if proxy is valid and active
    2. If not, refresh proxy pool

    Parameters
    ----------
    auto_refresh : bool
        If True, automatically refresh proxy pool if validation fails
    max_attempts : int
        Maximum number of refresh attempts
    exclude_proxies : set of str, optional
        Set of proxy URLs to exclude (e.g., recently failed proxies)

    Returns
    -------
    Optional[str]
        Valid proxy URL or None if no valid proxy available
    """
    exclude_proxies = exclude_proxies or set()
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        
        # Load proxy pool
        proxy_pool = load_proxy_pool()

        if not proxy_pool:
            LOGGER.warning("📭 Proxy pool is empty (attempt %d/%d)", attempt, max_attempts)

            if auto_refresh:
                LOGGER.info("🔄 Auto-refreshing proxy pool...")
                if refresh_proxy_pool():
                    proxy_pool = load_proxy_pool()
                else:
                    if attempt < max_attempts:
                        LOGGER.info("⏳ Waiting 5 seconds before retry...")
                        time.sleep(5)
                        continue
                    return None
            else:
                return None

        # Filter out excluded proxies
        available_proxies = [p for p in proxy_pool if p not in exclude_proxies]
        
        if not available_proxies:
            LOGGER.warning("⚠️ All proxies in pool are excluded, clearing exclusions...")
            available_proxies = proxy_pool
            exclude_proxies.clear()

        # Try to find valid proxy (check all proxies in pool)
        valid_proxies = []
        for proxy_url in available_proxies:
            is_valid, detected_ip, error = validate_proxy(proxy_url, timeout=15.0)

            if is_valid:
                valid_proxies.append((proxy_url, detected_ip))
        
        if valid_proxies:
            # Return first valid proxy
            chosen_proxy, detected_ip = valid_proxies[0]
            LOGGER.info(f"✅ Found {len(valid_proxies)} valid proxies. Using: {detected_ip}")
            return chosen_proxy

        # No valid proxy found
        LOGGER.warning("⚠️  No valid proxy found in pool (attempt %d/%d)", attempt, max_attempts)

        if auto_refresh and attempt < max_attempts:
            LOGGER.info("🔄 Auto-refreshing proxy pool and retrying...")
            if refresh_proxy_pool():
                LOGGER.info("⏳ Waiting 5 seconds for proxies to stabilize...")
                time.sleep(5)
                continue
            else:
                if attempt < max_attempts:
                    LOGGER.info("⏳ Refresh failed, waiting 5 seconds before retry...")
                    time.sleep(5)
                    continue

    LOGGER.error("❌ Failed to get valid proxy after %d attempts", max_attempts)
    return None


@dataclass
class ProxyRotator:
    """Auto-rotating proxy manager with failure tracking and blacklisting."""
    
    proxies: List[str] = field(default_factory=list)
    current_index: int = 0
    failed_proxies: Set[str] = field(default_factory=set)
    max_failures_per_proxy: int = 3
    failure_counts: dict = field(default_factory=dict)
    last_refresh: float = 0
    refresh_interval: int = 600  # 10 minutes
    
    def __post_init__(self):
        """Initialize proxy pool on creation."""
        if not self.proxies:
            self.refresh_pool()
    
    def refresh_pool(self, force: bool = False) -> bool:
        """Refresh proxy pool from file or generate new ones.
        
        Parameters
        ----------
        force : bool
            Force refresh even if recently refreshed
            
        Returns
        -------
        bool
            True if refresh was successful
        """
        current_time = time.time()
        if not force and (current_time - self.last_refresh) < self.refresh_interval:
            LOGGER.debug("Skipping proxy refresh, last refresh was recent")
            return True
        
        LOGGER.info("🔄 Refreshing proxy pool...")
        
        # Try to refresh proxies using the script
        if refresh_proxy_pool():
            self.proxies = load_proxy_pool()
            self.last_refresh = current_time
            self.failed_proxies.clear()
            self.failure_counts.clear()
            self.current_index = 0
            LOGGER.info(f"✅ Proxy pool refreshed with {len(self.proxies)} proxies")
            return True
        else:
            # Fallback: load existing proxies
            self.proxies = load_proxy_pool()
            if self.proxies:
                LOGGER.warning(f"⚠️ Using existing proxy pool ({len(self.proxies)} proxies)")
                return True
            else:
                LOGGER.error("❌ No proxies available")
                return False
    
    def get_next_proxy(self) -> Optional[str]:
        """Get next available proxy (round-robin, skipping failed).
        
        Returns
        -------
        Optional[str]
            Next proxy URL or None if all proxies failed
        """
        if not self.proxies:
            LOGGER.warning("📭 Proxy pool is empty, refreshing...")
            if not self.refresh_pool(force=True):
                return None
        
        # Filter out completely failed proxies
        available = [p for p in self.proxies if p not in self.failed_proxies]
        
        if not available:
            LOGGER.warning("⚠️ All proxies failed, refreshing pool...")
            if self.refresh_pool(force=True):
                available = [p for p in self.proxies if p not in self.failed_proxies]
            
            if not available:
                LOGGER.error("❌ No working proxies available after refresh")
                return None
        
        # Get next proxy in rotation
        proxy = available[self.current_index % len(available)]
        self.current_index = (self.current_index + 1) % len(available)
        
        return proxy
    
    def mark_failure(self, proxy_url: str, error_type: str = "unknown") -> None:
        """Mark a proxy as failed and potentially blacklist it.
        
        Parameters
        ----------
        proxy_url : str
            Proxy URL that failed
        error_type : str
            Type of error (e.g., "timeout", "connection", "blocked")
        """
        self.failure_counts[proxy_url] = self.failure_counts.get(proxy_url, 0) + 1
        
        LOGGER.warning(
            f"⚠️ Proxy failure ({error_type}): {proxy_url[:60]}... "
            f"(failures: {self.failure_counts[proxy_url]}/{self.max_failures_per_proxy})"
        )
        
        if self.failure_counts[proxy_url] >= self.max_failures_per_proxy:
            self.failed_proxies.add(proxy_url)
            LOGGER.error(f"❌ Proxy blacklisted after {self.failure_counts[proxy_url]} failures: {proxy_url[:60]}...")
    
    def mark_success(self, proxy_url: str) -> None:
        """Mark a proxy as successful (reset failure counter).
        
        Parameters
        ----------
        proxy_url : str
            Proxy URL that succeeded
        """
        if proxy_url in self.failure_counts:
            del self.failure_counts[proxy_url]
        if proxy_url in self.failed_proxies:
            self.failed_proxies.remove(proxy_url)
    
    def get_stats(self) -> dict:
        """Get current proxy pool statistics.
        
        Returns
        -------
        dict
            Statistics about proxy pool
        """
        return {
            "total_proxies": len(self.proxies),
            "failed_proxies": len(self.failed_proxies),
            "available_proxies": len(self.proxies) - len(self.failed_proxies),
            "failure_counts": dict(self.failure_counts),
        }
