"""Connection adapter: wraps PgConnection.

Provides a unified interface for repository code that uses raw SQL
via PgConnection.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.dual_writer")


class DualWriter:
    """Wraps a PgConnection.

    All existing code works unchanged because .execute(),
    .fetchone(), .fetchall(), and .description delegate to PgConnection.
    """

    def __init__(
        self,
        conn: "PgConnection",
        pg_session: Any = None,
    ) -> None:
        self._conn = conn
        self._pg = pg_session

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query on the connection (passthrough)."""
        if params is None:
            return self._conn.execute(query)
        return self._conn.execute(query, params)

    def fetchone(self) -> Any:
        """Fetch one row from the connection (passthrough)."""
        return self._conn.fetchone()

    def fetchall(self) -> list[Any]:
        """Fetch all rows from the connection (passthrough)."""
        return self._conn.fetchall()

    @property
    def description(self) -> Any:
        """Column descriptions from the connection (passthrough)."""
        return self._conn.description

    def pg_session(self) -> Any:
        """Get the SQLAlchemy session, or None."""
        return self._pg

    def pg_flush(self) -> None:
        """Flush pending ORM changes."""
        if self._pg is None:
            return
        try:
            self._pg.flush()
        except Exception:
            logger.warning("Postgres flush failed", exc_info=True)
            self._pg.rollback()

    def pg_commit(self) -> None:
        """Commit the ORM session."""
        if self._pg is None:
            return
        try:
            self._pg.commit()
        except Exception:
            logger.warning("Postgres commit failed", exc_info=True)
            self._pg.rollback()

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()
        if self._pg is not None:
            self._pg.close()
