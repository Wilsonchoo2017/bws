"""Image assets repository -- tracks downloaded BrickLink images."""

from __future__ import annotations

from typing import Any


from db.pg.writes import (
    _get_pg,
    pg_mark_image_downloaded,
    pg_mark_image_failed,
    pg_upsert_image_asset,
)


def get_asset(
    conn: Any, asset_type: str, item_id: str
) -> dict | None:
    """Get a single image asset by type and item_id."""
    row = conn.execute(
        "SELECT id, asset_type, item_id, source_url, local_path, "
        "file_size_bytes, content_type, downloaded_at, status, error, retry_count "
        "FROM image_assets WHERE asset_type = ? AND item_id = ?",
        [asset_type, item_id],
    ).fetchone()
    if not row:
        return None
    columns = [
        "id", "asset_type", "item_id", "source_url", "local_path",
        "file_size_bytes", "content_type", "downloaded_at", "status",
        "error", "retry_count",
    ]
    return dict(zip(columns, row))


def get_pending_assets(
    conn: Any, *, limit: int = 50
) -> list[dict]:
    """Get assets awaiting download (pending or failed with retries left)."""
    rows = conn.execute(
        "SELECT id, asset_type, item_id, source_url, local_path, retry_count "
        "FROM image_assets "
        "WHERE status IN ('pending', 'failed') AND retry_count < 3 "
        "ORDER BY status ASC, created_at ASC "
        "LIMIT ?",
        [limit],
    ).fetchall()
    columns = ["id", "asset_type", "item_id", "source_url", "local_path", "retry_count"]
    return [dict(zip(columns, row)) for row in rows]


def upsert_asset(
    conn: Any,
    asset_type: str,
    item_id: str,
    source_url: str,
    local_path: str,
) -> None:
    """Register an image asset for download. No-op if already exists."""
    conn.execute(
        """
        INSERT INTO image_assets (
            id, asset_type, item_id, source_url, local_path
        ) VALUES (
            nextval('image_assets_id_seq'), ?, ?, ?, ?
        )
        ON CONFLICT (asset_type, item_id) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            local_path = EXCLUDED.local_path
        """,
        [asset_type, item_id, source_url, local_path],
    )

    # Write to Postgres
    pg = _get_pg(conn)
    if pg is not None:
        pg_upsert_image_asset(
            pg,
            asset_type=asset_type,
            item_id=item_id,
            source_url=source_url,
            local_path=local_path,
        )


def mark_downloaded(
    conn: Any,
    asset_type: str,
    item_id: str,
    file_size_bytes: int,
    content_type: str = "image/png",
) -> None:
    """Mark an asset as successfully downloaded."""
    conn.execute(
        """
        UPDATE image_assets
        SET status = 'downloaded',
            file_size_bytes = ?,
            content_type = ?,
            downloaded_at = now(),
            error = NULL
        WHERE asset_type = ? AND item_id = ?
        """,
        [file_size_bytes, content_type, asset_type, item_id],
    )

    # Write to Postgres
    pg = _get_pg(conn)
    if pg is not None:
        pg_mark_image_downloaded(
            pg,
            asset_type=asset_type,
            item_id=item_id,
            status="downloaded",
            file_size_bytes=file_size_bytes,
            content_type=content_type,
            error=None,
        )


def mark_failed(
    conn: Any,
    asset_type: str,
    item_id: str,
    error: str,
) -> None:
    """Mark an asset download as failed and increment retry count."""
    conn.execute(
        """
        UPDATE image_assets
        SET status = 'failed',
            error = ?,
            retry_count = retry_count + 1
        WHERE asset_type = ? AND item_id = ?
        """,
        [error, asset_type, item_id],
    )

    # Write to Postgres
    pg = _get_pg(conn)
    if pg is not None:
        pg_mark_image_failed(
            pg,
            asset_type=asset_type,
            item_id=item_id,
            status="failed",
            error=error,
        )


def get_download_stats(conn: Any) -> dict:
    """Get image download statistics by status and type."""
    rows = conn.execute(
        "SELECT asset_type, status, COUNT(*) AS cnt, "
        "COALESCE(SUM(file_size_bytes), 0) AS total_bytes "
        "FROM image_assets GROUP BY asset_type, status"
    ).fetchall()

    stats: dict = {"by_type": {}, "totals": {"pending": 0, "downloaded": 0, "failed": 0, "total": 0, "total_bytes": 0}}
    for asset_type, status, cnt, total_bytes in rows:
        if asset_type not in stats["by_type"]:
            stats["by_type"][asset_type] = {"pending": 0, "downloaded": 0, "failed": 0, "total": 0}
        stats["by_type"][asset_type][status] = cnt
        stats["by_type"][asset_type]["total"] += cnt
        stats["totals"][status] = stats["totals"].get(status, 0) + cnt
        stats["totals"]["total"] += cnt
        stats["totals"]["total_bytes"] += total_bytes
    return stats


def register_existing_images(conn: Any) -> int:
    """Backfill image_assets from existing bricklink_items and minifigures.

    Returns the number of newly registered assets.
    """
    registered = 0

    # Register set images from bricklink_items
    rows = conn.execute(
        "SELECT item_id, image_url FROM bricklink_items "
        "WHERE image_url IS NOT NULL AND item_type = 'S'"
    ).fetchall()
    for item_id, image_url in rows:
        conn.execute(
            """
            INSERT INTO image_assets (id, asset_type, item_id, source_url, local_path)
            VALUES (nextval('image_assets_id_seq'), 'set', ?, ?, ?)
            ON CONFLICT (asset_type, item_id) DO NOTHING
            """,
            [item_id, image_url, f"sets/{item_id}.png"],
        )
        registered += 1

    # Register minifigure images
    rows = conn.execute(
        "SELECT minifig_id, image_url FROM minifigures "
        "WHERE image_url IS NOT NULL"
    ).fetchall()
    for minifig_id, image_url in rows:
        conn.execute(
            """
            INSERT INTO image_assets (id, asset_type, item_id, source_url, local_path)
            VALUES (nextval('image_assets_id_seq'), 'minifig', ?, ?, ?)
            ON CONFLICT (asset_type, item_id) DO NOTHING
            """,
            [minifig_id, image_url, f"minifigs/{minifig_id}.png"],
        )
        registered += 1

    # Register set images from lego_items (master catalog)
    rows = conn.execute(
        "SELECT set_number, image_url FROM lego_items "
        "WHERE image_url IS NOT NULL "
        "AND image_url LIKE '%img.bricklink.com%'"
    ).fetchall()
    for set_number, image_url in rows:
        # Derive item_id: lego_items uses set_number like "75192-1"
        conn.execute(
            """
            INSERT INTO image_assets (id, asset_type, item_id, source_url, local_path)
            VALUES (nextval('image_assets_id_seq'), 'set', ?, ?, ?)
            ON CONFLICT (asset_type, item_id) DO NOTHING
            """,
            [set_number, image_url, f"sets/{set_number}.png"],
        )
        registered += 1

    return registered
