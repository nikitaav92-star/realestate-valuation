"""Base product fetcher with anti-bot integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from ..antibot import (
    CaptchaSolver,
    CircuitBreaker,
    CircuitBreakerConfig,
    ProxyConfig,
    StorageStateManager,
    UserAgentPool,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of product fetch operation."""
    
    success: bool
    product_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    escalation_level: str = "http_direct"
    captcha_solved: bool = False
    proxy_used: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "product_data": self.product_data,
            "error": self.error,
            "escalation_level": self.escalation_level,
            "captcha_solved": self.captcha_solved,
            "proxy_used": self.proxy_used,
        }


class ProductFetcher(Protocol):
    """Abstract product fetcher interface."""
    
    def fetch(self, url: str, external_id: str) -> FetchResult:
        """Fetch product data from URL.
        
        Parameters
        ----------
        url : str
            Product page URL
        external_id : str
            Product ID from source site
            
        Returns
        -------
        FetchResult
            Fetch result with product data or error
        """
        ...


class BaseFetcher:
    """Base fetcher with anti-bot helpers.
    
    Subclass this and implement _fetch_http() and _parse_response().
    """
    
    def __init__(
        self,
        *,
        proxy_config: Optional[ProxyConfig] = None,
        captcha_solver: Optional[CaptchaSolver] = None,
        storage_manager: Optional[StorageStateManager] = None,
        user_agent_pool: Optional[UserAgentPool] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        """Initialize base fetcher.
        
        Parameters
        ----------
        proxy_config : ProxyConfig, optional
            Proxy configuration
        captcha_solver : CaptchaSolver, optional
            Captcha solver instance
        storage_manager : StorageStateManager, optional
            Storage state manager
        user_agent_pool : UserAgentPool, optional
            User-agent pool
        circuit_breaker : CircuitBreaker, optional
            Circuit breaker instance
        """
        self.proxy_config = proxy_config or ProxyConfig.from_env()
        self.captcha_solver = captcha_solver
        self.storage_manager = storage_manager
        self.user_agent_pool = user_agent_pool or UserAgentPool()
        
        if circuit_breaker is None:
            cb_config = CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout=60.0,
            )
            self.circuit_breaker = CircuitBreaker(cb_config)
        else:
            self.circuit_breaker = circuit_breaker
    
    def fetch(self, url: str, external_id: str) -> FetchResult:
        """Fetch product with escalation fallback.
        
        Tries in order:
        1. HTTP direct
        2. HTTP with proxy
        3. Playwright headless
        4. Playwright headed (if captcha solver available)
        """
        LOGGER.info("Fetching product: %s (ID=%s)", url, external_id)
        
        # Try HTTP direct first
        try:
            result = self.circuit_breaker.call(
                self._fetch_http,
                url,
                external_id,
                use_proxy=False,
            )
            if result.success:
                return result
        except Exception as exc:
            LOGGER.warning("HTTP direct failed: %s", exc)
        
        # Try HTTP with proxy
        if self.proxy_config:
            try:
                result = self.circuit_breaker.call(
                    self._fetch_http,
                    url,
                    external_id,
                    use_proxy=True,
                )
                if result.success:
                    return result
            except Exception as exc:
                LOGGER.warning("HTTP with proxy failed: %s", exc)
        
        # Escalate to Playwright if HTTP fails
        LOGGER.info("Escalating to Playwright for %s", url)
        
        try:
            result = self._fetch_playwright(url, external_id, headless=True)
            if result.success:
                return result
        except Exception as exc:
            LOGGER.warning("Playwright headless failed: %s", exc)
        
        # Final escalation: headed browser with captcha solving
        if self.captcha_solver:
            try:
                result = self._fetch_playwright(url, external_id, headless=False)
                return result
            except Exception as exc:
                LOGGER.error("Playwright headed failed: %s", exc)
                return FetchResult(
                    success=False,
                    error=f"All escalation levels failed: {exc}",
                    escalation_level="playwright_headed",
                )
        
        return FetchResult(
            success=False,
            error="All fetch methods exhausted",
            escalation_level="playwright_headless",
        )
    
    def _fetch_http(
        self,
        url: str,
        external_id: str,
        use_proxy: bool = False,
    ) -> FetchResult:
        """Fetch via HTTP (to be implemented by subclass).
        
        Parameters
        ----------
        url : str
            Product URL
        external_id : str
            Product ID
        use_proxy : bool
            Whether to use proxy
            
        Returns
        -------
        FetchResult
            Fetch result
        """
        raise NotImplementedError("Subclass must implement _fetch_http()")
    
    def _fetch_playwright(
        self,
        url: str,
        external_id: str,
        headless: bool = True,
    ) -> FetchResult:
        """Fetch via Playwright (to be implemented by subclass).
        
        Parameters
        ----------
        url : str
            Product URL
        external_id : str
            Product ID
        headless : bool
            Run headless browser
            
        Returns
        -------
        FetchResult
            Fetch result
        """
        raise NotImplementedError("Subclass must implement _fetch_playwright()")
    
    def _parse_response(self, html: str, url: str) -> Dict[str, Any]:
        """Parse HTML response into product data (to be implemented by subclass).
        
        Parameters
        ----------
        html : str
            HTML response
        url : str
            Product URL
            
        Returns
        -------
        dict
            Product data dictionary
        """
        raise NotImplementedError("Subclass must implement _parse_response()")

