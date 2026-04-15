"""Repository helpers for shopee_captcha_events."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("bws.shopee.captcha_events")


@dataclass(frozen=True)
class CaptchaEvent:
    id: int
    job_id: str | None
    source_url: str
    snapshot_dir: str
    detection_reason: str
    detection_signals: dict[str, Any] | None
    detected_at: datetime


def _row_to_event(row: tuple) -> CaptchaEvent:
    signals_raw = row[5]
    if isinstance(signals_raw, str):
        try:
            signals = json.loads(signals_raw)
        except (json.JSONDecodeError, TypeError):
            signals = None
    else:
        signals = signals_raw
    return CaptchaEvent(
        id=row[0],
        job_id=row[1],
        source_url=row[2],
        snapshot_dir=row[3],
        detection_reason=row[4],
        detection_signals=signals,
        detected_at=row[6],
    )


_SELECT_COLS = (
    "id, job_id, source_url, snapshot_dir, detection_reason, detection_signals, "
    "detected_at"
)


def record_event(
    conn: Any,
    *,
    source_url: str,
    snapshot_dir: str,
    detection_reason: str,
    detection_signals: dict[str, Any] | None,
    job_id: str | None = None,
) -> int:
    """Insert a new captcha event row and return its id."""
    signals_json = json.dumps(detection_signals) if detection_signals else None
    row = conn.execute(
        f"""
        INSERT INTO shopee_captcha_events
            (job_id, source_url, snapshot_dir, detection_reason,
             detection_signals, detected_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id
        """,  # noqa: S608
        (
            job_id,
            source_url,
            snapshot_dir,
            detection_reason,
            signals_json,
            datetime.now(tz=timezone.utc),
        ),
    ).fetchone()
    event_id = int(row[0])
    logger.info(
        "Recorded captcha event id=%s reason=%s url=%s",
        event_id, detection_reason, source_url,
    )
    return event_id


def get_event(conn: Any, event_id: int) -> CaptchaEvent | None:
    row = conn.execute(
        f"SELECT {_SELECT_COLS} FROM shopee_captcha_events WHERE id = %s",  # noqa: S608
        (event_id,),
    ).fetchone()
    return _row_to_event(row) if row else None


def list_events(
    conn: Any,
    limit: int = 50,
) -> list[CaptchaEvent]:
    """List recent captcha events."""
    rows = conn.execute(
        f"""
        SELECT {_SELECT_COLS}
        FROM shopee_captcha_events
        ORDER BY detected_at DESC
        LIMIT %s
        """,  # noqa: S608
        (limit,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def has_recent_captcha(conn: Any, hours: int = 2) -> bool:
    """Check if a captcha was detected within the last N hours."""
    row = conn.execute(
        """
        SELECT 1 FROM shopee_captcha_events
        WHERE detected_at > NOW() - INTERVAL %s
        LIMIT 1
        """,
        (f"{hours} hours",),
    ).fetchone()
    return row is not None
