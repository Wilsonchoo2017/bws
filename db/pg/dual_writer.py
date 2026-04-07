"""Connection adapter: wraps PgConnection + optional SQLAlchemy session.

Provides a unified interface for repository code that needs both raw SQL
(via PgConnection) and ORM access (via SQLAlchemy Session).
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.dual_writer")


class DualWriter:
    """Wraps a PgConnection and an optional SQLAlchemy ORM session.

    All existing code continues to work unchanged because .execute(),
    .fetchone(), .fetchall(), and .description delegate to PgConnection.

    Repository code that needs ORM access can use .pg_session().
    """

    def __init__(
        self,
        conn: "PgConnection",
        pg_session: "Session | None" = None,
    ) -> None:
        self.duck = conn  # kept as .duck for backward compat with ML code
        self._pg = pg_session

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

    def pg_session(self) -> "Session | None":
        """Get the SQLAlchemy session, or None."""
        return self._pg

    def pg_flush(self) -> None:
        """Flush pending ORM changes. Safe to call even if session is None."""
        if self._pg is None:
            return
        try:
            self._pg.flush()
        except Exception:
            logger.warning("Postgres flush failed", exc_info=True)
            self._pg.rollback()

    def pg_commit(self) -> None:
        """Commit the ORM session. Safe to call even if session is None."""
        if self._pg is None:
            return
        try:
            self._pg.commit()
        except Exception:
            logger.warning("Postgres commit failed", exc_info=True)
            self._pg.rollback()

    def close(self) -> None:
        """Close both connections."""
        self.duck.close()
        if self._pg is not None:
            self._pg.close()
