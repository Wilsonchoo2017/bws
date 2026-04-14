"""Portfolio settings repository -- key-value store for portfolio config."""

from __future__ import annotations

from typing import Any

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS portfolio_settings (
    key TEXT PRIMARY KEY,
    value_cents BIGINT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
"""

_table_ensured = False


def _ensure_table(conn: Any) -> None:
    global _table_ensured
    if not _table_ensured:
        conn.execute(_TABLE_SQL)
        _table_ensured = True


def get_total_capital(conn: Any) -> int | None:
    """Return total_capital_cents, or None if not set."""
    _ensure_table(conn)
    row = conn.execute(
        "SELECT value_cents FROM portfolio_settings WHERE key = ?",
        ["total_capital"],
    ).fetchone()
    return row[0] if row else None


def set_total_capital(conn: Any, cents: int) -> None:
    """Upsert total_capital_cents."""
    _ensure_table(conn)
    conn.execute(
        """
        INSERT INTO portfolio_settings (key, value_cents, updated_at)
        VALUES ('total_capital', ?, NOW())
        ON CONFLICT (key) DO UPDATE SET value_cents = ?, updated_at = NOW()
        """,
        [cents, cents],
    )
