"""Gating logic for Shopee jobs when a manual captcha verification is pending.

The rule is simple: if any shopee_captcha_events row has status in
('pending', 'verifying'), no Shopee-family job (shopee, shopee_saturation,
shopee_competition) may start. Jobs that arrive are moved to BLOCKED_VERIFY
status. When the user successfully verifies an event, the blocked jobs are
re-enqueued.
"""

from __future__ import annotations

import logging
from typing import Any

from db.connection import get_connection
from db.schema import init_schema
from services.shopee.captcha_events import (
    count_pending,
    has_pending_events,
)

logger = logging.getLogger("bws.shopee.captcha_gate")

SHOPEE_SCRAPER_PREFIX = "shopee"


def _shopee_scraper(scraper_id: str) -> bool:
    return scraper_id.startswith(SHOPEE_SCRAPER_PREFIX)


def has_pending_verification() -> bool:
    """Return True if any Shopee captcha event is pending/verifying.

    Opens a short-lived connection. Never raises — on DB failure returns
    False so scraping can proceed rather than stalling everything.
    """
    try:
        conn = get_connection()
        init_schema(conn)
        result = has_pending_events(conn)
        conn.close()
        return result
    except Exception:
        logger.exception("has_pending_verification: DB check failed")
        return False


def pending_count() -> int:
    """Count of pending/verifying events. 0 on DB failure."""
    try:
        conn = get_connection()
        init_schema(conn)
        result = count_pending(conn)
        conn.close()
        return result
    except Exception:
        logger.exception("pending_count: DB check failed")
        return 0


def latest_pending_event_id(conn: Any | None = None) -> int | None:
    """Return the most recent pending/verifying event id, or None."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
        init_schema(conn)
    try:
        row = conn.execute(
            """
            SELECT id FROM shopee_captcha_events
            WHERE status IN ('pending', 'verifying')
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


def should_gate_job(scraper_id: str) -> bool:
    """True if this scraper_id is Shopee-family AND a verification is pending."""
    if not _shopee_scraper(scraper_id):
        return False
    return has_pending_verification()
