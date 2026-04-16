"""Repository helpers for shopee_captcha_clearance.

Manages the 24-hour clearance window that gates all Shopee-family jobs.
Clearance is granted after the user proactively solves a captcha via the
dedicated browser session, and is invalidated if a captcha is detected
mid-scrape.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("bws.shopee.captcha_clearance")

CLEARANCE_HOURS = 24


@dataclass(frozen=True)
class ClearanceRecord:
    id: int
    cleared_at: datetime
    expires_at: datetime
    invalidated_at: datetime | None
    invalidated_reason: str | None
    method: str


def _row_to_record(row: tuple) -> ClearanceRecord:
    return ClearanceRecord(
        id=row[0],
        cleared_at=row[1],
        expires_at=row[2],
        invalidated_at=row[3],
        invalidated_reason=row[4],
        method=row[5],
    )


_SELECT_COLS = (
    "id, cleared_at, expires_at, invalidated_at, invalidated_reason, method"
)


def record_clearance(conn: Any, *, method: str = "proactive") -> int:
    """Insert a new clearance row. Returns the row id."""
    row = conn.execute(
        """
        INSERT INTO shopee_captcha_clearance
            (cleared_at, expires_at, method)
        VALUES (NOW(), NOW() + make_interval(hours => %s), %s)
        RETURNING id
        """,
        (CLEARANCE_HOURS, method),
    ).fetchone()
    clearance_id = int(row[0])
    logger.info(
        "Recorded captcha clearance id=%s method=%s (expires in %dh)",
        clearance_id, method, CLEARANCE_HOURS,
    )
    return clearance_id


def get_active_clearance(conn: Any) -> ClearanceRecord | None:
    """Return the latest valid clearance, or None."""
    row = conn.execute(
        f"""
        SELECT {_SELECT_COLS}
        FROM shopee_captcha_clearance
        WHERE invalidated_at IS NULL
          AND expires_at > NOW()
        ORDER BY cleared_at DESC
        LIMIT 1
        """,  # noqa: S608
    ).fetchone()
    return _row_to_record(row) if row else None


def invalidate_clearance(conn: Any, *, reason: str) -> bool:
    """Mark the active clearance as invalidated. Returns True if updated."""
    result = conn.execute(
        """
        UPDATE shopee_captcha_clearance
        SET invalidated_at = NOW(),
            invalidated_reason = %s
        WHERE invalidated_at IS NULL
          AND expires_at > NOW()
        """,
        (reason,),
    )
    updated = result.rowcount > 0
    if updated:
        logger.warning("Clearance invalidated: %s", reason)
    return updated


def has_valid_clearance(conn: Any) -> bool:
    """True if an unexpired, non-invalidated clearance exists."""
    return get_active_clearance(conn) is not None


def get_clearance_status(conn: Any) -> dict[str, Any]:
    """Return a status dict for the API."""
    record = get_active_clearance(conn)
    if record is None:
        return {"valid": False}
    now = datetime.now(tz=timezone.utc)
    remaining = (record.expires_at - now).total_seconds()
    return {
        "valid": True,
        "cleared_at": record.cleared_at.isoformat(),
        "expires_at": record.expires_at.isoformat(),
        "remaining_seconds": max(0, int(remaining)),
        "method": record.method,
    }
