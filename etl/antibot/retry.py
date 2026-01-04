"""Circuit breaker and retry budget management."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TypeVar

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""
    
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    
    failure_threshold: int = 5  # Open circuit after N failures
    success_threshold: int = 2  # Close circuit after N successes in half-open
    timeout: float = 60.0  # Seconds to wait before trying half-open
    expected_exceptions: tuple = (Exception,)  # Exceptions that count as failures


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures."""
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None) -> None:
        """Initialize circuit breaker.
        
        Parameters
        ----------
        config : CircuitBreakerConfig, optional
            Configuration (uses defaults if not provided)
        """
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection.
        
        Parameters
        ----------
        func : callable
            Function to call
        *args, **kwargs
            Arguments to pass to function
            
        Returns
        -------
        T
            Function result
            
        Raises
        ------
        RuntimeError
            If circuit is open
        Exception
            If function raises expected exception
        """
        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if self.last_failure_time is None:
                raise RuntimeError("Circuit breaker is OPEN (no failure time recorded)")
            
            if time.time() - self.last_failure_time < self.config.timeout:
                raise RuntimeError(
                    f"Circuit breaker is OPEN (failed {self.failure_count} times, "
                    f"wait {self.config.timeout:.0f}s before retry)"
                )
            
            # Timeout elapsed, try half-open
            LOGGER.info("Circuit breaker transitioning to HALF_OPEN")
            self.state = CircuitState.HALF_OPEN
            self.success_count = 0
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exceptions as exc:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            LOGGER.debug(
                "Circuit breaker success in HALF_OPEN (%d/%d)",
                self.success_count,
                self.config.success_threshold,
            )
            
            if self.success_count >= self.config.success_threshold:
                LOGGER.info("Circuit breaker transitioning to CLOSED (recovered)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_failure_time = None
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            if self.failure_count > 0:
                self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            LOGGER.warning("Circuit breaker failure in HALF_OPEN, reopening")
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                LOGGER.warning(
                    "Circuit breaker OPEN after %d failures",
                    self.failure_count,
                )
                self.state = CircuitState.OPEN
    
    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        LOGGER.info("Circuit breaker manually reset")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN


@dataclass
class RetryBudget:
    """Retry budget tracker for rate limiting retries."""
    
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff: float = 60.0
    
    def __post_init__(self):
        self.attempts = 0
    
    def should_retry(self) -> bool:
        """Check if we should retry based on budget."""
        return self.attempts < self.max_retries
    
    def get_backoff_delay(self) -> float:
        """Calculate backoff delay for current attempt."""
        delay = self.backoff_base * (self.backoff_multiplier ** self.attempts)
        return min(delay, self.max_backoff)
    
    def record_attempt(self) -> None:
        """Record a retry attempt."""
        self.attempts += 1
    
    def reset(self) -> None:
        """Reset retry budget."""
        self.attempts = 0


class EscalationMatrix:
    """Manages fallback escalation strategy (HTTP → Smart Proxy → Playwright)."""
    
    def __init__(self):
        """Initialize escalation matrix."""
        self.levels = [
            "http_direct",
            "http_with_proxy",
            "smart_proxy",
            "playwright_headless",
            "playwright_headed",
        ]
        self.current_level = 0
    
    def escalate(self) -> Optional[str]:
        """Escalate to next level.
        
        Returns
        -------
        str or None
            Next level name, or None if exhausted
        """
        self.current_level += 1
        if self.current_level >= len(self.levels):
            return None
        
        level = self.levels[self.current_level]
        LOGGER.info("Escalating to level %d: %s", self.current_level, level)
        return level
    
    def get_current_level(self) -> str:
        """Get current escalation level."""
        return self.levels[self.current_level]
    
    def reset(self) -> None:
        """Reset to initial level."""
        self.current_level = 0

