"""Proactive captcha solving session.

Manages a browser session that navigates to Shopee and waits for the user
to solve any captcha challenge.  Once the page loads cleanly (no captcha
signals), a 24-hour clearance is recorded in the database.

Usage:
    state = await start_solve_session()
    # Poll get_solver_state() from the API until status is completed/failed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from db.connection import get_connection
from db.schema import init_schema
from services.shopee.browser import shopee_browser, new_page
from services.shopee.captcha_clearance import record_clearance
from services.shopee.captcha_detection import detect_captcha
from services.shopee.popups import dismiss_popups, setup_dialog_handler

logger = logging.getLogger("bws.shopee.captcha_solver")

SHOPEE_BASE = "https://shopee.com.my"
_MAX_WAIT_SECONDS = 300  # 5 minutes
_POLL_INTERVAL_SECONDS = 3


class SolverStatus(str, Enum):
    IDLE = "idle"
    LAUNCHING = "launching"
    WAITING_FOR_USER = "waiting_for_user"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SolverState:
    status: SolverStatus = SolverStatus.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    clearance_id: int | None = None
    captcha_detected: bool = False


# Module-level singleton
_state = SolverState()
_lock = asyncio.Lock()


def get_solver_state() -> SolverState:
    """Return a snapshot of the current solver state."""
    from dataclasses import replace
    return replace(_state)


def reset_solver_state() -> None:
    """Reset to idle for the next attempt."""
    global _state
    _state = SolverState()


def _is_running() -> bool:
    return _state.status in (
        SolverStatus.LAUNCHING,
        SolverStatus.WAITING_FOR_USER,
        SolverStatus.VERIFYING,
    )


async def start_solve_session() -> SolverState:
    """Launch a browser, navigate to Shopee, and wait for captcha resolution.

    The browser opens non-headless so the user can interact with the captcha.
    Polls detect_captcha() every few seconds; once signals clear, records
    clearance and closes the browser.

    Thread-safe via asyncio.Lock -- concurrent calls return immediately if
    a session is already running.
    """
    global _state

    async with _lock:
        if _is_running():
            return _state
        _state = SolverState(
            status=SolverStatus.LAUNCHING,
            started_at=datetime.now(tz=timezone.utc),
        )

    try:
        async with shopee_browser() as browser:
            page = await new_page(browser)
            setup_dialog_handler(page)

            _state.status = SolverStatus.LAUNCHING
            logger.info("Captcha solver: navigating to %s", SHOPEE_BASE)

            await page.goto(SHOPEE_BASE, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            # Dismiss any popups that appear on first load
            await dismiss_popups(page)

            # Check initial captcha state
            signals = await detect_captcha(page)

            if signals.detected:
                _state.status = SolverStatus.WAITING_FOR_USER
                _state.captcha_detected = True
                logger.info(
                    "Captcha solver: captcha detected (%s), waiting for user",
                    signals.reason,
                )

                # Poll until captcha disappears or timeout
                polls = _MAX_WAIT_SECONDS // _POLL_INTERVAL_SECONDS
                for _ in range(polls):
                    await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                    signals = await detect_captcha(page)
                    if not signals.detected:
                        break
                else:
                    _state.status = SolverStatus.FAILED
                    _state.error = (
                        f"Captcha not solved within {_MAX_WAIT_SECONDS}s"
                    )
                    logger.warning("Captcha solver: timeout")
                    return _state
            else:
                logger.info("Captcha solver: no captcha detected, granting clearance")

            # Captcha solved or never appeared -- record clearance
            _state.status = SolverStatus.VERIFYING
            conn = get_connection()
            try:
                init_schema(conn)
                clearance_id = record_clearance(conn, method="proactive")
            finally:
                conn.close()

            _state.clearance_id = clearance_id
            _state.status = SolverStatus.COMPLETED
            _state.completed_at = datetime.now(tz=timezone.utc)
            logger.info("Captcha solver: clearance granted (id=%s)", clearance_id)

    except Exception as exc:
        logger.exception("Captcha solver failed")
        _state.status = SolverStatus.FAILED
        _state.error = str(exc)

    return _state
