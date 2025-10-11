"""Anti-bot session management primitives shared across collectors."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional


class AntiBotStrategy(str, Enum):
    """Fallback chain order when scraping."""

    DIRECT_HTTP = "direct_http"
    SMART_PROXY = "smart_proxy"
    PLAYWRIGHT = "playwright"
    PLAYWRIGHT_CAPTCHA = "playwright_captcha"


@dataclass
class AntiBotSessionConfig:
    """
    Normalised configuration used by collectors to initialise clients.

    The goal is to replace ad-hoc environment lookups inside fetchers with a
    structured object that can be passed to worker processes or serialised
    into task queues.
    """

    user_agents: List[str] = field(default_factory=list)
    proxy_pool: List[str] = field(default_factory=list)
    storage_state_paths: List[Path] = field(default_factory=list)
    cookies_env_var: Optional[str] = None
    anticaptcha_key: Optional[str] = None
    max_retries_per_stage: int = 2
    strategy_order: List[AntiBotStrategy] = field(
        default_factory=lambda: [
            AntiBotStrategy.DIRECT_HTTP,
            AntiBotStrategy.SMART_PROXY,
            AntiBotStrategy.PLAYWRIGHT,
            AntiBotStrategy.PLAYWRIGHT_CAPTCHA,
        ]
    )

    def resolve_storage_states(self) -> List[Path]:
        """Filter out non-existing storage-state files."""
        resolved: List[Path] = []
        for raw in self.storage_state_paths:
            path = raw.expanduser()
            if path.exists():
                resolved.append(path)
        return resolved

    def iter_proxies(self) -> Iterable[str]:
        """Round-robin style iterator placeholder."""
        for proxy in self.proxy_pool:
            yield proxy

