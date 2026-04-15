"""Backfill retired_date across lego_items and brickeconomy_snapshots.

Two gaps in the schema:
1. lego_items.retired_date is 100% NULL — populate from
   brickeconomy_snapshots.retired_date (latest snapshot per set).
2. brickeconomy_snapshots.year_retired is 100% NULL — derive from its own
   retired_date so feature queries that read year_retired work.

Idempotent: re-running only touches rows that are still NULL.

Usage:
    .venv/bin/python -m scripts.backfill_retired_date
"""

from __future__ import annotations

import logging

from db.pg.engine import get_engine


logger = logging.getLogger(__name__)


def backfill_lego_items_from_be(engine) -> int:
    """Copy BE's latest retired_date onto lego_items for any row still NULL."""
    with engine.begin() as conn:
        result = conn.exec_driver_sql(
            """
            WITH latest_be AS (
                SELECT DISTINCT ON (set_number)
                    set_number, retired_date
                FROM brickeconomy_snapshots
                WHERE retired_date IS NOT NULL
                ORDER BY set_number, scraped_at DESC
            )
            UPDATE lego_items li
            SET retired_date = latest_be.retired_date,
                year_retired = COALESCE(
                    li.year_retired,
                    EXTRACT(YEAR FROM latest_be.retired_date)::INTEGER
                )
            FROM latest_be
            WHERE li.set_number = latest_be.set_number
              AND li.retired_date IS NULL
            """
        )
        return result.rowcount or 0


def backfill_be_year_retired(engine) -> int:
    """Denormalize year_retired from retired_date on BE snapshots."""
    with engine.begin() as conn:
        result = conn.exec_driver_sql(
            """
            UPDATE brickeconomy_snapshots
            SET year_retired = EXTRACT(YEAR FROM retired_date)::INTEGER
            WHERE year_retired IS NULL
              AND retired_date IS NOT NULL
            """
        )
        return result.rowcount or 0


def backfill_li_year_retired_from_own_date(engine) -> int:
    """Fill year_retired on lego_items from its own retired_date column."""
    with engine.begin() as conn:
        result = conn.exec_driver_sql(
            """
            UPDATE lego_items
            SET year_retired = EXTRACT(YEAR FROM retired_date)::INTEGER
            WHERE year_retired IS NULL
              AND retired_date IS NOT NULL
            """
        )
        return result.rowcount or 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(name)s %(levelname)s: %(message)s",
    )
    engine = get_engine()

    n_li = backfill_lego_items_from_be(engine)
    logger.info("lego_items: backfilled retired_date on %d rows", n_li)

    n_be = backfill_be_year_retired(engine)
    logger.info("brickeconomy_snapshots: backfilled year_retired on %d rows", n_be)

    n_li_yr = backfill_li_year_retired_from_own_date(engine)
    logger.info("lego_items: backfilled year_retired on %d rows", n_li_yr)

    # Reconciliation — how many retired sets still lack a date anywhere.
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            """
            SELECT
                (SELECT COUNT(*) FROM lego_items WHERE retired_date IS NULL) li_null,
                (SELECT COUNT(DISTINCT set_number) FROM bricklink_price_history) bl_sets,
                (SELECT COUNT(DISTINCT bl.set_number)
                 FROM bricklink_price_history bl
                 LEFT JOIN lego_items li ON li.set_number = bl.set_number
                 LEFT JOIN (
                    SELECT DISTINCT ON (set_number) set_number, retired_date
                    FROM brickeconomy_snapshots
                    ORDER BY set_number, scraped_at DESC
                 ) be ON be.set_number = bl.set_number
                 WHERE li.retired_date IS NULL
                   AND be.retired_date IS NULL
                   AND li.year_retired IS NULL
                ) bl_still_missing
            """
        ).fetchone()
        logger.info(
            "After backfill: lego_items null=%d, BL sets still without ANY retirement info=%d of %d",
            row[0], row[2], row[1],
        )


if __name__ == "__main__":
    main()
