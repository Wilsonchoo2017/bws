"""Shared FastAPI dependencies."""

from typing import Generator

from db.connection import get_connection
from db.pg.dual_writer import DualWriter
from db.pg.engine import get_session_factory


def get_db() -> Generator[DualWriter, None, None]:
    """Yield a DualWriter wrapping PgConnection + SQLAlchemy session."""
    primary = get_connection()
    pg_session = get_session_factory()()

    dw = DualWriter(primary, pg_session)
    try:
        yield dw
    finally:
        try:
            pg_session.commit()
        except Exception:
            pg_session.rollback()
        finally:
            pg_session.close()
        primary.close()
