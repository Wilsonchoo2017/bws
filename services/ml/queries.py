"""Data access layer for the ML pipeline.

All database queries live here. Functions accept a DuckDB connection and
return DataFrames or dicts. No business logic -- just data retrieval.

This eliminates the duplicated "latest snapshot per set" pattern that
was previously scattered across feature_extractors.py, target.py, and
growth_model.py.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base metadata
# ---------------------------------------------------------------------------


def load_base_metadata(
    conn: DuckDBPyConnection,
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Load core set metadata needed for feature extraction.

    Returns DataFrame with: set_number, title, theme, year_released,
    year_retired, retired_date, parts_count, minifig_count, retiring_soon.
    """
    where_clause = ""
    if set_numbers:
        placeholders = ", ".join(f"'{s}'" for s in set_numbers)
        where_clause = f"WHERE li.set_number IN ({placeholders})"

    query = f"""
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
            COALESCE(li.year_retired, be.year_retired) AS year_retired,
            COALESCE(li.retired_date, be.retired_date) AS retired_date,
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
    """
    return conn.execute(query).df()


def load_retired_sets(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load retired sets with RRP in USD cents.

    Returns DataFrame with: set_number, year_retired, retired_date, rrp_usd_cents.
    """
    return conn.execute("""
        SELECT
            li.set_number,
            li.year_retired,
            li.retired_date,
            be.rrp_usd_cents
        FROM lego_items li
        JOIN (
            SELECT
                set_number,
                rrp_usd_cents,
                ROW_NUMBER() OVER (
                    PARTITION BY set_number ORDER BY scraped_at DESC
                ) AS rn
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents IS NOT NULL AND rrp_usd_cents > 0
        ) be ON be.set_number = li.set_number AND be.rn = 1
        WHERE li.year_retired IS NOT NULL
        ORDER BY li.set_number
    """).df()


def load_year_retired(
    conn: DuckDBPyConnection,
    set_numbers: list[str],
) -> pd.DataFrame:
    """Load year_retired for a list of sets (used for chronological sorting)."""
    if not set_numbers:
        return pd.DataFrame(columns=["set_number", "year_retired"])

    placeholders = ", ".join(f"'{s}'" for s in set_numbers)
    return conn.execute(f"""
        SELECT set_number, year_retired
        FROM lego_items
        WHERE set_number IN ({placeholders})
    """).df()


# ---------------------------------------------------------------------------
# BrickEconomy snapshots
# ---------------------------------------------------------------------------


def load_latest_be_snapshots(
    conn: DuckDBPyConnection,
) -> pd.DataFrame:
    """Load the most recent BrickEconomy snapshot per set.

    Returns all columns from brickeconomy_snapshots for the latest scraped_at.
    """
    return conn.execute("""
        SELECT
            bs.set_number,
            bs.rrp_usd_cents,
            bs.annual_growth_pct,
            bs.rolling_growth_pct,
            bs.growth_90d_pct,
            bs.value_new_cents,
            bs.theme_rank,
            bs.subtheme_avg_growth_pct,
            bs.rating_value,
            bs.review_count,
            bs.distribution_mean_cents,
            bs.distribution_stddev_cents,
            bs.minifig_value_cents,
            bs.exclusive_minifigs,
            bs.scraped_at
        FROM brickeconomy_snapshots bs
        INNER JOIN (
            SELECT
                set_number,
                MAX(scraped_at) AS latest_scraped
            FROM brickeconomy_snapshots
            GROUP BY set_number
        ) latest ON bs.set_number = latest.set_number
            AND bs.scraped_at = latest.latest_scraped
    """).df()


def load_be_cutoff_snapshots(
    conn: DuckDBPyConnection,
    sets_with_cutoff: pd.DataFrame,
) -> pd.DataFrame:
    """Load latest BrickEconomy snapshot before each set's cutoff date.

    Args:
        sets_with_cutoff: DataFrame with set_number, cutoff_year, cutoff_month.

    Returns:
        DataFrame of snapshots filtered to before the cutoff.
    """
    parts: list[str] = []
    for _, row in sets_with_cutoff.iterrows():
        sn = row["set_number"]
        cy = int(row["cutoff_year"])
        cm = int(row["cutoff_month"])
        cutoff_ts = f"{cy:04d}-{cm:02d}-28"
        parts.append(
            f"SELECT * FROM ("
            f"  SELECT *, ROW_NUMBER() OVER (ORDER BY scraped_at DESC) AS rn"
            f"  FROM brickeconomy_snapshots"
            f"  WHERE set_number = '{sn}' AND scraped_at <= '{cutoff_ts}'"
            f") WHERE rn = 1"
        )

    if not parts:
        return pd.DataFrame()

    batch_size = 50
    results: list[pd.DataFrame] = []
    for i in range(0, len(parts), batch_size):
        batch = parts[i : i + batch_size]
        query = " UNION ALL ".join(batch)
        try:
            df = conn.execute(query).df()
            if not df.empty:
                results.append(df)
        except Exception:
            logger.warning("Cutoff snapshot query failed for batch %d", i, exc_info=True)

    if not results:
        return pd.DataFrame()

    combined = pd.concat(results, ignore_index=True)
    if "rn" in combined.columns:
        combined = combined.drop(columns=["rn"])
    return combined


def load_rrp_map(conn: DuckDBPyConnection) -> dict[str, float]:
    """Load latest RRP USD cents per set as a dict.

    Returns:
        Dict mapping set_number -> rrp_usd_cents.
    """
    df = conn.execute("""
        SELECT set_number, rrp_usd_cents
        FROM (
            SELECT set_number, rrp_usd_cents,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents IS NOT NULL
        ) WHERE rn = 1
    """).df()
    if df.empty:
        return {}
    return dict(zip(df["set_number"], df["rrp_usd_cents"]))


def load_be_value_charts(
    conn: DuckDBPyConnection,
) -> dict[str, list[tuple[int, int, int]]]:
    """Load BrickEconomy value_chart_json parsed into (year, month, cents).

    Returns:
        Dict mapping set_number -> sorted list of (year, month, price_cents).
    """
    df = conn.execute("""
        SELECT set_number, value_chart_json
        FROM (
            SELECT
                set_number,
                value_chart_json,
                ROW_NUMBER() OVER (
                    PARTITION BY set_number ORDER BY scraped_at DESC
                ) AS rn
            FROM brickeconomy_snapshots
            WHERE value_chart_json IS NOT NULL
        )
        WHERE rn = 1
    """).df()
    result: dict[str, list[tuple[int, int, int]]] = {}

    for _, row in df.iterrows():
        chart_raw = row["value_chart_json"]
        if not chart_raw:
            continue

        try:
            chart = json.loads(chart_raw) if isinstance(chart_raw, str) else chart_raw

            points: list[tuple[int, int, int]] = []
            for entry in chart:
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                date_str = str(entry[0])
                price = int(entry[1])
                if "-" in date_str:
                    date_parts = date_str.split("-")
                    points.append((int(date_parts[0]), int(date_parts[1]), price))

            if points:
                points.sort()
                result[row["set_number"]] = points
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    return result


def load_be_snapshot_values(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load BrickEconomy snapshot value_new_cents over time.

    Returns DataFrame with: set_number, scraped_at, value_new_cents.
    """
    return conn.execute("""
        SELECT
            set_number,
            scraped_at,
            value_new_cents
        FROM brickeconomy_snapshots
        WHERE value_new_cents IS NOT NULL AND value_new_cents > 0
        ORDER BY set_number, scraped_at
    """).df()


# ---------------------------------------------------------------------------
# BrickLink monthly sales
# ---------------------------------------------------------------------------


def load_bricklink_monthly_prices(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load BrickLink monthly sales with avg_price in USD cents.

    Returns DataFrame with: item_id, year, month, avg_price.
    """
    return conn.execute("""
        SELECT
            item_id,
            year,
            month,
            avg_price
        FROM bricklink_monthly_sales
        WHERE condition = 'N'
            AND avg_price IS NOT NULL
            AND avg_price > 0
        ORDER BY item_id, year, month
    """).df()


# ---------------------------------------------------------------------------
# Keepa snapshots
# ---------------------------------------------------------------------------


def load_latest_keepa_snapshots(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load the most recent Keepa snapshot per set.

    Returns DataFrame with: set_number, current_amazon_cents, lowest_ever_cents,
    highest_ever_cents, rating, review_count, tracking_users.
    """
    return conn.execute("""
        SELECT
            ks.set_number,
            ks.current_amazon_cents,
            ks.lowest_ever_cents,
            ks.highest_ever_cents,
            ks.rating,
            ks.review_count,
            ks.tracking_users
        FROM keepa_snapshots ks
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM keepa_snapshots
            GROUP BY set_number
        ) l ON ks.set_number = l.set_number AND ks.scraped_at = l.latest
    """).df()


def load_keepa_timelines(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load Keepa historical price timeline data.

    Returns DataFrame with: set_number, amazon_price_json, buy_box_json,
    tracking_users, kp_reviews, kp_rating.
    """
    return conn.execute("""
        SELECT set_number, amazon_price_json, buy_box_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        )
    """).df()


# ---------------------------------------------------------------------------
# Google Trends
# ---------------------------------------------------------------------------


def load_latest_gtrends_snapshots(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load the most recent Google Trends snapshot per set.

    Returns DataFrame with: set_number, peak_value, average_value.
    """
    return conn.execute("""
        SELECT
            gt.set_number,
            gt.peak_value,
            gt.average_value
        FROM google_trends_snapshots gt
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM google_trends_snapshots
            GROUP BY set_number
        ) l ON gt.set_number = l.set_number AND gt.scraped_at = l.latest
    """).df()


# ---------------------------------------------------------------------------
# Shopee saturation
# ---------------------------------------------------------------------------


def load_latest_shopee_snapshots(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load the most recent Shopee saturation data per set.

    Returns DataFrame with: set_number, listings_count, unique_sellers,
    price_spread_pct, saturation_score.
    """
    return conn.execute("""
        SELECT
            ss.set_number,
            ss.listings_count,
            ss.unique_sellers,
            ss.price_spread_pct,
            ss.saturation_score
        FROM shopee_saturation ss
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM shopee_saturation
            GROUP BY set_number
        ) l ON ss.set_number = l.set_number AND ss.scraped_at = l.latest
    """).df()


# ---------------------------------------------------------------------------
# Growth model queries
# ---------------------------------------------------------------------------


def load_growth_training_data(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load all sets with BrickEconomy growth data for growth model training.

    Uses the latest BE snapshot per set to avoid duplicate rows.
    """
    return conn.execute("""
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            be.annual_growth_pct, be.rrp_usd_cents, be.rating_value,
            be.review_count, be.pieces, be.minifigs,
            be.rrp_gbp_cents, be.subtheme,
            COALESCE(
                li.year_retired,
                be.year_retired,
                TRY_CAST(LEFT(COALESCE(li.retired_date, be.retired_date), 4) AS INTEGER)
            ) AS year_retired
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
    """).df()


def load_growth_candidate_sets(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load sets eligible for growth prediction.

    Uses the latest BE snapshot per set to avoid duplicate rows.
    """
    return conn.execute("""
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            COALESCE(li.retiring_soon, be.retiring_soon) AS retiring_soon,
            be.rrp_usd_cents, be.rating_value, be.review_count,
            be.pieces, be.minifigs, be.rrp_gbp_cents, be.subtheme
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """).df()
