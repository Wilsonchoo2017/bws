"""Persistence for BrickEconomy snapshots."""

import json
import logging

from db.pg.writes import _get_pg, pg_insert_be_snapshot
from services.brickeconomy.parser import BrickeconomySnapshot
from typing import Any


logger = logging.getLogger("bws.brickeconomy.repository")


def save_snapshot(conn: Any, snapshot: BrickeconomySnapshot) -> int:
    """Insert a snapshot row and return the new row ID."""
    row_id = conn.execute(
        "SELECT nextval('brickeconomy_snapshots_id_seq')"
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO brickeconomy_snapshots (
            id, set_number, scraped_at,
            title, theme, subtheme, year_released, year_retired,
            release_date, retired_date,
            pieces, minifigs, minifig_value_cents, exclusive_minifigs,
            availability, retiring_soon, image_url, brickeconomy_url,
            upc, ean, designer,
            rrp_usd_cents, rrp_gbp_cents, rrp_eur_cents,
            rrp_cad_cents, rrp_aud_cents,
            value_new_cents, value_used_cents,
            used_value_low_cents, used_value_high_cents,
            annual_growth_pct, total_growth_pct,
            rolling_growth_pct, growth_90d_pct,
            rating_value, review_count,
            theme_rank, subtheme_avg_growth_pct,
            future_estimate_cents, future_estimate_date,
            distribution_mean_cents, distribution_stddev_cents,
            value_chart_json, sales_trend_json, candlestick_json
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
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
            snapshot.year_retired,
            snapshot.release_date,
            snapshot.retired_date,
            snapshot.pieces,
            snapshot.minifigs,
            snapshot.minifig_value_cents,
            snapshot.exclusive_minifigs,
            snapshot.availability,
            snapshot.retiring_soon,
            snapshot.image_url,
            snapshot.brickeconomy_url,
            snapshot.upc,
            snapshot.ean,
            snapshot.designer,
            snapshot.rrp_usd_cents,
            snapshot.rrp_gbp_cents,
            snapshot.rrp_eur_cents,
            snapshot.rrp_cad_cents,
            snapshot.rrp_aud_cents,
            snapshot.value_new_cents,
            snapshot.value_used_cents,
            snapshot.used_value_low_cents,
            snapshot.used_value_high_cents,
            snapshot.annual_growth_pct,
            snapshot.total_growth_pct,
            snapshot.rolling_growth_pct,
            snapshot.growth_90d_pct,
            snapshot.rating_value,
            snapshot.review_count,
            snapshot.theme_rank,
            snapshot.subtheme_avg_growth_pct,
            snapshot.future_estimate_cents,
            snapshot.future_estimate_date,
            snapshot.distribution_mean_cents,
            snapshot.distribution_stddev_cents,
            json.dumps([list(row) for row in snapshot.value_chart]),
            json.dumps([list(row) for row in snapshot.sales_trend]),
            json.dumps([list(row) for row in snapshot.candlestick]),
        ],
    )

    # Write to Postgres
    pg = _get_pg(conn)
    if pg is not None:
        pg_insert_be_snapshot(
            pg,
            set_number=snapshot.set_number,
            scraped_at=snapshot.scraped_at,
            title=snapshot.title,
            theme=snapshot.theme,
            subtheme=snapshot.subtheme,
            year_released=snapshot.year_released,
            year_retired=snapshot.year_retired,
            release_date=snapshot.release_date,
            retired_date=snapshot.retired_date,
            pieces=snapshot.pieces,
            minifigs=snapshot.minifigs,
            minifig_value_cents=snapshot.minifig_value_cents,
            exclusive_minifigs=snapshot.exclusive_minifigs,
            availability=snapshot.availability,
            retiring_soon=snapshot.retiring_soon,
            image_url=snapshot.image_url,
            brickeconomy_url=snapshot.brickeconomy_url,
            upc=snapshot.upc,
            ean=snapshot.ean,
            designer=snapshot.designer,
            rrp_usd_cents=snapshot.rrp_usd_cents,
            rrp_gbp_cents=snapshot.rrp_gbp_cents,
            rrp_eur_cents=snapshot.rrp_eur_cents,
            rrp_cad_cents=snapshot.rrp_cad_cents,
            rrp_aud_cents=snapshot.rrp_aud_cents,
            value_new_cents=snapshot.value_new_cents,
            value_used_cents=snapshot.value_used_cents,
            used_value_low_cents=snapshot.used_value_low_cents,
            used_value_high_cents=snapshot.used_value_high_cents,
            annual_growth_pct=snapshot.annual_growth_pct,
            total_growth_pct=snapshot.total_growth_pct,
            rolling_growth_pct=snapshot.rolling_growth_pct,
            growth_90d_pct=snapshot.growth_90d_pct,
            rating_value=snapshot.rating_value,
            review_count=snapshot.review_count,
            theme_rank=snapshot.theme_rank,
            subtheme_avg_growth_pct=snapshot.subtheme_avg_growth_pct,
            future_estimate_cents=snapshot.future_estimate_cents,
            future_estimate_date=snapshot.future_estimate_date,
            distribution_mean_cents=snapshot.distribution_mean_cents,
            distribution_stddev_cents=snapshot.distribution_stddev_cents,
            value_chart_json=[list(row) for row in snapshot.value_chart],
            sales_trend_json=[list(row) for row in snapshot.sales_trend],
            candlestick_json=[list(row) for row in snapshot.candlestick],
        )

    logger.info(
        "Saved BrickEconomy snapshot id=%d for %s", row_id, snapshot.set_number
    )
    return row_id


def record_current_value(
    conn: Any, snapshot: BrickeconomySnapshot
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
    conn: Any, set_number: str
) -> dict | None:
    """Get the most recent snapshot for a set."""
    from db.queries import get_latest_row

    return get_latest_row(conn, "brickeconomy_snapshots", key_value=set_number)


def get_snapshots(
    conn: Any, set_number: str, *, limit: int = 50
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
    from db.queries import rows_to_dicts

    return rows_to_dicts(conn, rows)
