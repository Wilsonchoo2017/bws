"""DuckDB connection management for BWS.

Provides functions for creating and managing DuckDB connections.
"""

import logging

from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from config.settings import BWS_DB_PATH


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.db")

# Tracks whether WAL recovery has been performed this process
_wal_recovered = False


def ensure_db_directory() -> None:
    """Ensure the database directory exists."""
    BWS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _handle_wal_recovery(path: Path) -> bool:
    """Check for and remove stale WAL file from ungraceful shutdown.

    DuckDB crashes can corrupt the WAL, and replaying a corrupt WAL
    on connect triggers an uncatchable FATAL error that kills the process.

    Returns True if WAL was removed (indicating potential corruption).
    """
    wal_path = Path(f"{path}.wal")
    if wal_path.exists() and wal_path.stat().st_size > 0:
        logger.warning(
            "Stale WAL file detected (%d bytes) -- removing to prevent "
            "corruption replay. Some recent writes may be lost.",
            wal_path.stat().st_size,
        )
        wal_path.unlink()
        return True
    return False


def get_connection(db_path: Path | None = None) -> "DuckDBPyConnection":
    """Get a DuckDB connection.

    On first call per process, checks for stale WAL files from ungraceful
    shutdowns and removes them to prevent corruption. If a WAL was found,
    tables are rebuilt to repair any corrupted PK indexes.

    Args:
        db_path: Path to database file (default: BWS_DB_PATH)

    Returns:
        DuckDB connection
    """
    global _wal_recovered  # noqa: PLW0603
    path = db_path or BWS_DB_PATH
    ensure_db_directory()

    needs_rebuild = False
    if not _wal_recovered and path == BWS_DB_PATH:
        needs_rebuild = _handle_wal_recovery(path)
        _wal_recovered = True

    conn = duckdb.connect(str(path))

    if needs_rebuild:
        from db.schema import _rebuild_all_tables, init_schema

        init_schema(conn)
        logger.warning("Rebuilding all tables after WAL recovery")
        _rebuild_all_tables(conn)

    return conn


def get_memory_connection() -> "DuckDBPyConnection":
    """Get an in-memory DuckDB connection (for testing)."""
    return duckdb.connect(":memory:")
