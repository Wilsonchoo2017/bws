"""DuckDB persistence for BrickEconomy snapshots."""

import json
import logging
from typing import TYPE_CHECKING

from services.brickeconomy.parser import BrickeconomySnapshot

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.brickeconomy.repository")


def save_snapshot(conn: "DuckDBPyConnection", snapshot: BrickeconomySnapshot) -> int:
    """Insert a snapshot row and return the new row ID."""
    row_id = conn.execute(
        "SELECT nextval('brickeconomy_snapshots_id_seq')"
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO brickeconomy_snapshots (
            id, set_number, scraped_at,
            title, theme, subtheme, year_released, pieces, minifigs,
            availability, image_url, brickeconomy_url,
            rrp_usd_cents, rrp_gbp_cents, rrp_eur_cents,
            value_new_cents, value_used_cents,
            annual_growth_pct, rating_value, review_count,
            future_estimate_cents, future_estimate_date,
            distribution_mean_cents, distribution_stddev_cents,
            value_chart_json, sales_trend_json, candlestick_json
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?
        )
        """,
        [
            row_id,
            snapshot.set_number,
            snapshot.scraped_at,
            snapshot.title,
            snapshot.theme,
            snapshot.subtheme,
            snapshot.year_released,
            snapshot.pieces,
            snapshot.minifigs,
            snapshot.availability,
            snapshot.image_url,
            snapshot.brickeconomy_url,
            snapshot.rrp_usd_cents,
            snapshot.rrp_gbp_cents,
            snapshot.rrp_eur_cents,
            snapshot.value_new_cents,
            snapshot.value_used_cents,
            snapshot.annual_growth_pct,
            snapshot.rating_value,
            snapshot.review_count,
            snapshot.future_estimate_cents,
            snapshot.future_estimate_date,
            snapshot.distribution_mean_cents,
            snapshot.distribution_stddev_cents,
            json.dumps([list(row) for row in snapshot.value_chart]),
            json.dumps([list(row) for row in snapshot.sales_trend]),
            json.dumps([list(row) for row in snapshot.candlestick]),
        ],
    )

    logger.info(
        "Saved BrickEconomy snapshot id=%d for %s", row_id, snapshot.set_number
    )
    return row_id


def record_current_value(
    conn: "DuckDBPyConnection", snapshot: BrickeconomySnapshot
) -> None:
    """Write the current new/sealed value to the unified price_records table."""
    if snapshot.value_new_cents is None:
        return

    from services.items.repository import record_price

    record_price(
        conn,
        set_number=snapshot.set_number,
        source="brickeconomy",
        price_cents=snapshot.value_new_cents,
        currency="USD",
        title=snapshot.title,
        url=snapshot.brickeconomy_url,
    )


def get_latest_snapshot(
    conn: "DuckDBPyConnection", set_number: str
) -> dict | None:
    """Get the most recent snapshot for a set."""
    row = conn.execute(
        """
        SELECT * FROM brickeconomy_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in conn.description]
    return dict(zip(columns, row))


def get_snapshots(
    conn: "DuckDBPyConnection", set_number: str, *, limit: int = 50
) -> list[dict]:
    """Get snapshot history for a set, newest first."""
    rows = conn.execute(
        """
        SELECT * FROM brickeconomy_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        [set_number, limit],
    ).fetchall()
    columns = [desc[0] for desc in conn.description]
    return [dict(zip(columns, row)) for row in rows]
