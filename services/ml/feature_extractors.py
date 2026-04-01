"""Feature extraction functions for the ML pipeline.

Each function extracts features from one data source, restricted to data
available before the retirement cutoff (12 months before retirement).

For active sets, the latest available data is used.
"""

import json
import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config.ml import (
    FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT,
    LICENSED_THEMES,
)
from services.backtesting.cohort import PIECE_GROUPS, PRICE_TIERS
from services.ml.currency import to_usd_cents
from services.ml.feature_registry import register

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature registration (executed at import time)
# ---------------------------------------------------------------------------

# Group A: Set intrinsics
register("parts_count", "lego_items", "Number of pieces in set", "int")
register("minifig_count", "lego_items", "Number of minifigures", "int")
register("rrp_usd_cents", "brickeconomy_snapshots", "Retail price USD cents", "int")
register("price_per_part", "derived", "RRP USD cents / parts count")
register("shelf_life_years", "derived", "Years in production before retirement")
register("has_exclusive_minifigs", "brickeconomy_snapshots", "Has exclusive minifigures", "int")
register("minifig_value_ratio", "derived", "Minifig value / RRP ratio")

# Group B: Theme / category
register("is_licensed", "derived", "Theme is a licensed IP", "int")
register("subtheme_avg_growth_pct", "brickeconomy_snapshots", "Avg growth % for subtheme")
register("price_tier_ordinal", "derived", "Price tier bucket (0-3)")
register("pieces_bucket_ordinal", "derived", "Piece count bucket (0-4)")

# Group C: Market signals pre-retirement
register("annual_growth_pct", "brickeconomy_snapshots", "Annual growth %")
register("rolling_growth_pct", "brickeconomy_snapshots", "Rolling 12-month growth %")
register("growth_90d_pct", "brickeconomy_snapshots", "90-day growth %")
register("value_new_vs_rrp", "derived", "Market value (new) / RRP ratio")
register("theme_rank", "brickeconomy_snapshots", "Rank within theme/subtheme", "int")
register("distribution_cv", "derived", "Price distribution coefficient of variation")
register("rating_value", "brickeconomy_snapshots", "User rating (numeric)")
register("review_count", "brickeconomy_snapshots", "Number of reviews", "int")

# Group D: Amazon / Keepa signals
register("amazon_discount_pct", "derived", "Amazon price vs RRP discount %")
register("keepa_price_range_pct", "derived", "Keepa (highest-lowest)/RRP %")
register("keepa_rating", "keepa_snapshots", "Amazon rating")
register("keepa_review_count", "keepa_snapshots", "Amazon review count", "int")
register("keepa_tracking_users", "keepa_snapshots", "Keepa tracking user count", "int")

# Group E: Google Trends
register("gtrends_peak", "google_trends_snapshots", "Peak search interest value")
register("gtrends_avg", "google_trends_snapshots", "Average search interest value")

# Group F: Shopee saturation
register("shopee_listings", "shopee_saturation", "Number of Shopee listings", "int")
register("shopee_unique_sellers", "shopee_saturation", "Unique Shopee sellers", "int")
register("shopee_price_spread_pct", "shopee_saturation", "Shopee price spread %")
register("shopee_saturation_score", "shopee_saturation", "Shopee saturation score")


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------


def extract_all_features(
    conn: "DuckDBPyConnection",
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Extract all enabled features for the given sets.

    Features are restricted to data available before the retirement cutoff.
    For active sets, latest data is used.

    Returns DataFrame indexed by set_number with one column per feature.
    """
    base = _load_base_metadata(conn, set_numbers)
    if base.empty:
        return pd.DataFrame()

    # Extract from each source and merge
    intrinsics = _extract_intrinsics(base)
    be_features = _extract_brickeconomy_features(conn, base)
    keepa_features = _extract_keepa_features(conn, base)
    gtrends_features = _extract_gtrends_features(conn, base)
    shopee_features = _extract_shopee_features(conn, base)

    # Merge all feature groups on set_number
    result = intrinsics
    for df in [be_features, keepa_features, gtrends_features, shopee_features]:
        if not df.empty:
            result = result.merge(df, on="set_number", how="left")

    return result


# ---------------------------------------------------------------------------
# Base metadata (shared across extractors)
# ---------------------------------------------------------------------------


def _load_base_metadata(
    conn: "DuckDBPyConnection",
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Load core set metadata needed for cutoff computation."""
    where_clause = ""
    if set_numbers:
        placeholders = ", ".join(f"'{s}'" for s in set_numbers)
        where_clause = f"WHERE li.set_number IN ({placeholders})"

    query = f"""
        SELECT
            li.set_number,
            li.title,
            li.theme,
            li.year_released,
            li.year_retired,
            li.retired_date,
            li.parts_count,
            li.minifig_count,
            li.retiring_soon
        FROM lego_items li
        {where_clause}
        ORDER BY li.set_number
    """
    df = conn.execute(query).df()

    # Compute cutoff date for each set
    df["cutoff_year"] = None
    df["cutoff_month"] = None
    for idx, row in df.iterrows():
        rd = row.get("retired_date")
        yr = row.get("year_retired")
        if rd and isinstance(rd, str) and "-" in rd:
            parts = rd.split("-")
            ret_year, ret_month = int(parts[0]), int(parts[1])
            cy, cm = _sub_months(
                ret_year, ret_month, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            df.at[idx, "cutoff_year"] = cy
            df.at[idx, "cutoff_month"] = cm
        elif yr:
            cy, cm = _sub_months(
                int(yr), 1, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            df.at[idx, "cutoff_year"] = cy
            df.at[idx, "cutoff_month"] = cm
        # For active sets, cutoff is None -> we use latest data

    return df


# ---------------------------------------------------------------------------
# Group A: Set intrinsics
# ---------------------------------------------------------------------------


def _extract_intrinsics(base: pd.DataFrame) -> pd.DataFrame:
    """Extract features derived from core set metadata."""
    rows: list[dict] = []
    for _, item in base.iterrows():
        parts = item.get("parts_count")
        minifigs = item.get("minifig_count")
        theme = item.get("theme") or ""
        yr_released = item.get("year_released")
        yr_retired = item.get("year_retired")

        shelf_life = None
        if yr_released and yr_retired:
            shelf_life = float(yr_retired - yr_released)

        is_licensed = 1 if theme in LICENSED_THEMES else 0

        price_tier_ord = _ordinal_bucket(None, PRICE_TIERS)  # filled after BE merge
        pieces_ord = _ordinal_bucket(parts, PIECE_GROUPS) if parts else None

        rows.append({
            "set_number": item["set_number"],
            "parts_count": float(parts) if parts else None,
            "minifig_count": float(minifigs) if minifigs else None,
            "shelf_life_years": shelf_life,
            "is_licensed": float(is_licensed),
            "pieces_bucket_ordinal": float(pieces_ord) if pieces_ord is not None else None,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group C: BrickEconomy features (includes A extras and B)
# ---------------------------------------------------------------------------


def _extract_brickeconomy_features(
    conn: "DuckDBPyConnection",
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Extract features from BrickEconomy snapshots at cutoff time."""
    # Build per-set cutoff filter
    # For sets with cutoff, get latest snapshot before cutoff
    # For sets without cutoff (active), get latest snapshot
    query = """
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
    """
    be_df = conn.execute(query).df()
    if be_df.empty:
        return pd.DataFrame(columns=["set_number"])

    # For sets with a cutoff, re-query to get the snapshot before cutoff
    sets_with_cutoff = base.dropna(subset=["cutoff_year"])
    if not sets_with_cutoff.empty:
        cutoff_snapshots = _get_cutoff_snapshots(conn, sets_with_cutoff)
        if not cutoff_snapshots.empty:
            # Override latest snapshots with cutoff-filtered ones
            be_df = be_df[~be_df["set_number"].isin(cutoff_snapshots["set_number"])]
            be_df = pd.concat([be_df, cutoff_snapshots], ignore_index=True)

    rows: list[dict] = []
    for _, row in be_df.iterrows():
        sn = row["set_number"]
        rrp = _safe_float(row.get("rrp_usd_cents"))
        value_new = _safe_float(row.get("value_new_cents"))
        mean_cents = _safe_float(row.get("distribution_mean_cents"))
        stddev_cents = _safe_float(row.get("distribution_stddev_cents"))
        minifig_val = _safe_float(row.get("minifig_value_cents"))

        rating_str = row.get("rating_value")
        rating_num = None
        if pd.notna(rating_str) and rating_str:
            try:
                rating_num = float(str(rating_str).split("/")[0].strip())
            except (ValueError, IndexError):
                pass

        value_vs_rrp = None
        if rrp and rrp > 0 and value_new:
            value_vs_rrp = value_new / rrp

        dist_cv = None
        if mean_cents and mean_cents > 0 and stddev_cents:
            dist_cv = stddev_cents / mean_cents

        minifig_ratio = None
        if rrp and rrp > 0 and minifig_val:
            minifig_ratio = minifig_val / rrp

        has_exclusive = None
        excl_raw = row.get("exclusive_minifigs")
        if pd.notna(excl_raw):
            has_exclusive = 1.0 if excl_raw else 0.0

        price_tier_ord = _ordinal_bucket(int(rrp), PRICE_TIERS) if rrp else None

        # Compute price_per_part using base metadata
        base_row = base[base["set_number"] == sn]
        parts = None
        if not base_row.empty:
            parts = base_row.iloc[0].get("parts_count")
        ppp = None
        if rrp and rrp > 0 and parts and parts > 0:
            ppp = float(rrp) / float(parts)

        rows.append({
            "set_number": sn,
            "rrp_usd_cents": float(rrp) if rrp else None,
            "price_per_part": ppp,
            "annual_growth_pct": _safe_float(row.get("annual_growth_pct")),
            "rolling_growth_pct": _safe_float(row.get("rolling_growth_pct")),
            "growth_90d_pct": _safe_float(row.get("growth_90d_pct")),
            "value_new_vs_rrp": value_vs_rrp,
            "theme_rank": _safe_float(row.get("theme_rank")),
            "subtheme_avg_growth_pct": _safe_float(row.get("subtheme_avg_growth_pct")),
            "distribution_cv": dist_cv,
            "rating_value": rating_num,
            "review_count": _safe_float(row.get("review_count")),
            "has_exclusive_minifigs": has_exclusive,
            "minifig_value_ratio": minifig_ratio,
            "price_tier_ordinal": float(price_tier_ord) if price_tier_ord is not None else None,
        })

    return pd.DataFrame(rows)


def _get_cutoff_snapshots(
    conn: "DuckDBPyConnection",
    sets_with_cutoff: pd.DataFrame,
) -> pd.DataFrame:
    """Get latest BrickEconomy snapshot before each set's cutoff date."""
    # Build a UNION of per-set queries (DuckDB handles this efficiently)
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

    # Process in batches to avoid overly large queries
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
    # Drop the rn column
    if "rn" in combined.columns:
        combined = combined.drop(columns=["rn"])
    return combined


# ---------------------------------------------------------------------------
# Group D: Keepa / Amazon features
# ---------------------------------------------------------------------------


def _extract_keepa_features(
    conn: "DuckDBPyConnection",
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Extract features from Keepa snapshots."""
    query = """
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
    """
    keepa_df = conn.execute(query).df()
    if keepa_df.empty:
        return pd.DataFrame(columns=["set_number"])

    # Get RRP for discount calculation
    rrp_map: dict[str, float] = {}
    be_query = """
        SELECT set_number, rrp_usd_cents
        FROM (
            SELECT set_number, rrp_usd_cents,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents IS NOT NULL
        ) WHERE rn = 1
    """
    rrp_df = conn.execute(be_query).df()
    if not rrp_df.empty:
        rrp_map = dict(zip(rrp_df["set_number"], rrp_df["rrp_usd_cents"]))

    rows: list[dict] = []
    for _, row in keepa_df.iterrows():
        sn = row["set_number"]
        rrp_usd = rrp_map.get(sn)  # Already in USD cents from BrickEconomy
        # Keepa prices are in USD cents (Amazon US locale, domain ID 1)
        amazon_price = row.get("current_amazon_cents")
        lowest = row.get("lowest_ever_cents")
        highest = row.get("highest_ever_cents")

        # Both rrp_usd and amazon_price are in USD cents -- direct comparison
        discount_pct = None
        if rrp_usd and rrp_usd > 0 and amazon_price:
            discount_pct = (float(rrp_usd) - float(amazon_price)) / float(rrp_usd) * 100

        price_range_pct = None
        if rrp_usd and rrp_usd > 0 and lowest and highest:
            price_range_pct = (float(highest) - float(lowest)) / float(rrp_usd) * 100

        rows.append({
            "set_number": sn,
            "amazon_discount_pct": discount_pct,
            "keepa_price_range_pct": price_range_pct,
            "keepa_rating": _safe_float(row.get("rating")),
            "keepa_review_count": _safe_float(row.get("review_count")),
            "keepa_tracking_users": _safe_float(row.get("tracking_users")),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group E: Google Trends features
# ---------------------------------------------------------------------------


def _extract_gtrends_features(
    conn: "DuckDBPyConnection",
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Extract features from Google Trends snapshots."""
    query = """
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
    """
    gt_df = conn.execute(query).df()
    if gt_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in gt_df.iterrows():
        rows.append({
            "set_number": row["set_number"],
            "gtrends_peak": _safe_float(row.get("peak_value")),
            "gtrends_avg": _safe_float(row.get("average_value")),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group F: Shopee saturation features
# ---------------------------------------------------------------------------


def _extract_shopee_features(
    conn: "DuckDBPyConnection",
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Extract features from Shopee saturation data."""
    query = """
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
    """
    ss_df = conn.execute(query).df()
    if ss_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in ss_df.iterrows():
        # Shopee prices are in MYR; spread_pct is unitless so no conversion needed.
        # saturation_score is also unitless.
        rows.append({
            "set_number": row["set_number"],
            "shopee_listings": _safe_float(row.get("listings_count")),
            "shopee_unique_sellers": _safe_float(row.get("unique_sellers")),
            "shopee_price_spread_pct": _safe_float(row.get("price_spread_pct")),
            "shopee_saturation_score": _safe_float(row.get("saturation_score")),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(val: object) -> float | None:
    """Convert a value to float or None."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _ordinal_bucket(
    value: int | float | None,
    tiers: tuple[tuple[str, int, int], ...],
) -> int | None:
    """Map a value to its ordinal bucket index (0-based)."""
    if value is None:
        return None
    for i, (_, low, high) in enumerate(tiers):
        if low <= value < high:
            return i
    return None


def _sub_months(year: int, month: int, months: int) -> tuple[int, int]:
    """Subtract months from a year/month pair."""
    total = (year * 12 + month - 1) - months
    return total // 12, (total % 12) + 1
