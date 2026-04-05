"""Shared FastAPI dependencies."""

import threading
from typing import TYPE_CHECKING, Generator

from config.settings import PG_ENABLED
from db.connection import get_connection
from db.pg.dual_writer import DualWriter
from db.schema import init_schema

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

_schema_initialized = False
_schema_lock = threading.Lock()


def _ensure_schema(conn: "DuckDBPyConnection") -> None:
    """Run init_schema exactly once per process."""
    global _schema_initialized  # noqa: PLW0603
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        init_schema(conn)
        _schema_initialized = True


def get_db() -> Generator[DualWriter, None, None]:
    """Yield a DualWriter wrapping DuckDB + optional Postgres session."""
    duck = get_connection()
    _ensure_schema(duck)

    pg_session = None
    if PG_ENABLED:
        from db.pg.engine import get_session_factory

        pg_session = get_session_factory()()

    dw = DualWriter(duck, pg_session)
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
        duck.close()
