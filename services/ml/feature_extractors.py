"""Feature extraction facade for the ML pipeline.

Delegates to the extractors/ plugin package for actual extraction.
Maintains backward compatibility for existing imports.

Feature registration still happens here at import time so the
global feature_registry stays populated for feature_store.py.
"""

import logging
from typing import TYPE_CHECKING

import pandas as pd

from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
from services.ml.extractors import extract_all
from services.ml.feature_registry import register
from services.ml.helpers import compute_cutoff_dates
from services.ml.queries import load_base_metadata as _query_base_metadata

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature registration (executed at import time)
# These populate the global registry used by feature_store.py.
# The actual extraction logic lives in extractors/*.py.
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

# Group G: Keepa full price timeline
register("kpt_below_rrp_pct", "keepa_snapshots", "% of time Amazon price < 98% RRP")
register("kpt_avg_discount", "keepa_snapshots", "Avg Amazon discount from RRP %")
register("kpt_max_discount", "keepa_snapshots", "Max Amazon discount from RRP %")
register("kpt_median_discount", "keepa_snapshots", "Median Amazon discount from RRP %")
register("kpt_price_cv", "keepa_snapshots", "Amazon price coefficient of variation")
register("kpt_price_trend", "keepa_snapshots", "Early vs late price trend %")
register("kpt_price_momentum", "keepa_snapshots", "Last-quarter vs first-quarter price ratio")
register("kpt_price_acceleration", "keepa_snapshots", "Trend change: 2nd half minus 1st half")
register("kpt_months_in_stock", "keepa_snapshots", "Months Amazon listing was in stock")
register("kpt_stockout_count", "keepa_snapshots", "Number of stock-out events")
register("kpt_stockout_pct", "keepa_snapshots", "% of timeline with stock-outs")
register("kpt_bb_premium_pct", "keepa_snapshots", "Buy box premium after stock-out %")
register("kpt_bb_max_premium", "keepa_snapshots", "Max buy box premium vs RRP %")
register("kpt_3p_premium_pct", "keepa_snapshots", "3P FBA avg premium vs Amazon price %")
register("kpt_3p_price_cv", "keepa_snapshots", "3P FBA price coefficient of variation")
register("kpt_rank_median", "keepa_snapshots", "Median sales rank")
register("kpt_rank_trend", "keepa_snapshots", "Sales rank trend (negative = improving)")
register("kpt_rank_cv", "keepa_snapshots", "Sales rank coefficient of variation")
register("kpt_data_months", "keepa_snapshots", "Months of Keepa price data available")
register("kpt_n_price_points", "keepa_snapshots", "Number of price data points")

# Group H: BrickEconomy charts (value chart, candlestick, sales trend)
register("be_value_months", "brickeconomy_snapshots", "Months of BE value history")
register("be_value_trend_pct", "brickeconomy_snapshots", "Overall value trend %")
register("be_value_momentum", "brickeconomy_snapshots", "Recent vs early value ratio")
register("be_value_cv", "brickeconomy_snapshots", "Value chart coefficient of variation")
register("be_value_max_drawdown", "brickeconomy_snapshots", "Max peak-to-trough drawdown %")
register("be_value_recovery", "brickeconomy_snapshots", "Recovery from max drawdown %")
register("be_candle_avg_range_pct", "brickeconomy_snapshots", "Avg candle range / close %")
register("be_candle_bearish_pct", "brickeconomy_snapshots", "% of bearish candles")
register("be_candle_trend_strength", "brickeconomy_snapshots", "Avg body / range ratio")
register("be_candle_upper_shadow_pct", "brickeconomy_snapshots", "Avg upper shadow relative to range %")
register("be_candle_volatility_trend", "brickeconomy_snapshots", "Late vs early candle range change")
register("be_sales_avg_volume", "brickeconomy_snapshots", "Avg monthly transaction volume")
register("be_sales_volume_trend", "brickeconomy_snapshots", "Volume trend: late vs early ratio")
register("be_sales_volume_cv", "brickeconomy_snapshots", "Volume coefficient of variation")
register("be_sales_months_active", "brickeconomy_snapshots", "Months with sales activity")
register("be_future_est_return", "brickeconomy_snapshots", "BE future estimate vs current value ratio")

# Group I: BrickLink monthly sales (pre-retirement momentum)
register("bl_price_trend_pct", "bricklink_monthly_sales", "Price trend % over available history")
register("bl_price_momentum_3m", "bricklink_monthly_sales", "3-month price momentum %")
register("bl_price_momentum_6m", "bricklink_monthly_sales", "6-month price momentum %")
register("bl_price_vs_rrp", "bricklink_monthly_sales", "Latest BL price / RRP ratio")
register("bl_price_cv", "bricklink_monthly_sales", "Price coefficient of variation")
register("bl_price_range_pct", "bricklink_monthly_sales", "(Max - Min) / Mean price %")
register("bl_avg_monthly_sales", "bricklink_monthly_sales", "Avg monthly units sold")
register("bl_sales_trend", "bricklink_monthly_sales", "Sales volume trend ratio")
register("bl_total_quantity", "bricklink_monthly_sales", "Total units sold", "int")
register("bl_months_with_sales", "bricklink_monthly_sales", "Months with at least 1 sale", "int")
register("bl_sales_consistency", "bricklink_monthly_sales", "% of months with sales")
register("bl_avg_spread_pct", "bricklink_monthly_sales", "Avg (max-min)/avg spread %")

# Group J: Google Trends theme-level
register("gt_theme_lego_share", "google_trends_theme_snapshots", "LEGO share of theme search interest")
register("gt_theme_avg_lego", "google_trends_theme_snapshots", "Avg LEGO search interest for theme")
register("gt_theme_peak_lego", "google_trends_theme_snapshots", "Peak LEGO search interest for theme")
register("gt_theme_avg_bare", "google_trends_theme_snapshots", "Avg bare keyword search interest")
register("gt_theme_lego_vs_bare", "google_trends_theme_snapshots", "LEGO interest / bare interest ratio")


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------


def extract_all_features(
    conn: "DuckDBPyConnection",
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Extract all enabled features for the given sets.

    Delegates to the extractors/ plugin package. Each extractor handles
    its own data loading and computation.

    Returns DataFrame indexed by set_number with one column per feature.
    """
    base = _load_base_metadata(conn, set_numbers)
    if base.empty:
        return pd.DataFrame()

    return extract_all(conn, base)


# ---------------------------------------------------------------------------
# Base metadata (shared with extractors and growth model)
# ---------------------------------------------------------------------------


def _load_base_metadata(
    conn: "DuckDBPyConnection",
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Load core set metadata and compute cutoff dates."""
    df = _query_base_metadata(conn, set_numbers)
    return compute_cutoff_dates(df, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)
