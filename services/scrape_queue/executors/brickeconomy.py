"""BrickEconomy executor -- browser-based, uses PersistentBrowser."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from services.scrape_queue.models import ErrorCategory, ExecutorResult, TaskType
from services.scrape_queue.registry import executor
from typing import Any


logger = logging.getLogger("bws.scrape_queue.executor.brickeconomy")


# ---------------------------------------------------------------------------
# Explicit context replaces ``nonlocal scrape_was_data_miss``
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FetchContext:
    """Tracks state across the fetch/enrich pipeline without mutation."""

    data_miss: bool = False
    scrape_ok: bool = False
    last_error: str | None = None


def _brickeconomy_cooldown_remaining() -> float:
    from config.settings import BRICKECONOMY_RATE_LIMITER

    return BRICKECONOMY_RATE_LIMITER.cooldown_remaining()


def _trace_missing_item(conn: Any, set_number: str) -> str:
    # When an executor sees a task for a set that is not in lego_items, the
    # upstream producer either (a) enqueued a set it never inserted, or (b) the
    # item was deleted after enqueue (e.g. excluded-packaging cleanup in this
    # same executor). Peek at related tables so ops rows explain which it was.
    traces: list[str] = []
    probes = (
        ("bricklink_items", "set_number"),
        ("brickeconomy_snapshots", "set_number"),
        ("keepa_snapshots", "set_number"),
    )
    for table, col in probes:
        try:
            row = conn.execute(
                f"SELECT 1 FROM {table} WHERE {col} = ? LIMIT 1",  # noqa: S608
                [set_number],
            ).fetchone()
        except Exception:
            continue
        if row:
            traces.append(f"seen in {table}")
    if not traces:
        return "never seen in any source table -- upstream enqueue bug"
    return "; ".join(traces) + " -- likely deleted post-enqueue"


@executor(
    TaskType.BRICKECONOMY,
    concurrency=3,
    timeout=300,
    browser_profile="brickeconomy-profile",
    cooldown_check=_brickeconomy_cooldown_remaining,
)
def execute_brickeconomy(
    conn: Any,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickEconomy and store enrichment fields + snapshot."""
    from config.settings import BRICKECONOMY_CONFIG
    from services.brickeconomy.scraper import scrape_with_search
    from services.browser import BrowserConfig, get_persistent_browser
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.source_adapter import adapt_brickeconomy, make_failed_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    item = get_item_detail(conn, set_number)
    if not item:
        trace = _trace_missing_item(conn, set_number)
        logger.warning(
            "BrickEconomy task for %s: item not in lego_items (%s) -- permanent fail",
            set_number, trace,
        )
        return ExecutorResult.fail(
            f"Item {set_number} not found in lego_items ({trace})",
            category=ErrorCategory.NOT_FOUND,
            permanent=True,
        )

    browser = get_persistent_browser(BrowserConfig(
        profile_name=f"brickeconomy-{worker_index}",
        headless=BRICKECONOMY_CONFIG.headless,
        locale=BRICKECONOMY_CONFIG.locale,
    ))

    # Mutable container for fetch context -- avoids nonlocal mutation.
    # The list holds exactly one _FetchContext that gets replaced (not mutated).
    ctx_holder: list[_FetchContext] = [_FetchContext(), _FetchContext()]  # [ctx, _timeout_marker]

    def _fetch_be(sn: str):
        from services.brickeconomy.parser import is_excluded_packaging
        from services.brickeconomy.repository import record_current_value, save_snapshot
        from services.items.repository import delete_item

        try:
            scrape_result = browser.run(scrape_with_search, sn, timeout=120)
        except TimeoutError:
            error_msg = f"Browser timed out for {sn} after 120s"
            logger.warning(
                "BrickEconomy browser timed out for %s (120s) -- marking permanent fail",
                sn,
            )
            ctx_holder[0] = _FetchContext(last_error=error_msg)
            ctx_holder[1] = _FetchContext(last_error="TIMEOUT")  # signal permanent
            browser.restart()
            return make_failed_result(SourceId.BRICKECONOMY, error_msg)
        except Exception as exc:
            error_msg = f"Browser error for {sn}: {exc}"
            logger.warning("BrickEconomy unexpected error for %s: %s", sn, exc)
            ctx_holder[0] = _FetchContext(last_error=error_msg)
            browser.restart()
            return make_failed_result(SourceId.BRICKECONOMY, error_msg)

        if not scrape_result.success:
            error_msg = scrape_result.error or "Unknown error"
            ctx_holder[0] = _FetchContext(
                data_miss=scrape_result.not_found,
                last_error=error_msg,
            )
            return make_failed_result(SourceId.BRICKECONOMY, error_msg)
        if scrape_result.snapshot is None:
            ctx_holder[0] = _FetchContext(last_error="Scrape succeeded but snapshot is None")
            return make_failed_result(SourceId.BRICKECONOMY, "No data returned")

        # Track that scrape succeeded so we can report a useful error if
        # enrichment later finds 0 fields (instead of "unknown").
        snap = scrape_result.snapshot
        ctx_holder[0] = _FetchContext(
            scrape_ok=True,
            last_error=(
                f"Scrape OK but metadata empty "
                f"(title={snap.title!r}, theme={snap.theme!r}, "
                f"year={snap.year_released}, pieces={snap.pieces})"
            ),
        )

        # Delete non-standard packaging sets (foil packs, polybags, etc.)
        if is_excluded_packaging(scrape_result.snapshot.packaging):
            delete_item(conn, sn)
            return make_failed_result(
                SourceId.BRICKECONOMY,
                f"Excluded packaging '{scrape_result.snapshot.packaging}' -- item deleted",
            )

        save_snapshot(conn, scrape_result.snapshot)
        record_current_value(conn, scrape_result.snapshot)
        return adapt_brickeconomy(scrape_result.snapshot)

    fetchers = {SourceId.BRICKECONOMY: _fetch_be}
    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)

    if result.fields_found == 0 and result.field_results:
        if ctx_holder[0].data_miss:
            logger.info("BrickEconomy for %s: not found, skipping", set_number)
            return ExecutorResult.skip("Not found on BrickEconomy")
        if ctx_holder[0].scrape_ok:
            # Scrape succeeded and snapshot/value saved, but the remaining
            # missing fields (e.g. year_retired, retired_date) are genuinely
            # unavailable from the source.  This is normal for current sets.
            missing_names = [
                fr.field.value for fr in result.field_results
                if fr.status.value != "found"
            ]
            logger.info(
                "BrickEconomy for %s: snapshot saved, %d missing fields "
                "unavailable from source: %s",
                set_number, len(missing_names), ", ".join(missing_names[:5]),
            )
            return ExecutorResult.ok()
        # Log field-level detail for diagnosis
        failed_fields = [
            f"{fr.field.value}={fr.status.value}"
            for fr in result.field_results
            if fr.status.value != "found"
        ]
        error_detail = ctx_holder[0].last_error or "unknown"
        timed_out = ctx_holder[1].last_error == "TIMEOUT"
        logger.warning(
            "BrickEconomy for %s: 0 fields -- %s (fields: %s)%s",
            set_number, error_detail, ", ".join(failed_fields[:5]),
            " -- permanent fail (timeout)" if timed_out else " -- restarting browser",
        )
        browser.restart()
        return ExecutorResult.fail(
            f"BrickEconomy returned no data (0 fields): {error_detail}",
            category=ErrorCategory.TIMEOUT if timed_out else ErrorCategory.BROWSER_CRASH,
            permanent=timed_out,
        )
    elif not result.field_results:
        logger.info(
            "BrickEconomy for %s: all fields already populated, snapshot saved",
            set_number,
        )

    store_enrichment_result(conn, result)

    logger.info(
        "BrickEconomy for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return ExecutorResult.ok()
