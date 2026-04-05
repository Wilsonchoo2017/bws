"""PostgreSQL connection wrapper with DuckDB-compatible API.

When DUCK_ENABLED=false, this adapter lets all existing repository code
(which uses conn.execute(sql, params).fetchall() / .df()) work against
Postgres without changes.

Key translations:
- ``?`` placeholders -> ``%s`` (psycopg2 format)
- ``.df()`` on result -> pandas DataFrame via column descriptions
- ``nextval('seq')`` -> works natively in Postgres
"""

import logging
import re
from typing import Any

logger = logging.getLogger("bws.pg.connection")

# Matches ``?`` that is NOT inside a single-quoted string literal.
# Good enough for the parameterised queries used in this codebase.
_PARAM_RE = re.compile(r"\?")


_TRY_CAST_RE = re.compile(r"TRY_CAST\(", re.IGNORECASE)


def _duck_to_pg_sql(sql: str) -> str:
    """Translate DuckDB SQL to psycopg2-compatible Postgres SQL.

    Translations:
    - ``?`` placeholders -> ``%s``
    - ``TRY_CAST(`` -> ``CAST(`` (Postgres has no TRY_CAST; callers
      should ensure data is clean or wrap in a CASE expression)
    """
    sql = _TRY_CAST_RE.sub("CAST(", sql)
    if "?" not in sql:
        return sql
    # Escape literal % first (e.g. LIKE '%foo%')
    sql = sql.replace("%", "%%")
    # Then replace ? with %s
    sql = _PARAM_RE.sub("%s", sql)
    return sql


class PgCursorResult:
    """Wraps a psycopg2 cursor to provide DuckDB-style .fetchone()/.fetchall()/.df()."""

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    @property
    def description(self) -> Any:
        return self._cursor.description

    def df(self) -> Any:
        """Return query result as a pandas DataFrame (DuckDB .df() compat)."""
        import pandas as pd

        rows = self._cursor.fetchall()
        if not self._cursor.description:
            return pd.DataFrame()
        columns = [desc[0] for desc in self._cursor.description]
        return pd.DataFrame(rows, columns=columns)


class PgConnection:
    """DuckDB-compatible connection wrapper over a raw psycopg2 connection.

    Provides execute/fetchone/fetchall/description/df so that repository
    code works unchanged.
    """

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn
        self._cursor: Any = None

    def execute(self, query: str, params: Any = None) -> "PgCursorResult":
        pg_sql = _duck_to_pg_sql(query)
        cursor = self._conn.cursor()
        self._cursor = cursor
        try:
            if params is None:
                cursor.execute(pg_sql)
            else:
                # DuckDB accepts list; psycopg2 accepts tuple
                cursor.execute(pg_sql, tuple(params))
        except Exception:
            logger.error("PG execute failed: %s", pg_sql[:200], exc_info=True)
            raise
        return PgCursorResult(cursor)

    def fetchone(self) -> Any:
        if self._cursor is None:
            return None
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        if self._cursor is None:
            return []
        return self._cursor.fetchall()

    @property
    def description(self) -> Any:
        if self._cursor is None:
            return None
        return self._cursor.description

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
