"""Gating logic for Shopee jobs based on captcha clearance.

The rule: Shopee-family jobs (shopee, shopee_saturation, shopee_competition)
may only run when a valid captcha clearance exists (granted within the last
24 hours and not invalidated by a mid-scrape captcha detection).

If no valid clearance exists, jobs are moved to BLOCKED_VERIFY status.
"""

from __future__ import annotations

import logging
from typing import Any

from db.connection import get_connection
from db.schema import init_schema
from services.shopee.captcha_clearance import (
    has_valid_clearance,
    invalidate_clearance,
)

logger = logging.getLogger("bws.shopee.captcha_gate")

SHOPEE_SCRAPER_PREFIX = "shopee"


def _shopee_scraper(scraper_id: str) -> bool:
    return scraper_id.startswith(SHOPEE_SCRAPER_PREFIX)


def should_gate_job(scraper_id: str) -> bool:
    """True if this scraper_id is Shopee-family AND no valid clearance exists."""
    if not _shopee_scraper(scraper_id):
        return False
    return not _check_clearance()


def _check_clearance() -> bool:
    """Return True if a valid clearance exists.

    Opens a short-lived connection.  Never raises -- on DB failure returns
    False so that jobs are gated (safe default).
    """
    try:
        conn = get_connection()
        try:
            init_schema(conn)
            return has_valid_clearance(conn)
        finally:
            conn.close()
    except Exception:
        logger.exception("Clearance check failed")
        return False


def invalidate_current_clearance(reason: str) -> None:
    """Invalidate the active clearance (e.g. captcha detected mid-scrape).

    Never raises -- logs on failure.
    """
    try:
        conn = get_connection()
        try:
            init_schema(conn)
            invalidate_clearance(conn, reason=reason)
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to invalidate clearance")


def latest_pending_event_id(conn: Any | None = None) -> int | None:
    """Return the most recent captcha event id, or None.

    Kept for backward compatibility with existing blocked jobs.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
        init_schema(conn)
    try:
        row = conn.execute(
            """
            SELECT id FROM shopee_captcha_events
            ORDER BY detected_at DESC
            LIMIT 1
            """
        ).fetchone()
        return int(row[0]) if row else None
    except Exception:
        logger.exception("latest_pending_event_id failed")
        return None
    finally:
        if own_conn and conn is not None:
            conn.close()
