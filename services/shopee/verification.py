"""Manual captcha verification service.

Launches a Camoufox browser (reusing the persistent profile so cookies /
fingerprint survive), navigates to the captured URL, and polls the page for
captcha clearance. The user physically solves the captcha in the browser
window; this service observes when it clears, updates the event row, and
re-enqueues any Shopee jobs that were blocked by this event.

Ntfy notifications are sent on:
    - verification started   (info)
    - verification success   (info, includes resumed job count)
    - verification failure   (max priority)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config.settings import SHOPEE_CONFIG
from db.connection import get_connection
from db.schema import init_schema
from services.notifications.ntfy import NtfyMessage, send_notification
from services.shopee.browser import human_delay, new_page, shopee_browser
from services.shopee.captcha_detection import (
    detect_captcha,
    save_snapshot,
    snapshot_relative_path,
)
from services.shopee.captcha_events import (
    STATUS_PENDING,
    STATUS_VERIFYING,
    get_event,
    mark_expired,
    mark_failed,
    mark_resolved,
    mark_verifying,
)

logger = logging.getLogger("bws.shopee.verification")

_POLL_INTERVAL_S = 2
_MIN_CLEAR_STREAK = 2  # require N consecutive clean polls before declaring resolved


@dataclass(frozen=True)
class VerificationResult:
    event_id: int
    status: str
    duration_s: int
    resumed_job_ids: tuple[str, ...] = ()
    message: str = ""


def _send_ntfy(
    title: str,
    message: str,
    *,
    priority: int,
    tags: tuple[str, ...],
) -> None:
    try:
        send_notification(
            NtfyMessage(
                title=title,
                message=message,
                priority=priority,
                tags=tags,
                topic="bws-alerts",
            )
        )
    except Exception:
        logger.exception("Failed to send ntfy notification: %s", title)


async def run_verification(
    event_id: int,
    *,
    timeout_s: int | None = None,
) -> VerificationResult:
    """Launch the browser and guide the user through solving the captcha.

    Steps:
        1. Load the event row; bail if it's not pending/verifying.
        2. Transition pending -> verifying (atomic).
        3. Launch Camoufox, navigate to the source_url.
        4. Poll detect_captcha every 2s; require 2 consecutive clean reads
           before declaring resolved.
        5. On success: snapshot, mark_resolved, re-enqueue blocked jobs, ntfy.
        6. On timeout: snapshot, mark_expired, ntfy failure.
    """
    timeout = timeout_s or SHOPEE_CONFIG.verify_timeout_s
    started_at = datetime.now(tz=timezone.utc)

    # Load + transition
    conn = get_connection()
    init_schema(conn)
    event = get_event(conn, event_id)
    if event is None:
        conn.close()
        raise ValueError(f"Captcha event #{event_id} not found")
    if event.status not in (STATUS_PENDING, STATUS_VERIFYING):
        conn.close()
        raise ValueError(
            f"Captcha event #{event_id} is {event.status}, cannot verify"
        )
    if event.status == STATUS_PENDING:
        mark_verifying(conn, event_id)
    conn.close()

    logger.info(
        "Starting verification for event #%s url=%s (timeout=%ds)",
        event_id, event.source_url, timeout,
    )
    _send_ntfy(
        "Shopee: verification started",
        f"Browser launched for event #{event_id}. "
        f"You have {timeout}s to solve the captcha at {event.source_url}.",
        priority=4,
        tags=("mag", "robot"),
    )

    # Launch browser
    try:
        async with shopee_browser() as browser:
            page = await new_page(browser)
            try:
                await page.goto(event.source_url, wait_until="domcontentloaded")
            except Exception:
                logger.warning(
                    "goto failed for %s; browser is live for manual navigation",
                    event.source_url,
                    exc_info=True,
                )

            # Poll loop
            deadline = asyncio.get_event_loop().time() + timeout
            clear_streak = 0
            last_reason = "unknown"
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(_POLL_INTERVAL_S)
                try:
                    signals = await detect_captcha(page)
                except Exception:
                    logger.debug("detect_captcha poll failed", exc_info=True)
                    continue
                last_reason = signals.reason
                if not signals.detected:
                    clear_streak += 1
                    if clear_streak >= _MIN_CLEAR_STREAK:
                        break
                else:
                    clear_streak = 0

            duration = int(
                (datetime.now(tz=timezone.utc) - started_at).total_seconds()
            )

            if clear_streak >= _MIN_CLEAR_STREAK:
                # SUCCESS — capture a post-verify snapshot for the record
                try:
                    post_snap = await save_snapshot(
                        page,
                        reason="verified",
                        signals=signals,
                        extra_meta={"event_id": event_id, "duration_s": duration},
                    )
                    logger.info("Post-verify snapshot saved to %s", post_snap)
                except Exception:
                    logger.debug("post-verify snapshot failed", exc_info=True)
                return _finish_success(event_id, duration)

            # TIMEOUT — capture a final snapshot so we can see what's stuck
            try:
                await save_snapshot(
                    page,
                    reason=f"verification_timeout:{last_reason}",
                    extra_meta={"event_id": event_id, "duration_s": duration},
                )
            except Exception:
                logger.debug("timeout snapshot failed", exc_info=True)
            return _finish_timeout(event_id, duration, last_reason)

    except Exception as e:
        duration = int(
            (datetime.now(tz=timezone.utc) - started_at).total_seconds()
        )
        logger.exception("Verification browser failure for event #%s", event_id)
        return _finish_failure(event_id, duration, str(e))


def _finish_success(event_id: int, duration: int) -> VerificationResult:
    from api.jobs import job_manager

    conn = get_connection()
    init_schema(conn)
    mark_resolved(conn, event_id, duration)
    conn.close()

    resumed = tuple(job_manager.requeue_blocked(event_id))
    logger.info(
        "Captcha event #%s resolved in %ds, resumed %d jobs",
        event_id, duration, len(resumed),
    )
    _send_ntfy(
        "Shopee: verified",
        f"Event #{event_id} cleared in {duration}s. "
        f"{len(resumed)} blocked jobs resumed.",
        priority=3,
        tags=("white_check_mark", "robot"),
    )
    return VerificationResult(
        event_id=event_id,
        status="resolved",
        duration_s=duration,
        resumed_job_ids=resumed,
        message=f"Resolved in {duration}s",
    )


def _finish_timeout(
    event_id: int, duration: int, last_reason: str,
) -> VerificationResult:
    conn = get_connection()
    init_schema(conn)
    mark_expired(
        conn, event_id,
        note=f"verify_timeout after {duration}s, last_signal={last_reason}",
    )
    conn.close()
    logger.error(
        "Captcha event #%s verification timed out after %ds (last=%s)",
        event_id, duration, last_reason,
    )
    _send_ntfy(
        "Shopee: verification failed",
        f"Event #{event_id} not cleared within {duration}s "
        f"(last signal: {last_reason}). Open Operations and retry.",
        priority=5,
        tags=("x", "robot"),
    )
    return VerificationResult(
        event_id=event_id,
        status="expired",
        duration_s=duration,
        message=f"Timed out after {duration}s",
    )


def _finish_failure(
    event_id: int, duration: int, error: str,
) -> VerificationResult:
    conn = get_connection()
    init_schema(conn)
    mark_failed(conn, event_id, note=f"browser_failure: {error}"[:500])
    conn.close()
    _send_ntfy(
        "Shopee: verification error",
        f"Event #{event_id} browser launch failed: {error[:200]}",
        priority=5,
        tags=("x", "robot"),
    )
    return VerificationResult(
        event_id=event_id,
        status="failed",
        duration_s=duration,
        message=f"Browser failure: {error[:200]}",
    )
