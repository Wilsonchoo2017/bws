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
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date,
            CAST(COALESCE(li.retired_date, be.retired_date) AS TEXT) AS retired_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
    """)


def load_keepa_bl_training_data(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Load training data for the Keepa+BL model.

    Returns:
        (base_df, keepa_df, target_series)
        - base_df: Factual metadata (theme, pieces, RRP, etc.)
        - keepa_df: Keepa timelines
        - target_series: BL current new price / RRP ratio, indexed by set_number
    """
    base_df = _read(engine, """
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            be.subtheme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            be.rrp_usd_cents,
            be.minifig_value_cents,
            be.exclusive_minifigs,
            COALESCE(li.year_released, be.year_released) AS year_released,
            COALESCE(
                li.year_retired,
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(
                li.retired_date,
                be.retired_date,
                CASE WHEN li.year_retired IS NOT NULL
                     THEN (li.year_retired::TEXT || '-07-01')::DATE
                END
            ) AS TEXT) AS retired_date,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """)

    keepa_df = _read(engine, """
        SELECT set_number, amazon_price_json, new_3p_fba_json,
               new_3p_fbm_json, buy_box_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) sub
    """)

    # BL current new price as target
    bl_df = _read(engine, """
        SELECT
            DISTINCT ON (set_number) set_number, current_new
        FROM bricklink_price_history
        ORDER BY set_number, scraped_at DESC
    """)

    # Extract price and compute ratio
    import numpy as np

    target_data: dict[str, float] = {}
    rrp_lookup = dict(zip(base_df["set_number"], base_df["rrp_usd_cents"]))

    for _, row in bl_df.iterrows():
        sn = str(row["set_number"])
        rrp = rrp_lookup.get(sn)
        if not rrp or rrp <= 0:
            continue
        cn = row.get("current_new")
        if not isinstance(cn, dict):
            continue
        for key in ("qty_avg_price", "avg_price"):
            val = cn.get(key)
            if isinstance(val, dict) and val.get("amount") and val["amount"] > 0:
                # BL prices are in MYR, convert to USD cents
                myr_amount = float(val["amount"])
                usd_cents = myr_amount / 4.4
                target_data[sn] = usd_cents / float(rrp)
                break

    target_series = pd.Series(target_data, name="bl_vs_rrp")
    return base_df, keepa_df, target_series


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
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date,
            CAST(COALESCE(li.retired_date, be.retired_date) AS TEXT) AS retired_date
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
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(li.retired_date, be.retired_date) AS TEXT) AS retired_date,
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
