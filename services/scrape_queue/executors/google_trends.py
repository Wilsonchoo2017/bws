"""Google Trends executor -- thread-safe cooldown tracker.

Pipeline: prerequisites (pure) -> freshness check (IO) -> fetch (IO) -> persist (IO).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from services.core.result import Err, Ok, Result
from services.scrape_queue.models import ErrorCategory, ExecutorResult, TaskType
from services.scrape_queue.registry import executor

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor.google_trends")


# ---------------------------------------------------------------------------
# Cooldown tracker
# ---------------------------------------------------------------------------


class _TrendsCooldown:
    """Thread-safe cooldown state for Google Trends rate limiting."""

    DURATION_SECONDS = 3600

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_failure_at: float | None = None

    def remaining(self) -> float:
        with self._lock:
            if self._last_failure_at is None:
                return 0.0
            elapsed = time.time() - self._last_failure_at
            return max(self.DURATION_SECONDS - elapsed, 0.0)

    def activate(self) -> None:
        with self._lock:
            self._last_failure_at = time.time()
        logger.warning(
            "Google Trends rate limited -- entering %ds cooldown",
            self.DURATION_SECONDS,
        )

    def clear(self) -> None:
        with self._lock:
            self._last_failure_at = None


_trends_cooldown = _TrendsCooldown()


def get_trends_cooldown_remaining() -> float:
    return _trends_cooldown.remaining()


def get_trends_cooldown_snapshot() -> dict:
    remaining = _trends_cooldown.remaining()
    return {
        "blocked_until_wallclock": time.time() + remaining if remaining > 0 else 0.0,
    }


def restore_trends_cooldown_snapshot(snap: dict) -> None:
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


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


def _check_prerequisites(
    conn: DuckDBPyConnection, set_number: str,
) -> Result[tuple[str, int], ExecutorResult]:
    """Pure: validate that title and year_released exist."""
    from services.enrichment.config import is_placeholder_title

    item_row = conn.execute(
        "SELECT title, year_released FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if not item_row or not item_row[0] or not item_row[1]:
        return Err(ExecutorResult.fail(
            "Missing title or year_released",
            category=ErrorCategory.NOT_FOUND,
            permanent=True,
        ))

    title, year_released = item_row[0], int(item_row[1])
    if is_placeholder_title(title):
        return Err(ExecutorResult.fail(
            "Placeholder title",
            category=ErrorCategory.NOT_FOUND,
            permanent=True,
        ))
    return Ok((title, year_released))


def _check_freshness(conn: DuckDBPyConnection, set_number: str) -> Result[bool, ExecutorResult]:
    """IO: check if we already have fresh data. Returns Ok(True) if stale/missing."""
    from datetime import timedelta

    row = conn.execute(
        """SELECT scraped_at FROM google_trends_snapshots
           WHERE set_number = ?
           ORDER BY scraped_at DESC LIMIT 1""",
        [set_number],
    ).fetchone()
    if row and row[0]:
        from db.queries import is_fresh
        if is_fresh(row[0], timedelta(days=30)):
            return Err(ExecutorResult.ok())  # Already fresh -- early exit
    return Ok(True)


def _fetch(set_number: str, year_released: int) -> Result[object, ExecutorResult]:
    """IO: call the Google Trends API."""
    from services.google_trends.scraper import fetch_interest

    trends_result = fetch_interest(set_number, year_released=year_released)
    if not trends_result.success:
        if trends_result.rate_limited:
            _trends_cooldown.activate()
            return Err(ExecutorResult.cooldown(_trends_cooldown.DURATION_SECONDS))
        return Err(ExecutorResult.fail(
            trends_result.error or "Google Trends fetch failed",
            category=ErrorCategory.NETWORK,
        ))
    _trends_cooldown.clear()
    return Ok(trends_result.data)


def _persist(conn: DuckDBPyConnection, data: object) -> None:
    """IO: save the trends snapshot."""
    from services.google_trends.repository import save_trends_snapshot
    save_trends_snapshot(conn, data)


# ---------------------------------------------------------------------------
# Executor (composes the pipeline)
# ---------------------------------------------------------------------------


@executor(TaskType.GOOGLE_TRENDS, concurrency=1, timeout=180)
def execute_google_trends(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Fetch Google Trends interest data for a LEGO set."""
    # Check cooldown
    remaining = _trends_cooldown.remaining()
    if remaining > 0:
        return ExecutorResult.cooldown(remaining)

    # Pipeline: prerequisites -> freshness -> fetch -> persist
    prereq = _check_prerequisites(conn, set_number)
    if prereq.is_err():
        return prereq.unwrap_or_else(lambda e: e)

    freshness = _check_freshness(conn, set_number)
    if freshness.is_err():
        return freshness.unwrap_or_else(lambda e: e)

    _title, year_released = prereq.unwrap()

    fetch_result = _fetch(set_number, year_released)
    if fetch_result.is_err():
        return fetch_result.unwrap_or_else(lambda e: e)

    data = fetch_result.unwrap()
    _persist(conn, data)

    logger.info(
        "Google Trends for %s: %d pts, peak=%s",
        set_number,
        len(data.interest_over_time),
        data.peak_value,
    )
    return ExecutorResult.ok()
