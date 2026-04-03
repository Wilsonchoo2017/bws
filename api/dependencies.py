"""Shared FastAPI dependencies."""

import threading
from typing import TYPE_CHECKING, Generator

from db.connection import get_connection
from db.schema import init_schema

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

_schema_initialized = False
_schema_lock = threading.Lock()


def _ensure_schema(conn: "DuckDBPyConnection") -> None:
    """Run init_schema exactly once per process."""
    global _schema_initialized
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        init_schema(conn)
        _schema_initialized = True


def get_db() -> Generator["DuckDBPyConnection", None, None]:
    """Yield an initialized DuckDB connection, closing it on exit."""
    conn = get_connection()
    try:
        _ensure_schema(conn)
        yield conn
    finally:
        conn.close()
