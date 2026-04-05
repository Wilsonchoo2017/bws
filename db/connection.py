"""Database connection management for BWS.

Provides functions for creating and managing DuckDB and Postgres connections.
When DUCK_ENABLED=false, all reads and writes go through Postgres only.
"""

import logging
import subprocess
import sys

from pathlib import Path
from typing import TYPE_CHECKING

from config.settings import BWS_DB_PATH, DUCK_ENABLED, PG_ENABLED


if DUCK_ENABLED:
    import duckdb

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

    from db.pg.dual_writer import DualWriter
    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.db")

# Tracks whether WAL recovery has been performed this process
_wal_recovered = False


def ensure_db_directory() -> None:
    """Ensure the database directory exists."""
    BWS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _handle_wal_recovery(path: Path) -> bool:
    """Attempt WAL replay via subprocess; remove only if replay crashes.

    DuckDB replays the WAL on connect. A valid WAL (e.g. from Ctrl+C)
    contains committed transactions that should be recovered. Only a
    corrupt WAL triggers an uncatchable FATAL error.

    Strategy: try connecting in a subprocess (which triggers WAL replay).
    If it succeeds, data is recovered. If it crashes, the WAL is corrupt
    and we remove it.

    Returns True if WAL was corrupt and removed (needs table rebuild).
    """
    wal_path = Path(f"{path}.wal")
    if not wal_path.exists() or wal_path.stat().st_size == 0:
        return False

    wal_size = wal_path.stat().st_size
    logger.info(
        "WAL file found (%d bytes) -- attempting replay via subprocess",
        wal_size,
    )

    replay_script = (
        "import sys, duckdb\n"
        "conn = duckdb.connect(sys.argv[1])\n"
        "conn.execute('CHECKPOINT')\n"
        "conn.close()\n"
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", replay_script, str(path)],
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("WAL replay timed out -- removing WAL to unblock startup")
        wal_path.unlink()
        return True

    if result.returncode == 0:
        logger.info("WAL replayed successfully -- all pending writes recovered")
        return False

    stderr = result.stderr.decode(errors="replace")
    logger.warning(
        "WAL replay crashed (exit %d) -- removing corrupt WAL. "
        "stderr: %.500s",
        result.returncode,
        stderr,
    )
    # WAL may have been partially consumed; remove if still present
    if wal_path.exists():
        wal_path.unlink()
    return True


def get_connection(db_path: Path | None = None) -> "DuckDBPyConnection | PgConnection":
    """Get a database connection.

    When DUCK_ENABLED=true (default): returns a DuckDB connection with
    WAL recovery and PK integrity checks on first call.

    When DUCK_ENABLED=false: returns a PgConnection wrapper that
    provides the same API over Postgres.

    Args:
        db_path: Path to database file (default: BWS_DB_PATH, ignored when PG-only)

    Returns:
        DuckDB connection or PgConnection wrapper
    """
    if not DUCK_ENABLED:
        return _get_pg_connection()

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


def _get_pg_connection() -> "PgConnection":
    """Create a raw psycopg2 connection wrapped in PgConnection."""
    import psycopg2

    from config.settings import POSTGRES_URL
    from db.pg.pg_connection import PgConnection

    # Parse SQLAlchemy URL to psycopg2 DSN
    # "postgresql+psycopg2://user:pass@host:port/db" -> psycopg2 connect params
    url = POSTGRES_URL.replace("postgresql+psycopg2://", "postgresql://")
    raw_conn = psycopg2.connect(url)
    raw_conn.autocommit = True
    return PgConnection(raw_conn)


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


def get_dual_connection(db_path: Path | None = None) -> "DualWriter":
    """Get a DualWriter wrapping DuckDB + optional Postgres session.

    Use this in background tasks instead of get_connection() to enable
    dual-write during migration.

    When DUCK_ENABLED=false, returns a DualWriter backed by PgConnection
    (no DuckDB involved).
    """
    from db.pg.dual_writer import DualWriter

    if not DUCK_ENABLED:
        pg_conn = _get_pg_connection()
        from db.pg.engine import get_session_factory

        pg_session = get_session_factory()()
        return DualWriter(pg_conn, pg_session)

    duck = get_connection(db_path)
    pg_session = None

    if PG_ENABLED:
        from db.pg.engine import get_session_factory

        pg_session = get_session_factory()()

    return DualWriter(duck, pg_session)
