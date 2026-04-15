"""Retention / pruning for Shopee captcha snapshots.

Resolved or expired snapshots older than the retention window are deleted
from disk. Pending snapshots are NEVER pruned — they're load-bearing for
the UI and only disappear once the user verifies or fails them.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone

from config.settings import SHOPEE_CONFIG
from db.connection import get_connection
from db.schema import init_schema
from services.shopee.captcha_detection import SNAPSHOT_DIR

logger = logging.getLogger("bws.shopee.retention")


def prune_old_snapshots(*, retention_days: int | None = None) -> int:
    """Delete snapshot dirs for resolved/expired events older than N days.

    Returns the number of directories removed.
    """
    days = retention_days or SHOPEE_CONFIG.snapshot_retention_days
    if days <= 0:
        logger.info("Snapshot retention disabled (retention_days=%d)", days)
        return 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    logger.info(
        "Pruning resolved/expired snapshots older than %s (%d days)",
        cutoff.isoformat(), days,
    )

    try:
        conn = get_connection()
        init_schema(conn)
    except Exception:
        logger.exception("prune_old_snapshots: DB connect failed")
        return 0

    try:
        rows = conn.execute(
            """
            SELECT id, snapshot_dir
            FROM shopee_captcha_events
            WHERE status IN ('resolved', 'expired', 'failed')
              AND COALESCE(resolved_at, detected_at) < %s
            """,
            (cutoff,),
        ).fetchall()
    except Exception:
        logger.exception("prune_old_snapshots: query failed")
        conn.close()
        return 0

    removed = 0
    for event_id, snap_rel in rows:
        if not snap_rel:
            continue
        snap_path = (SNAPSHOT_DIR / snap_rel).resolve()
        try:
            snap_path.relative_to(SNAPSHOT_DIR.resolve())
        except ValueError:
            logger.warning(
                "Skipping event %s: snapshot path %s escapes SNAPSHOT_DIR",
                event_id, snap_path,
            )
            continue
        if not snap_path.exists():
            continue
        try:
            shutil.rmtree(snap_path)
            removed += 1
            logger.debug("Pruned snapshot dir %s (event %s)", snap_path, event_id)
        except Exception:
            logger.exception("Failed to remove snapshot dir %s", snap_path)

    conn.close()
    logger.info("Pruned %d captcha snapshot directories", removed)
    return removed
