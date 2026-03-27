"""DuckDB connection management for BWS.

Provides functions for creating and managing DuckDB connections.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from config.settings import BWS_DB_PATH


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def ensure_db_directory() -> None:
    """Ensure the database directory exists."""
    BWS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path | None = None) -> "DuckDBPyConnection":
    """Get a DuckDB connection.

    Args:
        db_path: Path to database file (default: BWS_DB_PATH)

    Returns:
        DuckDB connection
    """
    path = db_path or BWS_DB_PATH
    ensure_db_directory()
    return duckdb.connect(str(path))


def get_memory_connection() -> "DuckDBPyConnection":
    """Get an in-memory DuckDB connection (for testing)."""
    return duckdb.connect(":memory:")
