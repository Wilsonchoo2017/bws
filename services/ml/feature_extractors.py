"""Feature extraction functions for the ML pipeline.

Each function extracts features from one data source, restricted to data
available before the retirement cutoff (12 months before retirement).

For active sets, the latest available data is used.
"""

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config.ml import (
    FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT,
    LICENSED_THEMES,
)
from services.backtesting.cohort import PIECE_GROUPS, PRICE_TIERS
from services.ml.feature_registry import register
from services.ml.helpers import offset_months, ordinal_bucket, safe_float
from services.ml.queries import (
    load_base_metadata as _query_base_metadata,
    load_be_cutoff_snapshots,
    load_latest_be_snapshots,
    load_latest_gtrends_snapshots,
    load_latest_keepa_snapshots,
    load_latest_shopee_snapshots,
    load_rrp_map,
)

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
# Main extraction entry point (impure -- orchestrates I/O + computation)
# ---------------------------------------------------------------------------


def extract_all_features(
    conn: "DuckDBPyConnection",
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Extract all enabled features for the given sets.

    This is the only impure function in this module -- it loads data from
    the database and delegates to pure extraction functions.

    Returns DataFrame indexed by set_number with one column per feature.
    """
    base = _load_base_metadata(conn, set_numbers)
    if base.empty:
        return pd.DataFrame()

    # Load data from each source
    be_df = load_latest_be_snapshots(conn)
    sets_with_cutoff = base.dropna(subset=["cutoff_year"])
    if not sets_with_cutoff.empty:
        cutoff_snapshots = load_be_cutoff_snapshots(conn, sets_with_cutoff)
        if not cutoff_snapshots.empty:
            be_df = be_df[~be_df["set_number"].isin(cutoff_snapshots["set_number"])]
            be_df = pd.concat([be_df, cutoff_snapshots], ignore_index=True)

    keepa_df = load_latest_keepa_snapshots(conn)
    rrp_map = load_rrp_map(conn)
    gtrends_df = load_latest_gtrends_snapshots(conn)
    shopee_df = load_latest_shopee_snapshots(conn)

    # Extract from each source (pure functions -- no I/O)
    intrinsics = extract_intrinsics(base)
    be_features = extract_brickeconomy_features(be_df, base)
    keepa_features = extract_keepa_features(keepa_df, rrp_map)
    gtrends_features = extract_gtrends_features(gtrends_df)
    shopee_features = extract_shopee_features(shopee_df)

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
    """Load core set metadata and compute cutoff dates."""
    df = _query_base_metadata(conn, set_numbers)

    # Compute cutoff date for each set
    df["cutoff_year"] = None
    df["cutoff_month"] = None
    for idx, row in df.iterrows():
        rd = row.get("retired_date")
        yr = row.get("year_retired")
        if rd and isinstance(rd, str) and "-" in rd:
            parts = rd.split("-")
            ret_year, ret_month = int(parts[0]), int(parts[1])
            cy, cm = offset_months(
                ret_year, ret_month, -FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            df.at[idx, "cutoff_year"] = cy
            df.at[idx, "cutoff_month"] = cm
        elif yr:
            cy, cm = offset_months(
                int(yr), 1, -FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            df.at[idx, "cutoff_year"] = cy
            df.at[idx, "cutoff_month"] = cm
        # For active sets, cutoff is None -> we use latest data

    return df


# ---------------------------------------------------------------------------
# Group A: Set intrinsics (pure)
# ---------------------------------------------------------------------------


def extract_intrinsics(base: pd.DataFrame) -> pd.DataFrame:
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

        pieces_ord = ordinal_bucket(parts, PIECE_GROUPS) if parts else None

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
# Group C: BrickEconomy features (includes A extras and B) (pure)
# ---------------------------------------------------------------------------


def extract_brickeconomy_features(
    be_df: pd.DataFrame,
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Extract features from pre-loaded BrickEconomy snapshots.

    Args:
        be_df: BrickEconomy snapshot data (already cutoff-filtered if needed).
        base: Base metadata with set_number, parts_count, etc.
    """
    if be_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in be_df.iterrows():
        sn = row["set_number"]
        rrp = safe_float(row.get("rrp_usd_cents"))
        value_new = safe_float(row.get("value_new_cents"))
        mean_cents = safe_float(row.get("distribution_mean_cents"))
        stddev_cents = safe_float(row.get("distribution_stddev_cents"))
        minifig_val = safe_float(row.get("minifig_value_cents"))

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

        price_tier_ord = ordinal_bucket(int(rrp), PRICE_TIERS) if rrp else None

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
            "annual_growth_pct": safe_float(row.get("annual_growth_pct")),
            "rolling_growth_pct": safe_float(row.get("rolling_growth_pct")),
            "growth_90d_pct": safe_float(row.get("growth_90d_pct")),
            "value_new_vs_rrp": value_vs_rrp,
            "theme_rank": safe_float(row.get("theme_rank")),
            "subtheme_avg_growth_pct": safe_float(row.get("subtheme_avg_growth_pct")),
            "distribution_cv": dist_cv,
            "rating_value": rating_num,
            "review_count": safe_float(row.get("review_count")),
            "has_exclusive_minifigs": has_exclusive,
            "minifig_value_ratio": minifig_ratio,
            "price_tier_ordinal": float(price_tier_ord) if price_tier_ord is not None else None,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group D: Keepa / Amazon features (pure)
# ---------------------------------------------------------------------------


def extract_keepa_features(
    keepa_df: pd.DataFrame,
    rrp_map: dict[str, float],
) -> pd.DataFrame:
    """Extract features from pre-loaded Keepa snapshots.

    Args:
        keepa_df: Latest Keepa snapshot data.
        rrp_map: Dict mapping set_number -> rrp_usd_cents.
    """
    if keepa_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in keepa_df.iterrows():
        sn = row["set_number"]
        rrp_usd = rrp_map.get(sn)
        amazon_price = row.get("current_amazon_cents")
        lowest = row.get("lowest_ever_cents")
        highest = row.get("highest_ever_cents")

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
            "keepa_rating": safe_float(row.get("rating")),
            "keepa_review_count": safe_float(row.get("review_count")),
            "keepa_tracking_users": safe_float(row.get("tracking_users")),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group E: Google Trends features (pure)
# ---------------------------------------------------------------------------


def extract_gtrends_features(gt_df: pd.DataFrame) -> pd.DataFrame:
    """Extract features from pre-loaded Google Trends snapshots."""
    if gt_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in gt_df.iterrows():
        rows.append({
            "set_number": row["set_number"],
            "gtrends_peak": safe_float(row.get("peak_value")),
            "gtrends_avg": safe_float(row.get("average_value")),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group F: Shopee saturation features (pure)
# ---------------------------------------------------------------------------


def extract_shopee_features(ss_df: pd.DataFrame) -> pd.DataFrame:
    """Extract features from pre-loaded Shopee saturation data."""
    if ss_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in ss_df.iterrows():
        rows.append({
            "set_number": row["set_number"],
            "shopee_listings": safe_float(row.get("listings_count")),
            "shopee_unique_sellers": safe_float(row.get("unique_sellers")),
            "shopee_price_spread_pct": safe_float(row.get("price_spread_pct")),
            "shopee_saturation_score": safe_float(row.get("saturation_score")),
        })

    return pd.DataFrame(rows)
