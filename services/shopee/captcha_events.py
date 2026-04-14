"""Repository helpers for shopee_captcha_events."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("bws.shopee.captcha_events")

STATUS_PENDING = "pending"
STATUS_VERIFYING = "verifying"
STATUS_RESOLVED = "resolved"
STATUS_EXPIRED = "expired"
STATUS_FAILED = "failed"

ACTIVE_STATUSES: tuple[str, ...] = (STATUS_PENDING, STATUS_VERIFYING)


@dataclass(frozen=True)
class CaptchaEvent:
    id: int
    job_id: str | None
    source_url: str
    snapshot_dir: str
    detection_reason: str
    detection_signals: dict[str, Any] | None
    status: str
    detected_at: datetime
    verified_at: datetime | None
    resolved_at: datetime | None
    resolution_duration_s: int | None
    notes: str | None


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
        status=row[6],
        detected_at=row[7],
        verified_at=row[8],
        resolved_at=row[9],
        resolution_duration_s=row[10],
        notes=row[11],
    )


_SELECT_COLS = (
    "id, job_id, source_url, snapshot_dir, detection_reason, detection_signals, "
    "status, detected_at, verified_at, resolved_at, resolution_duration_s, notes"
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
             detection_signals, status, detected_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id
        """,  # noqa: S608
        (
            job_id,
            source_url,
            snapshot_dir,
            detection_reason,
            signals_json,
            STATUS_PENDING,
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
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[CaptchaEvent]:
    if status:
        rows = conn.execute(
            f"""
            SELECT {_SELECT_COLS}
            FROM shopee_captcha_events
            WHERE status = %s
            ORDER BY detected_at DESC
            LIMIT %s
            """,  # noqa: S608
            (status, limit),
        ).fetchall()
    else:
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


def has_pending_events(conn: Any) -> bool:
    """Return True if any captcha event is currently pending or verifying."""
    row = conn.execute(
        "SELECT 1 FROM shopee_captcha_events "
        "WHERE status IN ('pending', 'verifying') LIMIT 1"
    ).fetchone()
    return row is not None


def count_pending(conn: Any) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM shopee_captcha_events "
        "WHERE status IN ('pending', 'verifying')"
    ).fetchone()
    return int(row[0]) if row else 0


def mark_verifying(conn: Any, event_id: int) -> bool:
    """Transition pending -> verifying. Returns False if not in pending state."""
    row = conn.execute(
        """
        UPDATE shopee_captcha_events
        SET status = 'verifying', verified_at = %s
        WHERE id = %s AND status = 'pending'
        RETURNING id
        """,
        (datetime.now(tz=timezone.utc), event_id),
    ).fetchone()
    return row is not None


def mark_resolved(conn: Any, event_id: int, duration_s: int) -> None:
    conn.execute(
        """
        UPDATE shopee_captcha_events
        SET status = 'resolved',
            resolved_at = %s,
            resolution_duration_s = %s
        WHERE id = %s
        """,
        (datetime.now(tz=timezone.utc), duration_s, event_id),
    )


def mark_expired(conn: Any, event_id: int, note: str | None = None) -> None:
    conn.execute(
        """
        UPDATE shopee_captcha_events
        SET status = 'expired',
            resolved_at = %s,
            notes = COALESCE(%s, notes)
        WHERE id = %s
        """,
        (datetime.now(tz=timezone.utc), note, event_id),
    )


def mark_failed(conn: Any, event_id: int, note: str) -> None:
    conn.execute(
        """
        UPDATE shopee_captcha_events
        SET status = 'failed',
            resolved_at = %s,
            notes = %s
        WHERE id = %s
        """,
        (datetime.now(tz=timezone.utc), note, event_id),
    )
