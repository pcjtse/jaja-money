"""Centralized token-bucket rate limiter for external API calls.

Thread-safe implementation that enforces requests-per-minute limits
across all concurrent callers (ThreadPoolExecutor workers, parallel
fetchers, server endpoints, etc.).

Usage:
    from rate_limiter import finnhub_limiter, anthropic_limiter

    finnhub_limiter.acquire()   # blocks until a token is available
    api.get_quote(symbol)       # safe to call
"""

from __future__ import annotations

import threading
import time

from log_setup import get_logger

log = get_logger(__name__)


class TokenBucketRateLimiter:
    """Thread-safe token-bucket rate limiter.

    Allows up to `max_tokens` requests per `refill_period` seconds.
    Tokens are refilled continuously (not in bulk).

    Parameters
    ----------
    max_tokens     : maximum burst size / bucket capacity
    refill_period  : seconds over which `max_tokens` are replenished
    name           : human-readable name for logging
    """

    def __init__(
        self,
        max_tokens: int = 55,
        refill_period: float = 60.0,
        name: str = "rate_limiter",
    ) -> None:
        self.max_tokens = max_tokens
        self.refill_period = refill_period
        self.name = name
        self._tokens = float(max_tokens)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * (self.max_tokens / self.refill_period)
        self._tokens = min(self.max_tokens, self._tokens + new_tokens)
        self._last_refill = now

    def acquire(self, timeout: float = 120.0) -> bool:
        """Block until a token is available or timeout is reached.

        Returns True if a token was acquired, False on timeout.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                # Calculate wait time for next token
                wait = (1.0 - self._tokens) * (self.refill_period / self.max_tokens)

            if time.monotonic() + wait > deadline:
                log.warning("%s: acquire timed out after %.1fs", self.name, timeout)
                return False

            time.sleep(min(wait, 0.5))

    def try_acquire(self) -> bool:
        """Non-blocking: return True if a token is available, else False."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    @property
    def available_tokens(self) -> float:
        """Return approximate number of available tokens (for monitoring)."""
        with self._lock:
            self._refill()
            return self._tokens


# ---------------------------------------------------------------------------
# Module-level singleton limiters
# ---------------------------------------------------------------------------

# Finnhub free tier: 60 req/min.  Use 55 to leave headroom.
finnhub_limiter = TokenBucketRateLimiter(
    max_tokens=55, refill_period=60.0, name="finnhub"
)

# Anthropic rate limits vary by tier; conservative default.
anthropic_limiter = TokenBucketRateLimiter(
    max_tokens=40, refill_period=60.0, name="anthropic"
)
