"""BrickLink metadata executor.

Tracks consecutive 0-field responses for silent ban detection.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from services.scrape_queue.models import ExecutorResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor.bricklink")


# ---------------------------------------------------------------------------
# Silent ban tracker
# ---------------------------------------------------------------------------


class _BrickLinkBanTracker:
    """Thread-safe tracker for consecutive 0-field BrickLink responses.

    Triggers a "silent ban" cooldown after N consecutive zero-field results,
    indicating BrickLink is serving empty pages without an explicit 429.
    """

    THRESHOLD = 5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consecutive_zeros = 0

    def record_zero(self) -> bool:
        """Record a 0-field response. Returns True if threshold hit."""
        with self._lock:
            self._consecutive_zeros += 1
            return self._consecutive_zeros >= self.THRESHOLD

    def reset(self) -> None:
        with self._lock:
            self._consecutive_zeros = 0

    @property
    def count(self) -> int:
        with self._lock:
            return self._consecutive_zeros


_bl_ban_tracker = _BrickLinkBanTracker()


def execute_bricklink_metadata(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickLink catalog page and store enrichment fields."""
    from config.settings import BRICKLINK_RATE_LIMITER
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.fetchers import fetch_from_bricklink
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    remaining = BRICKLINK_RATE_LIMITER.cooldown_remaining()
    if remaining > 0:
        logger.info("BrickLink in cooldown -- %d min remaining", int(remaining / 60))
        return ExecutorResult.cooldown(remaining)

    item = get_item_detail(conn, set_number)
    if not item:
        return ExecutorResult.fail(f"Item {set_number} not found in lego_items")

    fetchers = {
        SourceId.BRICKLINK: lambda sn: fetch_from_bricklink(conn, sn),
    }

    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)

    if result.fields_found == 0:
        if _bl_ban_tracker.record_zero():
            logger.warning(
                "Silent ban detected: %d consecutive 0-field responses "
                "-- tripping circuit breaker",
                _bl_ban_tracker.count,
            )
            BRICKLINK_RATE_LIMITER.trip_silent_ban()
            _bl_ban_tracker.reset()
            return ExecutorResult.cooldown(BRICKLINK_RATE_LIMITER.cooldown_remaining())
        return ExecutorResult.fail("No data returned (0 fields)")

    _bl_ban_tracker.reset()
    BRICKLINK_RATE_LIMITER.record_success()
    store_enrichment_result(conn, result)

    logger.info(
        "BrickLink metadata for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return ExecutorResult.ok()
