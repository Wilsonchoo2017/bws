"""Shared FastAPI dependencies."""

import threading
from typing import TYPE_CHECKING, Generator

from config.settings import DUCK_ENABLED, PG_ENABLED
from db.connection import get_connection
from db.pg.dual_writer import DualWriter

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

_schema_initialized = False
_schema_lock = threading.Lock()


def _ensure_schema(conn: "DuckDBPyConnection") -> None:
    """Run init_schema exactly once per process (DuckDB only)."""
    global _schema_initialized  # noqa: PLW0603
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        from db.schema import init_schema

        init_schema(conn)
        _schema_initialized = True


def get_db() -> Generator[DualWriter, None, None]:
    """Yield a DualWriter wrapping DuckDB + optional Postgres session.

    When DUCK_ENABLED=false, the primary connection is PgConnection
    and schema init is skipped (Postgres schema managed by Alembic).
    """
    primary = get_connection()

    if DUCK_ENABLED:
        _ensure_schema(primary)

    pg_session = None
    if PG_ENABLED or not DUCK_ENABLED:
        from db.pg.engine import get_session_factory

        pg_session = get_session_factory()()

    dw = DualWriter(primary, pg_session)
    try:
        yield dw
    finally:
        if pg_session is not None:
            try:
                pg_session.commit()
            except Exception:
                pg_session.rollback()
            finally:
                pg_session.close()
        primary.close()
