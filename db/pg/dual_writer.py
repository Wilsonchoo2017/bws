"""Dual-write adapter: writes to DuckDB first, then Postgres if enabled.

During the migration, DuckDB remains the source of truth. Postgres
receives shadow writes. If a Postgres write fails, it is logged and
swallowed -- the DuckDB write stands.

When DUCK_ENABLED=false, DuckDB is replaced by PgConnection and all
reads/writes go through Postgres only.
"""

import logging
from typing import TYPE_CHECKING, Any

from config.settings import DUCK_ENABLED, PG_ENABLED

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection
    from sqlalchemy.orm import Session

    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.dual_writer")


class DualWriter:
    """Wraps a DuckDB (or PgConnection) and an optional Postgres ORM session.

    All existing code continues to work unchanged because .execute(),
    .fetchone(), .fetchall(), and .description delegate to the primary
    connection (DuckDB or PgConnection depending on DUCK_ENABLED).

    Repository code that adds Postgres writes can access .pg_session().
    ML queries that need .df() can access .duck directly (which may be
    a PgConnection when DuckDB is disabled).
    """

    def __init__(
        self,
        duck: "DuckDBPyConnection | PgConnection",
        pg_session: "Session | None" = None,
    ) -> None:
        self.duck = duck
        self._pg = pg_session
        self._pg_enabled = (PG_ENABLED or not DUCK_ENABLED) and pg_session is not None

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query on the primary connection (passthrough)."""
        if params is None:
            return self.duck.execute(query)
        return self.duck.execute(query, params)

    def fetchone(self) -> Any:
        """Fetch one row from the primary connection (passthrough)."""
        return self.duck.fetchone()

    def fetchall(self) -> list[Any]:
        """Fetch all rows from the primary connection (passthrough)."""
        return self.duck.fetchall()

    @property
    def description(self) -> Any:
        """Column descriptions from the primary connection (passthrough)."""
        return self.duck.description

    def pg_session(self) -> "Session | None":
        """Get the Postgres session, or None if PG is disabled."""
        return self._pg if self._pg_enabled else None

    def pg_flush(self) -> None:
        """Flush pending Postgres changes. Safe to call even if PG is off."""
        if not self._pg_enabled or self._pg is None:
            return
        try:
            self._pg.flush()
        except Exception:
            logger.warning("Postgres flush failed", exc_info=True)
            self._pg.rollback()

    def pg_commit(self) -> None:
        """Commit the Postgres session. Safe to call even if PG is off."""
        if not self._pg_enabled or self._pg is None:
            return
        try:
            self._pg.commit()
        except Exception:
            logger.warning("Postgres commit failed", exc_info=True)
            self._pg.rollback()

    def close(self) -> None:
        """Close both connections."""
        self.duck.close()
        if self._pg_enabled and self._pg is not None:
            self._pg.close()
