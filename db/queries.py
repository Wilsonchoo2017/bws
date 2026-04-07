"""Common database query functions for BWS."""

from datetime import datetime, timedelta, timezone
from typing import Any


def get_next_id(conn: Any, sequence_name: str) -> int:
    """Get the next ID from a sequence."""
    result = conn.execute(f"SELECT nextval('{sequence_name}')").fetchone()
    if result is None:
        msg = f"Failed to get next ID from sequence {sequence_name}"
        raise RuntimeError(msg)
    return int(result[0])


def format_timestamp(dt: datetime | None) -> str | None:
    """Format a datetime as ISO string."""
    return dt.isoformat() if dt else None


def row_to_dict(conn: Any, row: tuple) -> dict:
    """Convert a single row to a dict using cursor column names."""
    columns = [desc[0] for desc in conn.description]
    return dict(zip(columns, row))


def rows_to_dicts(conn: Any, rows: list[tuple]) -> list[dict]:
    """Convert multiple rows to a list of dicts."""
    columns = [desc[0] for desc in conn.description]
    return [dict(zip(columns, row)) for row in rows]


def get_latest_row(
    conn: Any,
    table: str,
    *,
    key_column: str = "set_number",
    key_value: str,
    order_by: str = "scraped_at",
    columns: str = "*",
) -> dict | None:
    """Fetch the most recent row from a table by a key column.

    Common pattern used across snapshot repositories: select latest row
    ordered by a timestamp column descending.
    """
    # Table and column names are developer-controlled constants, not user input.
    sql = f"""
        SELECT {columns} FROM {table}
        WHERE {key_column} = ?
        ORDER BY {order_by} DESC
        LIMIT 1
    """  # noqa: S608
    row = conn.execute(sql, [key_value]).fetchone()
    if not row:
        return None
    return row_to_dict(conn, row)


def is_fresh(
    scraped_at: str | datetime | None,
    freshness: timedelta,
) -> bool:
    """Check whether a scraped_at timestamp is within the freshness window.

    Handles both string and datetime inputs, normalizes to UTC.
    Returns False if scraped_at is None or unparseable.
    """
    ts = parse_timestamp(scraped_at)
    if ts is None:
        return False
    return (datetime.now(tz=timezone.utc) - ts) < freshness


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    """Parse a timestamp string or datetime to a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
