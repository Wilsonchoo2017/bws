"""WorldBricks repository functions for database operations.

Pure functions for CRUD operations on WorldBricks data in DuckDB.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from db.queries import get_next_id, parse_timestamp
from services.worldbricks.parser import WorldBricksData


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
        "year_retired": row[4],
        "parts_count": row[5],
        "dimensions": row[6],
        "image_url": row[7],
        "scraped_at": parse_timestamp(row[8]),
        "created_at": parse_timestamp(row[9]),
    }


def get_set(conn: "DuckDBPyConnection", set_number: str) -> dict | None:
    """Get a WorldBricks set by set_number.

    Args:
        conn: DuckDB connection
        set_number: LEGO set number (e.g., "75192")

    Returns:
        Dict with set data or None if not found
    """
    result = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, year_retired,
               parts_count, dimensions, image_url, scraped_at, created_at
        FROM worldbricks_sets
        WHERE set_number = ?
        """,
        [set_number],
    ).fetchone()

    return _row_to_dict(result) if result else None


def upsert_set(conn: "DuckDBPyConnection", data: WorldBricksData) -> int:
    """Insert or update a WorldBricks set.

    Args:
        conn: DuckDB connection
        data: WorldBricksData from scraping

    Returns:
        ID of the inserted/updated set
    """
    now = datetime.now(tz=_UTC).isoformat()
    existing = get_set(conn, data.set_number)

    if existing:
        conn.execute(
            """
            UPDATE worldbricks_sets
            SET set_name = ?,
                year_released = ?,
                year_retired = ?,
                parts_count = ?,
                dimensions = ?,
                image_url = ?,
                scraped_at = ?
            WHERE set_number = ?
            """,
            [
                data.set_name,
                data.year_released,
                data.year_retired,
                data.parts_count,
                data.dimensions,
                data.image_url,
                now,
                data.set_number,
            ],
        )
        return existing["id"]

    set_id = get_next_id(conn, "worldbricks_sets_id_seq")
    conn.execute(
        """
        INSERT INTO worldbricks_sets (
            id, set_number, set_name, year_released, year_retired,
            parts_count, dimensions, image_url, scraped_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            set_id,
            data.set_number,
            data.set_name,
            data.year_released,
            data.year_retired,
            data.parts_count,
            data.dimensions,
            data.image_url,
            now,
            now,
        ],
    )

    return set_id


def list_sets(
    conn: "DuckDBPyConnection",
    limit: int = 100,
) -> list[dict]:
    """List WorldBricks sets.

    Args:
        conn: DuckDB connection
        limit: Maximum number of sets to return

    Returns:
        List of set dicts
    """
    results = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, year_retired,
               parts_count, dimensions, image_url, scraped_at, created_at
        FROM worldbricks_sets
        ORDER BY scraped_at DESC NULLS LAST
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    return [_row_to_dict(row) for row in results]


def get_sets_needing_scraping(
    conn: "DuckDBPyConnection",
    max_age_days: int = 90,
    limit: int = 50,
) -> list[dict]:
    """Get sets that need re-scraping based on age.

    Args:
        conn: DuckDB connection
        max_age_days: Maximum age in days before re-scrape
        limit: Maximum number of sets to return

    Returns:
        List of set dicts needing scraping
    """
    cutoff = (datetime.now(tz=_UTC) - timedelta(days=max_age_days)).isoformat()

    results = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, year_retired,
               parts_count, dimensions, image_url, scraped_at, created_at
        FROM worldbricks_sets
        WHERE scraped_at IS NULL OR scraped_at < ?
        ORDER BY scraped_at ASC NULLS FIRST
        LIMIT ?
        """,
        [cutoff, limit],
    ).fetchall()

    return [_row_to_dict(row) for row in results]


def get_sets_missing_year_released(
    conn: "DuckDBPyConnection",
    limit: int = 50,
) -> list[dict]:
    """Get sets missing year_released data.

    Args:
        conn: DuckDB connection
        limit: Maximum number of sets to return

    Returns:
        List of set dicts missing year_released
    """
    results = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, year_retired,
               parts_count, dimensions, image_url, scraped_at, created_at
        FROM worldbricks_sets
        WHERE year_released IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    return [_row_to_dict(row) for row in results]


def get_sets_missing_year_retired(
    conn: "DuckDBPyConnection",
    limit: int = 50,
) -> list[dict]:
    """Get sets missing year_retired data.

    Args:
        conn: DuckDB connection
        limit: Maximum number of sets to return

    Returns:
        List of set dicts missing year_retired
    """
    results = conn.execute(
        """
        SELECT id, set_number, set_name, year_released, year_retired,
               parts_count, dimensions, image_url, scraped_at, created_at
        FROM worldbricks_sets
        WHERE year_retired IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    return [_row_to_dict(row) for row in results]


def delete_set(conn: "DuckDBPyConnection", set_number: str) -> bool:
    """Delete a WorldBricks set.

    Args:
        conn: DuckDB connection
        set_number: LEGO set number

    Returns:
        True if set was deleted
    """
    result = conn.execute(
        "DELETE FROM worldbricks_sets WHERE set_number = ?",
        [set_number],
    )
    return result.rowcount > 0 if hasattr(result, "rowcount") else True


def count_sets(conn: "DuckDBPyConnection") -> dict[str, int]:
    """Get statistics about WorldBricks sets.

    Args:
        conn: DuckDB connection

    Returns:
        Dict with count statistics
    """
    total = conn.execute("SELECT COUNT(*) FROM worldbricks_sets").fetchone()
    with_year_released = conn.execute(
        "SELECT COUNT(*) FROM worldbricks_sets WHERE year_released IS NOT NULL"
    ).fetchone()
    with_year_retired = conn.execute(
        "SELECT COUNT(*) FROM worldbricks_sets WHERE year_retired IS NOT NULL"
    ).fetchone()
    with_parts_count = conn.execute(
        "SELECT COUNT(*) FROM worldbricks_sets WHERE parts_count IS NOT NULL"
    ).fetchone()

    return {
        "total": total[0] if total else 0,
        "with_year_released": with_year_released[0] if with_year_released else 0,
        "with_year_retired": with_year_retired[0] if with_year_retired else 0,
        "with_parts_count": with_parts_count[0] if with_parts_count else 0,
    }
