"""PostgreSQL data access for the ML pipeline.

Primary data layer for model training.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _read(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


def load_growth_training_data(engine: Engine) -> pd.DataFrame:
    """Load all sets with BrickEconomy growth data for training."""
    return _read(engine, """
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            be.annual_growth_pct, be.rrp_usd_cents, be.rating_value,
            be.review_count, be.pieces, be.minifigs,
            be.rrp_gbp_cents, be.rrp_eur_cents, be.rrp_cad_cents, be.rrp_aud_cents,
            be.subtheme,
            be.distribution_mean_cents, be.distribution_stddev_cents,
            be.minifig_value_cents, be.exclusive_minifigs,
            be.designer,
            COALESCE(li.year_released, be.year_released) AS year_released,
            COALESCE(
                li.year_retired,
                be.year_retired,
                CAST(LEFT(COALESCE(
                    CAST(li.retired_date AS TEXT),
                    CAST(be.retired_date AS TEXT)
                ), 4) AS INTEGER)
            ) AS year_retired,
            COALESCE(
                CAST(li.release_date AS TEXT),
                CAST(be.release_date AS TEXT)
            ) AS release_date,
            COALESCE(
                CAST(li.retired_date AS TEXT),
                CAST(be.retired_date AS TEXT)
            ) AS retired_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
    """)


def load_keepa_timelines(engine: Engine) -> pd.DataFrame:
    """Load Keepa historical price timeline data."""
    return _read(engine, """
        SELECT set_number, amazon_price_json, buy_box_json,
               new_3p_fba_json, new_3p_fbm_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) sub
    """)


def load_growth_candidate_sets(engine: Engine) -> pd.DataFrame:
    """Load sets eligible for growth prediction."""
    return _read(engine, """
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            COALESCE(li.retiring_soon, be.retiring_soon) AS retiring_soon,
            be.rrp_usd_cents, be.rating_value, be.review_count,
            be.pieces, be.minifigs,
            be.rrp_gbp_cents, be.rrp_eur_cents, be.rrp_cad_cents, be.rrp_aud_cents,
            be.subtheme,
            be.distribution_mean_cents, be.distribution_stddev_cents,
            be.minifig_value_cents, be.exclusive_minifigs,
            be.designer,
            COALESCE(li.year_released, be.year_released) AS year_released,
            COALESCE(
                li.year_retired,
                be.year_retired,
                CAST(LEFT(COALESCE(
                    CAST(li.retired_date AS TEXT),
                    CAST(be.retired_date AS TEXT)
                ), 4) AS INTEGER)
            ) AS year_retired,
            COALESCE(
                CAST(li.release_date AS TEXT),
                CAST(be.release_date AS TEXT)
            ) AS release_date,
            COALESCE(
                CAST(li.retired_date AS TEXT),
                CAST(be.retired_date AS TEXT)
            ) AS retired_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """)


def load_base_metadata(
    engine: Engine,
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Load core set metadata needed for feature extraction."""
    where_clause = ""
    if set_numbers:
        placeholders = ", ".join(f"'{s}'" for s in set_numbers)
        where_clause = f"WHERE li.set_number IN ({placeholders})"

    return _read(engine, f"""
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            CASE
                WHEN li.year_released IS NOT NULL AND li.year_released <= 2026
                    THEN li.year_released
                WHEN be.year_released IS NOT NULL
                    THEN be.year_released
                ELSE li.year_released
            END AS year_released,
            COALESCE(
                li.year_retired,
                be.year_retired,
                CAST(LEFT(COALESCE(
                    CAST(li.retired_date AS TEXT),
                    CAST(be.retired_date AS TEXT)
                ), 4) AS INTEGER)
            ) AS year_retired,
            COALESCE(
                CAST(li.retired_date AS TEXT),
                CAST(be.retired_date AS TEXT)
            ) AS retired_date,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            COALESCE(li.retiring_soon, be.retiring_soon) AS retiring_soon
        FROM lego_items li
        LEFT JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        {where_clause}
        ORDER BY li.set_number
    """)
