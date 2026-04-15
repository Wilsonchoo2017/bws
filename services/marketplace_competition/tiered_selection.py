"""Tiered staleness-based selection for marketplace competition sweeps.

The same CTE selects items needing a competition check for either
Shopee or Carousell; the only difference is which snapshots table
provides `last_checked`. This module owns that shared query so new
marketplaces don't duplicate the tier logic.

Tiers (priority, stale_days):
    1. cart_items            ->  7 days  (weekly)
    2. lego_items.watchlist  ->  7 days  (weekly)
    3. portfolio holdings    -> 14 days
    4. lego_items.retiring_soon -> 30 days (monthly)

A set that qualifies under multiple tiers uses the smallest priority
and the shortest stale window.
"""

from __future__ import annotations

from typing import Any

_ALLOWED_TABLES = {
    "shopee_competition_snapshots",
    "carousell_competition_snapshots",
}


def get_tiered_items_needing_check(
    conn: Any,
    snapshots_table: str,
    *,
    limit: int = 20,
) -> list[dict]:
    """Return up to `limit` items needing a competition check.

    Args:
        conn: DB connection.
        snapshots_table: Name of the `{platform}_competition_snapshots`
            table to use for last-checked staleness. Validated against an
            allow-list to prevent SQL injection.
        limit: Max items returned.

    Each row: {set_number, title, rrp_cents, priority, stale_days, last_checked}.
    """
    if not isinstance(limit, int):
        raise TypeError("limit must be int")
    if snapshots_table not in _ALLOWED_TABLES:
        raise ValueError(
            f"snapshots_table must be one of {_ALLOWED_TABLES}, got {snapshots_table!r}"
        )

    query = f"""
        WITH targets AS (
            SELECT set_number, 1 AS priority, 7 AS stale_days FROM cart_items
            UNION ALL
            SELECT set_number, 2, 7 FROM lego_items WHERE watchlist = TRUE
            UNION ALL
            SELECT pt.set_number, 3, 14
            FROM portfolio_transactions pt
            GROUP BY pt.set_number
            HAVING SUM(CASE WHEN pt.txn_type = 'BUY' THEN pt.quantity ELSE -pt.quantity END) > 0
            UNION ALL
            SELECT set_number, 4, 30 FROM lego_items WHERE retiring_soon = TRUE
        ),
        tiered AS (
            SELECT set_number,
                   MIN(priority) AS priority,
                   MIN(stale_days) AS stale_days
            FROM targets
            GROUP BY set_number
        )
        SELECT t.set_number,
               li.title,
               li.rrp_cents,
               t.priority,
               t.stale_days,
               cs.last_checked
        FROM tiered t
        JOIN lego_items li ON li.set_number = t.set_number
        LEFT JOIN (
            SELECT set_number, MAX(scraped_at) AS last_checked
            FROM {snapshots_table}
            GROUP BY set_number
        ) cs ON cs.set_number = t.set_number
        WHERE cs.last_checked IS NULL
           OR cs.last_checked < now() - make_interval(days => t.stale_days)
        ORDER BY t.priority ASC, cs.last_checked ASC NULLS FIRST
        LIMIT ?
    """  # noqa: S608 -- snapshots_table validated against _ALLOWED_TABLES above
    result = conn.execute(query, [limit]).fetchall()

    return [
        {
            "set_number": row[0],
            "title": row[1],
            "rrp_cents": row[2],
            "priority": row[3],
            "stale_days": row[4],
            "last_checked": row[5],
        }
        for row in result
    ]
