"""DuckDB connection management for BWS.

Provides functions for creating and managing DuckDB connections.
"""

import logging
import subprocess
import sys

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

    if not _integrity_checked and not needs_rebuild and path == BWS_DB_PATH:
        _check_pk_integrity(path)

    conn = duckdb.connect(str(path))

    if needs_rebuild:
        from db.schema import _rebuild_all_tables, init_schema

        init_schema(conn)
        logger.warning("Rebuilding all tables after WAL recovery")
        _rebuild_all_tables(conn)

    return conn


# Tracks whether PK integrity has been verified this process
_integrity_checked = False


# Subprocess script that probes each table with a write-then-rollback.
# DuckDB PK index corruption only manifests on writes (INSERT/UPDATE),
# not reads. A FATAL error from DuckDB calls abort() and is uncatchable,
# so we run the probe in a subprocess. If it crashes, we know which table
# is corrupt.
_PROBE_SCRIPT = """\
import sys, duckdb
conn = duckdb.connect(sys.argv[1])
tables = conn.execute(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
).fetchall()
for (t,) in tables:
    try:
        cols = conn.execute(
            f"SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = '{t}' ORDER BY ordinal_position LIMIT 1"
        ).fetchone()
        if not cols:
            continue
        col, dtype = cols
        # Attempt a dummy INSERT inside a transaction then rollback.
        # This exercises the PK index write path.
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute(f"INSERT INTO {t} ({col}) VALUES (NULL)")
        except Exception:
            pass  # constraint violations are expected
        conn.execute("ROLLBACK")
    except Exception:
        pass
conn.close()
"""


def _check_pk_integrity(path: Path) -> None:
    """Probe all tables for PK index corruption using a subprocess.

    DuckDB PK corruption causes uncatchable FATAL errors (abort()) on
    writes. We run a write-probe in a subprocess: if it crashes, we
    rebuild all tables (reads still work, so rebuild is safe).

    Must be called BEFORE the main process opens a connection, since
    DuckDB only allows one process to hold the database lock.
    """
    global _integrity_checked  # noqa: PLW0603
    _integrity_checked = True

    try:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE_SCRIPT, str(path)],
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("PK integrity probe timed out -- skipping")
        return

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        logger.warning(
            "PK integrity probe crashed (exit %d) -- rebuilding all tables. "
            "stderr: %.500s",
            result.returncode,
            stderr,
        )
        conn = duckdb.connect(str(path))
        try:
            from db.schema import _rebuild_all_tables, init_schema

            init_schema(conn)
            _rebuild_all_tables(conn)
            logger.info("Table rebuild complete after integrity check failure")
        finally:
            conn.close()


def get_memory_connection() -> "DuckDBPyConnection":
    """Get an in-memory DuckDB connection (for testing)."""
    return duckdb.connect(":memory:")
