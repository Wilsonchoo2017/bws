"""Database connection management for BWS.

Provides functions for creating and managing Postgres connections.
"""

import logging
from typing import TYPE_CHECKING

from config.settings import POSTGRES_URL

if TYPE_CHECKING:
    from db.pg.dual_writer import DualWriter
    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.db")


def get_connection() -> "PgConnection":
    """Get a Postgres database connection.

    Returns:
        PgConnection wrapper over a raw psycopg2 connection
    """
    import psycopg2

    from db.pg.pg_connection import PgConnection

    url = POSTGRES_URL.replace("postgresql+psycopg2://", "postgresql://")
    raw_conn = psycopg2.connect(url)
    raw_conn.autocommit = True
    return PgConnection(raw_conn)


def get_dual_connection() -> "DualWriter":
    """Get a DualWriter wrapping PgConnection + SQLAlchemy session.

    Use this in background tasks that need both raw SQL and ORM access.
    """
    from db.pg.dual_writer import DualWriter
    from db.pg.engine import get_session_factory

    pg_conn = get_connection()
    pg_session = get_session_factory()()
    return DualWriter(pg_conn, pg_session)
