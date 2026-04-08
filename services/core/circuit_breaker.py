"""Unified circuit breaker / cooldown system.

Replaces three separate implementations:
- ``config.settings.HourlyRateLimiter`` (BrickLink, BrickEconomy, Keepa)
- ``services.enrichment.circuit_breaker.CircuitBreakerState`` (enrichment)
- ``services.scrape_queue.executors.google_trends._TrendsCooldown``

All three tracked failures and gated access with a cooldown window.
This module provides a single ``CircuitBreaker`` protocol and two
concrete strategies:

- ``EscalatingBreaker``: sliding-window rate limiter with escalating
  cooldowns (replaces HourlyRateLimiter).
- ``ThresholdBreaker``: trips after N consecutive failures, resets on
  success (replaces CircuitBreakerState + _TrendsCooldown).

Both share the same ``record_success`` / ``record_failure`` /
``is_available`` / ``cooldown_remaining`` interface.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger("bws.circuit_breaker")


# ---------------------------------------------------------------------------
# Protocol -- what every consumer depends on
# ---------------------------------------------------------------------------


class CircuitBreaker(Protocol):
    """Minimal interface for cooldown / circuit-breaking logic."""

    @property
    def source_name(self) -> str: ...

    def record_success(self) -> None: ...

    def record_failure(self, *, reason: str = "") -> None: ...

    def is_available(self) -> bool: ...

    def cooldown_remaining(self) -> float: ...

    def to_snapshot(self) -> dict: ...

    def restore_snapshot(self, snap: dict) -> None: ...


# ---------------------------------------------------------------------------
# Escalating breaker (replaces HourlyRateLimiter)
# ---------------------------------------------------------------------------


@dataclass
class EscalatingBreakerConfig:
    """Tuning knobs for ``EscalatingBreaker``."""

    source_name: str
    base_cooldown_seconds: float = 3600.0        # 1h
    forbidden_cooldown_seconds: float = 14400.0   # 4h
    max_cooldown_seconds: float = 28800.0         # 8h cap
    max_continuous_scrape_seconds: float = 10800.0  # 3h
    rest_period_seconds: float = 1800.0           # 30min
    max_per_hour: int = 1500


class EscalatingBreaker:
    """Sliding-window rate limiter with escalating cooldowns.

    Thread-safe.  Drop-in replacement for ``HourlyRateLimiter``.
    """

    def __init__(self, config: EscalatingBreakerConfig) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._blocked_until: float = 0.0
        self._escalation_level: int = 0
        self._consecutive_failures: int = 0
        self._scraping_since: float = 0.0
        self._was_blocked: bool = False
        self._timestamps: list[float] = []

    # -- Protocol ------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return self._cfg.source_name

    def record_success(self) -> None:
        with self._lock:
            if self._was_blocked:
                self._notify_recovered()
                self._was_blocked = False
            self._escalation_level = 0
            self._consecutive_failures = 0

    def record_failure(self, *, reason: str = "") -> None:
        """Generic failure -- uses base cooldown escalation."""
        with self._lock:
            self._trip(self._cfg.base_cooldown_seconds, reason or "rate_limited")

    def is_available(self) -> bool:
        with self._lock:
            return time.monotonic() >= self._blocked_until

    def cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def to_snapshot(self) -> dict:
        with self._lock:
            remaining = max(0.0, self._blocked_until - time.monotonic())
            return {
                "blocked_until_wallclock": time.time() + remaining if remaining > 0 else 0.0,
                "escalation_level": self._escalation_level,
                "consecutive_failures": self._consecutive_failures,
                "was_blocked": self._was_blocked,
            }

    def restore_snapshot(self, snap: dict) -> None:
        with self._lock:
            blocked_wall = snap.get("blocked_until_wallclock", 0.0)
            remaining = blocked_wall - time.time()
            self._blocked_until = (
                time.monotonic() + remaining if remaining > 0 else 0.0
            )
            self._escalation_level = snap.get("escalation_level", 0)
            self._consecutive_failures = snap.get("consecutive_failures", 0)
            self._was_blocked = snap.get("was_blocked", False)
            if remaining > 0:
                logger.info(
                    "Restored %s cooldown: %.0f min remaining",
                    self._cfg.source_name, remaining / 60,
                )

    # -- Extended API (specific trip reasons) ---------------------------------

    def trip_forbidden(self) -> None:
        """403 / IP ban -- longer base cooldown."""
        with self._lock:
            self._trip(self._cfg.forbidden_cooldown_seconds, "forbidden")

    def trip_silent_ban(self) -> None:
        """Consecutive 0-field responses."""
        with self._lock:
            self._trip(self._cfg.forbidden_cooldown_seconds, "silent_ban")

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    # -- Rest period (sustained scraping guard) -------------------------------

    def check_rest_period(self) -> float:
        """Return seconds to rest, or 0.0 if no rest needed."""
        with self._lock:
            now = time.monotonic()
            if self._scraping_since == 0.0:
                self._scraping_since = now
                return 0.0
            elapsed = now - self._scraping_since
            if elapsed >= self._cfg.max_continuous_scrape_seconds:
                self._scraping_since = 0.0
                logger.warning(
                    "Continuous scraping for %.0f min -- resting for %.0f min",
                    elapsed / 60, self._cfg.rest_period_seconds / 60,
                )
                return self._cfg.rest_period_seconds
            return 0.0

    # -- Internals -----------------------------------------------------------

    def _trip(self, base: float, reason: str) -> None:
        cooldown = min(
            base * (2 ** self._escalation_level),
            self._cfg.max_cooldown_seconds,
        )
        self._blocked_until = time.monotonic() + cooldown
        self._escalation_level += 1
        self._consecutive_failures += 1
        self._was_blocked = True
        self._scraping_since = 0.0
        logger.warning(
            "%s tripped (%s, level %d) -- pausing for %.0f min",
            self._cfg.source_name, reason,
            self._escalation_level, cooldown / 60,
        )
        self._notify_tripped(reason, cooldown)

    def _notify_tripped(self, reason: str, cooldown: float) -> None:
        try:
            from services.notifications.scraper_alerts import (
                alert_forbidden,
                alert_silent_ban,
            )

            if reason == "forbidden":
                alert_forbidden(self._cfg.source_name, cooldown / 60, self._escalation_level)
            elif reason == "silent_ban":
                alert_silent_ban(
                    self._cfg.source_name, self._consecutive_failures, cooldown / 60,
                )
            # rate_limited and rest_period are expected behavior — log only
        except ImportError:
            pass

    def _notify_recovered(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Threshold breaker (replaces CircuitBreakerState + _TrendsCooldown)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThresholdBreakerConfig:
    """Tuning knobs for ``ThresholdBreaker``."""

    source_name: str
    failure_threshold: int = 5
    cooldown_seconds: float = 3600.0


class ThresholdBreaker:
    """Trips after N consecutive failures, resets on success.

    Thread-safe.  Replaces both the enrichment ``CircuitBreakerState``
    (threshold-based) and ``_TrendsCooldown`` (single-shot cooldown).
    """

    def __init__(self, config: ThresholdBreakerConfig) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._consecutive_failures: int = 0
        self._tripped_at: float | None = None

    @property
    def source_name(self) -> str:
        return self._cfg.source_name

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._tripped_at = None

    def record_failure(self, *, reason: str = "") -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._cfg.failure_threshold:
                self._tripped_at = time.monotonic()
                logger.warning(
                    "%s circuit breaker tripped after %d failures (cooldown %.0fs)",
                    self._cfg.source_name,
                    self._consecutive_failures,
                    self._cfg.cooldown_seconds,
                )

    def is_available(self) -> bool:
        with self._lock:
            if self._tripped_at is None:
                return True
            elapsed = time.monotonic() - self._tripped_at
            if elapsed >= self._cfg.cooldown_seconds:
                # Half-open: allow one attempt
                self._tripped_at = None
                self._consecutive_failures = 0
                return True
            return False

    def cooldown_remaining(self) -> float:
        with self._lock:
            if self._tripped_at is None:
                return 0.0
            elapsed = time.monotonic() - self._tripped_at
            return max(0.0, self._cfg.cooldown_seconds - elapsed)

    def to_snapshot(self) -> dict:
        with self._lock:
            remaining = self.cooldown_remaining()
            return {
                "blocked_until_wallclock": time.time() + remaining if remaining > 0 else 0.0,
                "consecutive_failures": self._consecutive_failures,
            }

    def restore_snapshot(self, snap: dict) -> None:
        with self._lock:
            blocked_wall = snap.get("blocked_until_wallclock", 0.0)
            remaining = blocked_wall - time.time()
            if remaining > 0:
                self._tripped_at = time.monotonic() - (self._cfg.cooldown_seconds - remaining)
                logger.info(
                    "Restored %s cooldown: %.0f min remaining",
                    self._cfg.source_name, remaining / 60,
                )
            else:
                self._tripped_at = None
            self._consecutive_failures = snap.get("consecutive_failures", 0)


# ---------------------------------------------------------------------------
# Global registry -- one breaker per source, shared across the codebase
# ---------------------------------------------------------------------------

_registry: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def register_breaker(name: str, breaker: CircuitBreaker) -> CircuitBreaker:
    """Register a circuit breaker. Returns existing if already registered."""
    with _registry_lock:
        if name in _registry:
            return _registry[name]
        _registry[name] = breaker
        return breaker


def get_breaker(name: str) -> CircuitBreaker | None:
    """Look up a registered breaker by name."""
    with _registry_lock:
        return _registry.get(name)


def all_breakers() -> dict[str, CircuitBreaker]:
    """Return a snapshot of all registered breakers."""
    with _registry_lock:
        return dict(_registry)


def save_all_snapshots() -> dict[str, dict]:
    """Export all breaker states for persistence."""
    with _registry_lock:
        return {
            name: breaker.to_snapshot()
            for name, breaker in _registry.items()
        }


def restore_all_snapshots(data: dict[str, dict]) -> None:
    """Restore breaker states from a saved dict."""
    with _registry_lock:
        for name, snap in data.items():
            breaker = _registry.get(name)
            if breaker is not None:
                breaker.restore_snapshot(snap)
