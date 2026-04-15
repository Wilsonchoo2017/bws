"""Gating logic for Shopee jobs when a recent captcha has been detected.

The rule is simple: if a captcha event was detected within the last 2 hours,
no Shopee-family job (shopee, shopee_saturation, shopee_competition) may start.
Jobs that arrive are moved to BLOCKED_VERIFY status. After 2 hours with no new
captcha, jobs automatically resume.
"""

from __future__ import annotations

import logging
from typing import Any

from db.connection import get_connection
from db.schema import init_schema
from services.shopee.captcha_events import has_recent_captcha

logger = logging.getLogger("bws.shopee.captcha_gate")

SHOPEE_SCRAPER_PREFIX = "shopee"
CAPTCHA_GATE_HOURS = 2


def _shopee_scraper(scraper_id: str) -> bool:
    return scraper_id.startswith(SHOPEE_SCRAPER_PREFIX)


def has_pending_captcha() -> bool:
    """Return True if a captcha was detected within the last 2 hours.

    Opens a short-lived connection. Never raises — on DB failure returns
    False so scraping can proceed rather than stalling everything.
    """
    try:
        conn = get_connection()
        init_schema(conn)
        result = has_recent_captcha(conn, hours=CAPTCHA_GATE_HOURS)
        conn.close()
        return result
    except Exception:
        logger.exception("has_pending_captcha: DB check failed")
        return False


def latest_pending_event_id(conn: Any | None = None) -> int | None:
    """Return the most recent captcha event id, or None."""
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


def should_gate_job(scraper_id: str) -> bool:
    """True if this scraper_id is Shopee-family AND a captcha was detected recently."""
    if not _shopee_scraper(scraper_id):
        return False
    return has_pending_captcha()
