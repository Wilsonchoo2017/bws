"""Token-bucket rate limiter for Reddit API calls.

Reddit's OAuth API allows 100 queries/minute per client for script apps.
We cap below that (60 QPM by default, configurable via REDDIT_RATE_LIMIT_QPM)
and enforce the budget with a classic token bucket so short bursts are
allowed but the long-run rate never exceeds the cap.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("bws.reddit.rate_limiter")


class TokenBucketRateLimiter:
    """Thread-safe token bucket.

    Tokens refill at `rate_per_second`. Each `acquire()` call waits until
    at least one token is available, then consumes it. The bucket capacity
    is equal to the per-minute rate (so a fresh bucket allows a one-minute
    burst before throttling kicks in).
    """

    def __init__(self, rate_per_minute: int) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self._capacity = float(rate_per_minute)
        self._rate_per_second = rate_per_minute / 60.0
        self._tokens = float(rate_per_minute)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._rate_per_second,
        )
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> None:
        """Block until `tokens` are available, then consume them."""
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                wait_seconds = deficit / self._rate_per_second
            # Release lock while we sleep so other threads can make
            # progress if they happen to hold spare tokens.
            logger.debug(
                "Rate limiter throttling: waiting %.2fs for %.1f tokens",
                wait_seconds,
                tokens,
            )
            time.sleep(wait_seconds)

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Non-blocking variant -- return True if tokens were consumed."""
        with self._lock:
            self._refill_locked()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def tokens_available(self) -> float:
        with self._lock:
            self._refill_locked()
            return self._tokens
