"""Google Trends executor -- thread-safe cooldown tracker."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from services.scrape_queue.models import ExecutorResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor.google_trends")


# ---------------------------------------------------------------------------
# Cooldown tracker
# ---------------------------------------------------------------------------


class _TrendsCooldown:
    """Thread-safe cooldown state for Google Trends rate limiting.

    Only enters cooldown on actual rate-limit responses (429), not on
    data errors like invalid year_released values.
    """

    DURATION_SECONDS = 3600

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_failure_at: float | None = None

    def remaining(self) -> float:
        """Seconds remaining in cooldown, or 0 if inactive."""
        with self._lock:
            if self._last_failure_at is None:
                return 0.0
            elapsed = time.time() - self._last_failure_at
            return max(self.DURATION_SECONDS - elapsed, 0.0)

    def activate(self) -> None:
        """Enter cooldown (called on rate-limit only)."""
        with self._lock:
            self._last_failure_at = time.time()
        logger.warning(
            "Google Trends rate limited -- entering %ds cooldown",
            self.DURATION_SECONDS,
        )

    def clear(self) -> None:
        """Clear cooldown after a successful request."""
        with self._lock:
            self._last_failure_at = None


_trends_cooldown = _TrendsCooldown()


def get_trends_cooldown_remaining() -> float:
    """Public accessor for the dispatcher timeout handler."""
    return _trends_cooldown.remaining()


def get_trends_cooldown_snapshot() -> dict:
    """Export Google Trends cooldown state for persistence."""
    remaining = _trends_cooldown.remaining()
    return {
        "blocked_until_wallclock": time.time() + remaining if remaining > 0 else 0.0,
    }


def restore_trends_cooldown_snapshot(snap: dict) -> None:
    """Restore Google Trends cooldown state from a saved snapshot."""
    blocked_wall = snap.get("blocked_until_wallclock", 0.0)
    remaining = blocked_wall - time.time()
    if remaining > 0:
        with _trends_cooldown._lock:
            _trends_cooldown._last_failure_at = time.time() - (
                _trends_cooldown.DURATION_SECONDS - remaining
            )
        logger.info(
            "Restored Google Trends cooldown: %.0f min remaining",
            remaining / 60,
        )


def execute_google_trends(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Fetch Google Trends interest data for a LEGO set."""
    from datetime import datetime, timedelta, timezone

    from services.enrichment.config import is_placeholder_title
    from services.google_trends.repository import save_trends_snapshot
    from services.google_trends.scraper import fetch_interest

    # Check cooldown
    remaining = _trends_cooldown.remaining()
    if remaining > 0:
        return ExecutorResult.cooldown(remaining)

    # Prerequisites
    item_row = conn.execute(
        "SELECT title, year_released FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if not item_row or not item_row[0] or not item_row[1]:
        return ExecutorResult.fail("Missing title or year_released")

    title, year_released = item_row[0], int(item_row[1])
    if is_placeholder_title(title):
        return ExecutorResult.fail("Placeholder title")

    # Freshness check
    row = conn.execute(
        """SELECT scraped_at FROM google_trends_snapshots
           WHERE set_number = ?
           ORDER BY scraped_at DESC LIMIT 1""",
        [set_number],
    ).fetchone()
    if row and row[0]:
        from db.queries import is_fresh

        if is_fresh(row[0], timedelta(days=30)):
            return ExecutorResult.ok()  # Already fresh

    # Fetch
    trends_result = fetch_interest(set_number, year_released=year_released)
    if not trends_result.success:
        if trends_result.rate_limited:
            _trends_cooldown.activate()
            return ExecutorResult.cooldown(_trends_cooldown.DURATION_SECONDS)
        return ExecutorResult.fail(
            trends_result.error or "Google Trends fetch failed"
        )

    save_trends_snapshot(conn, trends_result.data)
    _trends_cooldown.clear()

    logger.info(
        "Google Trends for %s: %d pts, peak=%s",
        set_number,
        len(trends_result.data.interest_over_time),
        trends_result.data.peak_value,
    )
    return ExecutorResult.ok()
