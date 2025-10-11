"""Generic anti-bot toolkit for web scraping.

This module provides reusable components for bypassing anti-bot measures:
- Proxy rotation and management
- User-agent and device fingerprinting
- Storage state management (cookies/localStorage)
- Captcha solving integration
- Circuit breakers and retry logic
- Request pacing and rate limiting
"""

from .captcha import CaptchaSolver, CaptchaTelemetry
from .fingerprint import DeviceFingerprint, FingerprintPainter, create_stealth_context
from .proxy import ProxyRotator, ProxyConfig
from .retry import CircuitBreaker, RetryBudget, EscalationMatrix
from .storage import StorageStateManager
from .user_agent import UserAgentPool

__all__ = [
    "CaptchaSolver",
    "CaptchaTelemetry",
    "DeviceFingerprint",
    "FingerprintPainter",
    "create_stealth_context",
    "ProxyRotator",
    "ProxyConfig",
    "CircuitBreaker",
    "RetryBudget",
    "EscalationMatrix",
    "StorageStateManager",
    "UserAgentPool",
]
