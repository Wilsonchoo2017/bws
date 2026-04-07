"""BrickEconomy feature extractor.

Extracts RRP-derived features, growth metrics, ratings, and distribution
stats from BrickEconomy snapshots (respecting the retirement cutoff).
"""

from __future__ import annotations


import pandas as pd

from services.backtesting.cohort import PRICE_TIERS
from services.ml.helpers import ordinal_bucket, parse_rating_string, safe_float
from services.ml.queries import load_be_cutoff_snapshots, load_latest_be_snapshots
from services.ml.types import FeatureMeta
from typing import Any


class BrickEconomyExtractor:
    """Extracts features from BrickEconomy snapshots."""

    @property
    def name(self) -> str:
        return "brickeconomy"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("rrp_usd_cents", "brickeconomy_snapshots", "Retail price USD cents", "int"),
            FeatureMeta("price_per_part", "derived", "RRP USD cents / parts count"),
            FeatureMeta("annual_growth_pct", "brickeconomy_snapshots", "Annual growth %"),
            FeatureMeta("rolling_growth_pct", "brickeconomy_snapshots", "Rolling 12-month growth %"),
            FeatureMeta("growth_90d_pct", "brickeconomy_snapshots", "90-day growth %"),
            FeatureMeta("value_new_vs_rrp", "derived", "Market value (new) / RRP ratio"),
            FeatureMeta("theme_rank", "brickeconomy_snapshots", "Rank within theme/subtheme", "int"),
            FeatureMeta("subtheme_avg_growth_pct", "brickeconomy_snapshots", "Avg growth % for subtheme"),
            FeatureMeta("distribution_cv", "derived", "Price distribution coefficient of variation"),
            FeatureMeta("rating_value", "brickeconomy_snapshots", "User rating (numeric)"),
            FeatureMeta("review_count", "brickeconomy_snapshots", "Number of reviews", "int"),
            FeatureMeta("has_exclusive_minifigs", "brickeconomy_snapshots", "Has exclusive minifigures", "int"),
            FeatureMeta("minifig_value_ratio", "derived", "Minifig value / RRP ratio"),
            FeatureMeta("price_tier_ordinal", "derived", "Price tier bucket (0-3)"),
        )

    def extract(
        self,
        conn: Any,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Load snapshots (with cutoff filtering) and extract features."""
        be_df = load_latest_be_snapshots(conn)

        # For sets with a cutoff, use pre-cutoff snapshots instead
        sets_with_cutoff = base.dropna(subset=["cutoff_year"])
        if not sets_with_cutoff.empty:
            cutoff_snapshots = load_be_cutoff_snapshots(conn, sets_with_cutoff)
            if not cutoff_snapshots.empty:
                be_df = be_df[~be_df["set_number"].isin(cutoff_snapshots["set_number"])]
                be_df = pd.concat([be_df, cutoff_snapshots], ignore_index=True)

        return _compute_be_features(be_df, base)


def _compute_be_features(
    be_df: pd.DataFrame,
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Pure computation of BrickEconomy features from pre-loaded data."""
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

        rating_num = parse_rating_string(row.get("rating_value"))

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
            p_raw = base_row.iloc[0].get("parts_count")
            if pd.notna(p_raw):
                parts = p_raw
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
