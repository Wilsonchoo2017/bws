"""BrickRanker repository functions for database operations.

Pure functions for CRUD operations on BrickRanker data in DuckDB.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from db.queries import parse_timestamp
from services.brickranker.parser import RetirementItem
from services.items.repository import get_or_create_item


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


_UTC = UTC


def _row_to_dict(row: tuple) -> dict:
    """Convert database row to dict."""
    return {
        "id": row[0],
        "set_number": row[1],
        "set_name": row[2],
        "year_released": row[3],
        "retiring_soon": bool(row[4]) if row[4] is not None else False,
        "expected_retirement_date": row[5],
        "theme": row[6],
        "image_url": row[7],
        "is_active": bool(row[8]) if row[8] is not None else True,
        "scraped_at": parse_timestamp(row[9]),
        "created_at": parse_timestamp(row[10]),
    }


def get_item(conn: "DuckDBPyConnection", set_number: str) -> dict | None:
    """Get a BrickRanker item by set_number.

    Args:
        conn: DuckDB connection
        set_number: LEGO set number (e.g., "75192")

    Returns:
        Dict with item data or None if not found
    """
    result = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, retiring_soon,
               expected_retirement_date, theme, image_url, is_active,
               scraped_at, created_at
        FROM brickranker_items
        WHERE set_number = ?
        """,
        [set_number],
    ).fetchone()

    return _row_to_dict(result) if result else None


def upsert_item(conn: "DuckDBPyConnection", item: RetirementItem) -> int:
    """Insert or update a BrickRanker item.

    Args:
        conn: DuckDB connection
        item: RetirementItem from parsing

    Returns:
        ID of the inserted/updated item
    """
    now = datetime.now(tz=_UTC).isoformat()
    existing = get_item(conn, item.set_number)

    if existing:
        conn.execute(
            """
            UPDATE brickranker_items
            SET set_name = ?,
                year_released = ?,
                retiring_soon = ?,
                expected_retirement_date = ?,
                theme = ?,
                image_url = ?,
                is_active = TRUE,
                scraped_at = ?
            WHERE set_number = ?
            """,
            [
                item.set_name,
                item.year_released,
                item.retiring_soon,
                item.expected_retirement_date,
                item.theme,
                item.image_url,
                now,
                item.set_number,
            ],
        )
        item_id = existing["id"]
    else:
        conn.execute(
            """
            INSERT INTO brickranker_items (
                id, set_number, set_name, year_released, retiring_soon,
                expected_retirement_date, theme, image_url, is_active,
                scraped_at, created_at
            ) VALUES (nextval('brickranker_items_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.set_number,
                item.set_name,
                item.year_released,
                item.retiring_soon,
                item.expected_retirement_date,
                item.theme,
                item.image_url,
                True,
                now,
                now,
            ],
        )

        row = conn.execute(
            "SELECT id FROM brickranker_items WHERE set_number = ?",
            [item.set_number],
        ).fetchone()
        item_id = row[0] if row else 0

    # Write to unified lego_items (metadata only, no prices)
    get_or_create_item(
        conn,
        item.set_number,
        title=item.set_name,
        theme=item.theme,
        year_released=item.year_released,
        image_url=item.image_url,
        retiring_soon=item.retiring_soon,
    )

    return item_id


def batch_upsert_items(
    conn: "DuckDBPyConnection",
    items: list[RetirementItem],
) -> dict[str, int]:
    """Batch upsert BrickRanker items.

    Also marks items not in the list as inactive.

    Args:
        conn: DuckDB connection
        items: List of RetirementItem objects

    Returns:
        Dict with created, updated, and total counts
    """
    created = 0
    updated = 0

    # Get existing items to determine created vs updated
    existing_set_numbers = {
        row[0] for row in conn.execute("SELECT set_number FROM brickranker_items").fetchall()
    }

    # Upsert each item
    for item in items:
        if item.set_number in existing_set_numbers:
            updated += 1
        else:
            created += 1
        upsert_item(conn, item)

    # Mark items not in the list as inactive
    active_set_numbers = {item.set_number for item in items}
    inactive_set_numbers = existing_set_numbers - active_set_numbers

    if inactive_set_numbers:
        now = datetime.now(tz=_UTC).isoformat()
        placeholders = ",".join("?" * len(inactive_set_numbers))
        conn.execute(
            f"UPDATE brickranker_items SET is_active = FALSE, scraped_at = ? WHERE set_number IN ({placeholders})",  # noqa: S608
            [now, *inactive_set_numbers],
        )

    return {
        "created": created,
        "updated": updated,
        "total": len(items),
    }


def list_items(
    conn: "DuckDBPyConnection",
    active_only: bool = True,
    limit: int = 100,
) -> list[dict]:
    """List BrickRanker items.

    Args:
        conn: DuckDB connection
        active_only: Only return active items
        limit: Maximum number of items to return

    Returns:
        List of item dicts
    """
    query = """
        SELECT id, set_number, set_name, year_released, retiring_soon,
               expected_retirement_date, theme, image_url, is_active,
               scraped_at, created_at
        FROM brickranker_items
    """
    params: list = []

    if active_only:
        query += " WHERE is_active = TRUE"

    query += " ORDER BY retiring_soon DESC, theme, set_number LIMIT ?"
    params.append(limit)

    results = conn.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in results]


def get_retiring_soon_items(
    conn: "DuckDBPyConnection",
    limit: int = 50,
) -> list[dict]:
    """Get items marked as retiring soon.

    Args:
        conn: DuckDB connection
        limit: Maximum number of items to return

    Returns:
        List of item dicts marked as retiring soon
    """
    results = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, retiring_soon,
               expected_retirement_date, theme, image_url, is_active,
               scraped_at, created_at
        FROM brickranker_items
        WHERE retiring_soon = TRUE AND is_active = TRUE
        ORDER BY expected_retirement_date, theme, set_number
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    return [_row_to_dict(row) for row in results]


def get_items_by_theme(
    conn: "DuckDBPyConnection",
    theme: str,
    limit: int = 100,
) -> list[dict]:
    """Get items by theme.

    Args:
        conn: DuckDB connection
        theme: Theme name
        limit: Maximum number of items to return

    Returns:
        List of item dicts for the theme
    """
    results = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, retiring_soon,
               expected_retirement_date, theme, image_url, is_active,
               scraped_at, created_at
        FROM brickranker_items
        WHERE theme = ? AND is_active = TRUE
        ORDER BY retiring_soon DESC, set_number
        LIMIT ?
        """,
        [theme, limit],
    ).fetchall()

    return [_row_to_dict(row) for row in results]


def count_items(conn: "DuckDBPyConnection") -> dict[str, int]:
    """Get statistics about BrickRanker items.

    Args:
        conn: DuckDB connection

    Returns:
        Dict with count statistics
    """
    total = conn.execute("SELECT COUNT(*) FROM brickranker_items").fetchone()
    active = conn.execute(
        "SELECT COUNT(*) FROM brickranker_items WHERE is_active = TRUE"
    ).fetchone()
    retiring_soon = conn.execute(
        "SELECT COUNT(*) FROM brickranker_items WHERE retiring_soon = TRUE AND is_active = TRUE"
    ).fetchone()

    return {
        "total": total[0] if total else 0,
        "active": active[0] if active else 0,
        "retiring_soon": retiring_soon[0] if retiring_soon else 0,
    }
