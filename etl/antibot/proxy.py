"""Proxy rotation and management."""
from __future__ import annotations

import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProxyProvider(str, Enum):
    """Supported proxy providers."""
    
    BRIGHT_DATA = "brightdata"
    NODE_MAVEN = "nodemaven"
    SMART_PROXY = "smartproxy"
    CUSTOM = "custom"


@dataclass
class ProxyConfig:
    """Proxy configuration."""
    
    server: str
    username: Optional[str] = None
    password: Optional[str] = None
    provider: ProxyProvider = ProxyProvider.CUSTOM
    
    @classmethod
    def from_url(cls, url: str, provider: ProxyProvider = ProxyProvider.CUSTOM) -> ProxyConfig:
        """Parse proxy from URL format.
        
        Format: http://username:password@host:port
        """
        if "@" in url:
            # Extract credentials
            scheme_and_creds, server = url.rsplit("@", 1)
            if "://" in scheme_and_creds:
                scheme, creds = scheme_and_creds.split("://", 1)
                server = f"{scheme}://{server}"
            else:
                creds = scheme_and_creds
            
            if ":" in creds:
                username, password = creds.split(":", 1)
            else:
                username = creds
                password = None
            
            return cls(
                server=server,
                username=username,
                password=password,
                provider=provider,
            )
        else:
            return cls(server=url, provider=provider)
    
    @classmethod
    def from_env(cls) -> Optional[ProxyConfig]:
        """Load proxy configuration from environment variables.
        
        Checks (in order):
        - NODEMAVEN_PROXY_URL
        - BRIGHTDATA_PROXY_URL
        - SMART_PROXY_URL
        - PROXY_URL
        """
        if url := os.getenv("NODEMAVEN_PROXY_URL"):
            return cls.from_url(url, ProxyProvider.NODE_MAVEN)
        if url := os.getenv("BRIGHTDATA_PROXY_URL"):
            return cls.from_url(url, ProxyProvider.BRIGHT_DATA)
        if url := os.getenv("SMART_PROXY_URL"):
            return cls.from_url(url, ProxyProvider.SMART_PROXY)
        if url := os.getenv("PROXY_URL"):
            return cls.from_url(url, ProxyProvider.CUSTOM)
        return None
    
    def to_playwright_dict(self) -> dict:
        """Convert to Playwright proxy format."""
        proxy_dict = {"server": self.server}
        if self.username:
            proxy_dict["username"] = self.username
        if self.password:
            proxy_dict["password"] = self.password
        return proxy_dict
    
    def to_httpx_url(self) -> str:
        """Convert to httpx proxy URL format."""
        if self.username and self.password:
            # Extract scheme and host from server
            if "://" in self.server:
                scheme, host = self.server.split("://", 1)
                return f"{scheme}://{self.username}:{self.password}@{host}"
            else:
                return f"http://{self.username}:{self.password}@{self.server}"
        return self.server


class ProxyRotator:
    """Rotating proxy manager."""
    
    def __init__(self, proxies: list[ProxyConfig]) -> None:
        """Initialize proxy rotator.
        
        Parameters
        ----------
        proxies : list[ProxyConfig]
            List of proxy configurations
        """
        if not proxies:
            raise ValueError("ProxyRotator requires at least one proxy")
        self.proxies = proxies
        self.current_index = 0
        self.failure_counts: dict[str, int] = {p.server: 0 for p in proxies}
        self.max_failures = 3
    
    def get_next(self) -> ProxyConfig:
        """Get next proxy in rotation (round-robin)."""
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def get_random(self) -> ProxyConfig:
        """Get random proxy (weighted by failure count)."""
        # Filter out proxies with too many failures
        available = [
            p for p in self.proxies
            if self.failure_counts[p.server] < self.max_failures
        ]
        
        if not available:
            # Reset all failure counts if all proxies are exhausted
            self.failure_counts = {p.server: 0 for p in self.proxies}
            available = self.proxies
        
        return random.choice(available)
    
    def mark_failure(self, proxy: ProxyConfig) -> None:
        """Mark a proxy as failed."""
        self.failure_counts[proxy.server] = self.failure_counts.get(proxy.server, 0) + 1
    
    def mark_success(self, proxy: ProxyConfig) -> None:
        """Mark a proxy as successful (reset failure count)."""
        self.failure_counts[proxy.server] = 0
    
    def get_healthy_proxies(self) -> list[ProxyConfig]:
        """Get list of healthy proxies (below failure threshold)."""
        return [
            p for p in self.proxies
            if self.failure_counts[p.server] < self.max_failures
        ]
    
    @classmethod
    def from_env_list(cls, env_var: str = "PROXY_LIST") -> Optional[ProxyRotator]:
        """Create rotator from comma-separated environment variable.
        
        Parameters
        ----------
        env_var : str
            Environment variable name containing comma-separated proxy URLs
            
        Returns
        -------
        ProxyRotator or None
            Rotator if proxies found, None otherwise
        """
        proxy_list = os.getenv(env_var)
        if not proxy_list:
            return None
        
        proxies = []
        for url in proxy_list.split(","):
            url = url.strip()
            if url:
                proxies.append(ProxyConfig.from_url(url))
        
        if not proxies:
            return None
        
        return cls(proxies)

