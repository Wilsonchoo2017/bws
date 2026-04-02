"""Shared FastAPI dependencies."""

from typing import TYPE_CHECKING, Generator

from db.connection import get_connection
from db.schema import init_schema

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def get_db() -> Generator["DuckDBPyConnection", None, None]:
    """Yield an initialized DuckDB connection, closing it on exit."""
    conn = get_connection()
    try:
        init_schema(conn)
        yield conn
    finally:
        conn.close()
