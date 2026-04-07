"""Connection adapter: wraps PgConnection.

Provides a unified interface for repository code that uses raw SQL
via PgConnection. The ORM session (SQLAlchemy) dual-write path has
been removed -- all writes go through PgConnection directly.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.dual_writer")


class DualWriter:
    """Wraps a PgConnection.

    All existing code continues to work unchanged because .execute(),
    .fetchone(), .fetchall(), and .description delegate to PgConnection.

    The .duck attribute is kept for backward compat with ML code.
    """

    def __init__(
        self,
        conn: "PgConnection",
        pg_session: Any = None,
    ) -> None:
        self.duck = conn  # kept as .duck for backward compat with ML code
        self._pg = pg_session  # retained for callers that still pass it

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query on the connection (passthrough)."""
        if params is None:
            return self.duck.execute(query)
        return self.duck.execute(query, params)

    def fetchone(self) -> Any:
        """Fetch one row from the connection (passthrough)."""
        return self.duck.fetchone()

    def fetchall(self) -> list[Any]:
        """Fetch all rows from the connection (passthrough)."""
        return self.duck.fetchall()

    @property
    def description(self) -> Any:
        """Column descriptions from the connection (passthrough)."""
        return self.duck.description

    def pg_session(self) -> Any:
        """Get the SQLAlchemy session, or None. Kept for backward compat."""
        return self._pg

    def pg_flush(self) -> None:
        """Flush pending ORM changes. No-op since ORM writes were removed."""
        if self._pg is None:
            return
        try:
            self._pg.flush()
        except Exception:
            logger.warning("Postgres flush failed", exc_info=True)
            self._pg.rollback()

    def pg_commit(self) -> None:
        """Commit the ORM session. No-op if session is None."""
        if self._pg is None:
            return
        try:
            self._pg.commit()
        except Exception:
            logger.warning("Postgres commit failed", exc_info=True)
            self._pg.rollback()

    def close(self) -> None:
        """Close the connection."""
        self.duck.close()
        if self._pg is not None:
            self._pg.close()
