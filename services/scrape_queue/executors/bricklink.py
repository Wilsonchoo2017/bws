"""BrickLink metadata executor.

Tracks consecutive 0-field responses for silent ban detection.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.scrape_queue.models import ErrorCategory, ExecutorResult, TaskType
from services.scrape_queue.registry import executor

if TYPE_CHECKING:
    from services.enrichment.types import EnrichmentResult


logger = logging.getLogger("bws.scrape_queue.executor.bricklink")

_SNAPSHOT_DIR = Path("logs/bricklink_snapshots")
_MAX_SNAPSHOTS = 50


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


def _save_enrichment_snapshot(set_number: str, result: EnrichmentResult) -> None:
    """Save a JSON debug snapshot when enrichment returns 0 fields."""
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _SNAPSHOT_DIR / f"{ts}_{set_number}_enrich_0fields.json"

        field_details = []
        for fr in result.field_results:
            field_details.append({
                "field": fr.field.value if hasattr(fr.field, "value") else str(fr.field),
                "status": fr.status.value if hasattr(fr.status, "value") else str(fr.status),
                "value": str(fr.value) if fr.value is not None else None,
                "source": fr.source.value if fr.source is not None and hasattr(fr.source, "value") else None,
                "errors": list(fr.errors) if fr.errors else [],
            })

        snapshot = {
            "set_number": set_number,
            "timestamp": ts,
            "fields_found": result.fields_found,
            "fields_missing": result.fields_missing,
            "sources_called": [s.value for s in result.sources_called] if result.sources_called else [],
            "field_results": field_details,
        }
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        logger.info("Saved enrichment debug snapshot: %s", path)

        # Prune old JSON snapshots
        for old in sorted(_SNAPSHOT_DIR.glob("*.json"))[:-_MAX_SNAPSHOTS]:
            old.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Failed to save enrichment snapshot: %s", e)


def _bricklink_cooldown_remaining() -> float:
    from config.settings import BRICKLINK_RATE_LIMITER

    if BRICKLINK_RATE_LIMITER.is_in_maintenance():
        return BRICKLINK_RATE_LIMITER.maintenance_remaining()
    return BRICKLINK_RATE_LIMITER.cooldown_remaining()


@executor(
    TaskType.BRICKLINK_METADATA,
    concurrency=2,
    timeout=300,
    cooldown_check=_bricklink_cooldown_remaining,
)
def execute_bricklink_metadata(
    conn: Any,
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

    # Skip during daily maintenance window (1pm-2pm MYT)
    if BRICKLINK_RATE_LIMITER.is_in_maintenance():
        maint_remaining = BRICKLINK_RATE_LIMITER.maintenance_remaining()
        logger.info(
            "BrickLink maintenance window -- %d min remaining",
            int(maint_remaining / 60),
        )
        return ExecutorResult.cooldown(maint_remaining)

    remaining = BRICKLINK_RATE_LIMITER.cooldown_remaining()
    if remaining > 0:
        logger.info("BrickLink in cooldown -- %d min remaining", int(remaining / 60))
        return ExecutorResult.cooldown(remaining)

    item = get_item_detail(conn, set_number)
    if not item:
        return ExecutorResult.fail(
            f"Item {set_number} not found in lego_items",
            category=ErrorCategory.NOT_FOUND,
            permanent=True,
        )

    fetchers = {
        SourceId.BRICKLINK: lambda sn: fetch_from_bricklink(conn, sn),
    }

    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)

    # Classify the result to decide whether 0 fields is a ban signal.
    bricklink_was_called = SourceId.BRICKLINK in result.sources_called
    no_fields_to_enrich = len(result.field_results) == 0

    if result.fields_found == 0 and not bricklink_was_called and no_fields_to_enrich:
        # Item already has all metadata -- not a ban signal
        logger.info("BrickLink metadata for %s: already complete, nothing to enrich", set_number)
        _bl_ban_tracker.reset()
        return ExecutorResult.skip("Already enriched")

    if result.fields_found == 0 and not bricklink_was_called:
        # Missing fields exist but none are BrickLink-provided (e.g. year_retired,
        # release_date, retired_date are BrickEconomy-only).  Not a ban signal.
        missing = [fr.field.value for fr in result.field_results]
        logger.info(
            "BrickLink metadata for %s: skipped -- %d missing fields are not "
            "BrickLink-provided: %s",
            set_number, len(missing), missing,
        )
        _bl_ban_tracker.reset()
        return ExecutorResult.skip(
            "Missing fields not provided by BrickLink: %s" % missing,
        )

    if result.fields_found == 0 and bricklink_was_called:
        from services.enrichment.types import FieldStatus

        _save_enrichment_snapshot(set_number, result)

        # Classify per-field outcomes to decide if this looks like a ban.
        # NOT_FOUND = source succeeded but field has no value (legit, e.g. no minifigs)
        # FAILED with DB errors = infra issue, not a ban
        # FAILED with no BL source available = BE-only field, ignore
        bl_fields_not_found = sum(
            1 for fr in result.field_results
            if fr.status == FieldStatus.NOT_FOUND
        )
        bl_fields_failed_with_bl_error = sum(
            1 for fr in result.field_results
            if fr.status == FieldStatus.FAILED
            and any("bricklink" in err.lower() for err in fr.errors)
        )
        has_db_error = any(
            "duplicate key" in err or "constraint" in err
            for fr in result.field_results
            for err in fr.errors
        )

        if has_db_error:
            logger.warning(
                "BrickLink metadata for %s: 0 fields due to DB error, not a ban signal",
                set_number,
            )
            return ExecutorResult.fail(
                "DB error during enrichment (sources_called=%s)" % list(result.sources_called),
                category=ErrorCategory.DATA_MISSING,
            )

        if bl_fields_failed_with_bl_error == 0:
            # BrickLink was called and succeeded -- fields are just legitimately
            # absent (e.g. set has no minifigs).  Not a ban signal.
            logger.info(
                "BrickLink metadata for %s: scrape OK but %d fields not available "
                "(not a ban signal)",
                set_number, bl_fields_not_found,
            )
            _bl_ban_tracker.reset()
            return ExecutorResult.skip(
                "BrickLink scrape OK, %d fields not available on BrickLink"
                % bl_fields_not_found,
            )

        # Real BrickLink failures -- possible ban signal.
        if _bl_ban_tracker.record_zero():
            logger.warning(
                "Silent ban detected: %d consecutive 0-field responses "
                "-- tripping circuit breaker",
                _bl_ban_tracker.count,
            )
            BRICKLINK_RATE_LIMITER.trip_silent_ban()
            _bl_ban_tracker.reset()
            return ExecutorResult.cooldown(BRICKLINK_RATE_LIMITER.cooldown_remaining())
        return ExecutorResult.fail(
            "No data returned (0 fields, %d BL errors, sources_called=%s)"
            % (bl_fields_failed_with_bl_error, list(result.sources_called)),
            category=ErrorCategory.DATA_MISSING,
        )

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
