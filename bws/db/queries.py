"""Common database query functions for BWS."""

from datetime import datetime
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def get_next_id(conn: "DuckDBPyConnection", sequence_name: str) -> int:
    """Get the next ID from a sequence.

    Args:
        conn: DuckDB connection
        sequence_name: Name of the sequence

    Returns:
        Next ID value
    """
    result = conn.execute(f"SELECT nextval('{sequence_name}')").fetchone()
    if result is None:
        msg = f"Failed to get next ID from sequence {sequence_name}"
        raise RuntimeError(msg)
    return int(result[0])


def format_timestamp(dt: datetime | None) -> str | None:
    """Format a datetime for DuckDB.

    Args:
        dt: Datetime to format, or None

    Returns:
        ISO format string or None
    """
    return dt.isoformat() if dt else None


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    """Parse a timestamp from DuckDB.

    Args:
        value: Timestamp string or datetime, or None

    Returns:
        Datetime or None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
