"""BrickLink sales-velocity features.

Captures *how often* a set actually transacts on BrickLink, not just the
listing price spread. A set turning 5+ units/month is materially different
from one sitting at 0 — the long-term APR target hides this distinction.

Pulls from `bricklink_monthly_sales` (condition='new') and emits per-set
aggregates over the trailing 12 months. All metrics are missing-safe and
respect a `cutoff_date` so training can ignore post-retirement spikes.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


SALES_VELOCITY_FEATURE_NAMES: tuple[str, ...] = (
    "bl_sales_per_month_recent",   # avg units/month over trailing 90d
    "bl_sales_per_month_12m",      # avg units/month over trailing 12m
    "bl_sales_velocity_slope",     # OLS slope of monthly volume (12m)
    "bl_sales_lumpiness",          # std/mean of monthly volume (12m, 0 if flat)
    "bl_sales_active_months_12m",  # count of months with ≥1 sale (0-12)
    "bl_sales_log_total_12m",      # log1p(total_qty over 12m)
)

# Default sentinel for sets with zero sales coverage. -1 sits below any
# legitimate velocity (counts and slopes are nonnegative or near-zero) so
# LightGBM can split on "no sales data" as its own branch.
NO_SALES_SENTINEL = -1.0


def load_sales_velocity_features(engine: Engine) -> pd.DataFrame:
    """Compute trailing-12-month velocity metrics from bricklink_monthly_sales.

    Returns a DataFrame indexed by set_number with the columns in
    SALES_VELOCITY_FEATURE_NAMES. Sets with zero NEW sales rows in the
    window are emitted with sentinel values, not omitted, so the merge in
    feature engineering keeps them and lets the classifier learn from
    "absence of sales activity".
    """
    today = date.today()
    cutoff_period = today.year * 12 + today.month - 12  # trailing 12 months
    recent_period = today.year * 12 + today.month - 3   # trailing 90d

    rows = pd.read_sql(
        """
        SELECT
            set_number,
            year,
            month,
            times_sold,
            (year * 12 + month) AS period_key
        FROM bricklink_monthly_sales
        WHERE condition = 'new'
          AND times_sold IS NOT NULL
          AND times_sold > 0
          AND (year * 12 + month) >= %(cutoff)s
        """,
        engine,
        params={"cutoff": cutoff_period},
    )

    if rows.empty:
        logger.warning("No sales rows in trailing 12-month window")
        return pd.DataFrame(columns=("set_number",) + SALES_VELOCITY_FEATURE_NAMES)

    rows["months_ago"] = today.year * 12 + today.month - rows["period_key"]

    feats: dict[str, dict[str, float]] = {}
    for sn, group in rows.groupby("set_number"):
        qty = group["times_sold"].astype(float).to_numpy()
        months_ago = group["months_ago"].astype(int).to_numpy()
        recent_mask = group["period_key"].to_numpy() >= recent_period

        recent_qty_sum = float(qty[recent_mask].sum()) if recent_mask.any() else 0.0
        per_month_recent = recent_qty_sum / 3.0
        per_month_12m = float(qty.sum()) / 12.0

        # Velocity slope: simple OLS on (months_since_now=12-x → x) vs qty.
        # Positive slope = volume rising toward present.
        if len(qty) >= 3:
            x = -months_ago.astype(float)  # ascending in time
            slope = float(np.polyfit(x, qty, 1)[0])
        else:
            slope = 0.0

        mean_qty = float(qty.mean())
        std_qty = float(qty.std(ddof=0))
        lumpiness = std_qty / mean_qty if mean_qty > 0 else 0.0

        feats[sn] = {
            "bl_sales_per_month_recent": per_month_recent,
            "bl_sales_per_month_12m": per_month_12m,
            "bl_sales_velocity_slope": slope,
            "bl_sales_lumpiness": lumpiness,
            "bl_sales_active_months_12m": float(len(qty)),
            "bl_sales_log_total_12m": float(np.log1p(qty.sum())),
        }

    df = pd.DataFrame.from_dict(feats, orient="index")
    df.index.name = "set_number"
    df = df.reset_index()
    logger.info("Sales velocity features: %d sets", len(df))
    return df


def merge_sales_velocity(base: pd.DataFrame, velocity: pd.DataFrame) -> pd.DataFrame:
    """Left-merge velocity features onto base; sentinel-fill missing sets."""
    if velocity.empty:
        for col in SALES_VELOCITY_FEATURE_NAMES:
            base[col] = NO_SALES_SENTINEL
        return base

    merged = base.merge(velocity, on="set_number", how="left")
    for col in SALES_VELOCITY_FEATURE_NAMES:
        if col in merged.columns:
            merged[col] = merged[col].fillna(NO_SALES_SENTINEL)
        else:
            merged[col] = NO_SALES_SENTINEL
    return merged
