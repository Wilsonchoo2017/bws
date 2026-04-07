"""Feature engineering for the growth model.

Tier 1: Intrinsic features from set metadata + theme/subtheme encodings.
Tier 2: Adds Keepa timeline features (Amazon pricing signals).
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from config.ml import LICENSED_THEMES
from services.ml.encodings import (
    compute_group_stats,
    group_mean_encode,
    group_size_encode,
    loo_bayesian_encode,
)

logger = logging.getLogger(__name__)

TIER1_FEATURES: tuple[str, ...] = (
    # Core set attributes
    "log_rrp", "log_parts", "price_per_part", "mfigs", "minifig_density",
    "price_tier", "is_licensed", "usd_gbp_ratio", "usd_vs_mean", "currency_cv",
    # Rating & reviews (NEW)
    "rating_value", "log_reviews", "rating_x_reviews",
    # Distribution & value signals (NEW)
    "dist_cv", "has_designer", "mfig_value_to_rrp",
    # Lifecycle features (from BrickTalk gap analysis)
    "shelf_life_months", "retire_quarter", "retires_before_q4",
    # Theme/subtheme encodings
    "theme_bayes", "theme_size", "theme_growth_std",
    "subtheme_loo", "sub_size",
    # Cohort review rankings (non-leaky: reviews available at prediction time)
    "review_rank_in_year", "review_rank_in_quarter",
    "review_rank_in_price_tier", "review_rank_in_pieces_tier",
    "review_rank_in_theme", "review_rank_in_retire_year",
    # BrickTalk gap analysis signals
    "high_price_barrier", "shelf_life_x_reviews",
    # Feature interactions
    "theme_x_price", "licensed_x_parts", "rating_x_price",
)

# Growth rankings are computed for analysis only (leaky -- derived from target).
# Stored separately so they can be used in research notebooks but NOT in training.
GROWTH_RANK_FEATURES: tuple[str, ...] = (
    "growth_rank_in_year", "growth_rank_in_quarter",
    "growth_rank_in_price_tier", "growth_rank_in_pieces_tier",
    "growth_rank_in_theme", "growth_rank_in_retire_year",
)

TIER2_FEATURES: tuple[str, ...] = TIER1_FEATURES + (
    "kp_below_rrp_pct", "kp_avg_discount", "kp_max_discount",
    "kp_price_trend", "kp_price_cv", "kp_months_stock", "kp_bb_premium",
)


def _add_cohort_rankings(
    df: pd.DataFrame,
    training_target: pd.Series | None = None,
) -> pd.DataFrame:
    """Add within-cohort percentile rankings for reviews and growth.

    Cohorts:
    - Release year: sets released in the same year
    - Release quarter: same year + quarter (3-month bucket)
    - Price tier: same price bracket
    - Theme: same theme
    - Retirement year: sets retiring in the same year

    Rankings are percentile ranks (0-1) within each cohort.
    Growth rankings use LOO (exclude self) during training to avoid leakage.
    Review rankings are non-leaky (available at prediction time).
    """
    result = df.copy()

    yr_released = pd.to_numeric(result.get("year_released"), errors="coerce")
    yr_retired = pd.to_numeric(result.get("year_retired"), errors="coerce")
    reviews = pd.to_numeric(result.get("review_count"), errors="coerce")
    rrp = pd.to_numeric(result.get("rrp_usd_cents"), errors="coerce") / 100

    # Build cohort group columns
    release_date = pd.to_datetime(result.get("release_date"), errors="coerce")
    quarter = release_date.dt.quarter.fillna(1).astype(int)

    parts = pd.to_numeric(result.get("parts_count"), errors="coerce")

    cohort_groups = {
        "year": yr_released,
        "quarter": yr_released.astype(str) + "Q" + quarter.astype(str),
        "price_tier": pd.cut(
            rrp, bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999],
            labels=range(1, 9),
        ).astype(str),
        "pieces_tier": pd.qcut(
            parts, q=8, duplicates="drop",
        ).astype(str),
        "theme": result.get("theme", pd.Series(dtype=str)),
        "retire_year": yr_retired,
    }

    for cohort_name, group_col in cohort_groups.items():
        # Review rank (non-leaky)
        result[f"review_rank_in_{cohort_name}"] = result.groupby(group_col)["review_count"].rank(
            pct=True, method="average", na_option="bottom"
        )

        # Growth rank (LOO during training to prevent leakage)
        if training_target is not None:
            result[f"growth_rank_in_{cohort_name}"] = _loo_rank(
                training_target.values, group_col,
            )
        else:
            result[f"growth_rank_in_{cohort_name}"] = np.nan

    return result


def _loo_rank(
    target: np.ndarray,
    group_col: pd.Series,
) -> pd.Series:
    """Compute leave-one-out percentile rank within each group.

    For each row, rank its target value among all OTHER rows in the same group.
    Returns percentile rank (0-1).
    """
    ranks = pd.Series(np.nan, index=group_col.index, dtype=float)

    for group_val, idx in group_col.groupby(group_col).groups.items():
        if pd.isna(group_val) or len(idx) < 2:
            continue
        group_targets = target[idx]
        for i, pos in enumerate(idx):
            others = np.delete(group_targets, i)
            rank = (others < group_targets[i]).sum() / len(others)
            ranks.iloc[pos] = rank

    return ranks


def engineer_intrinsic_features(
    df: pd.DataFrame,
    *,
    training_target: pd.Series | None = None,
    theme_stats: dict | None = None,
    subtheme_stats: dict | None = None,
) -> tuple[pd.DataFrame, dict | None, dict | None]:
    """Build Tier 1 intrinsic features.

    In training mode (training_target provided): computes LOO encodings.
    In prediction mode (stats provided): uses pre-computed values.

    Returns (df_with_features, theme_stats, subtheme_stats).
    """
    result = df.copy()

    # Numeric conversions
    for col in ("parts_count", "minifig_count", "rrp_usd_cents",
                "rrp_gbp_cents", "review_count", "pieces", "minifigs",
                "rating_value"):
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    parts_raw = pd.to_numeric(
        result["parts_count"].fillna(result.get("pieces", 0)), errors="coerce"
    ).fillna(0)
    rrp_raw = pd.to_numeric(result["rrp_usd_cents"], errors="coerce").fillna(0)
    mfigs_raw = pd.to_numeric(
        result.get("minifig_count", pd.Series(0, index=result.index)).fillna(
            result.get("minifigs", pd.Series(0, index=result.index))
        ), errors="coerce"
    ).fillna(0)

    # Derived features
    result["log_rrp"] = np.log1p(rrp_raw)
    result["log_parts"] = np.log1p(parts_raw)
    result["price_per_part"] = np.where(parts_raw > 0, rrp_raw / parts_raw, np.nan)
    result["mfigs"] = mfigs_raw
    result["minifig_density"] = np.where(
        parts_raw > 0, mfigs_raw / parts_raw * 100, np.nan
    )
    result["price_tier"] = pd.cut(
        rrp_raw / 100,
        bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999],
        labels=range(1, 9),
    ).astype(float)
    result["is_licensed"] = result["theme"].isin(LICENSED_THEMES).astype(int)

    gbp = result["rrp_gbp_cents"].fillna(0) if "rrp_gbp_cents" in result.columns else 0
    result["usd_gbp_ratio"] = np.where(gbp > 0, rrp_raw / gbp, np.nan)

    # Multi-currency pricing features
    price_cols = {
        "usd": rrp_raw,
        "gbp_usd": pd.to_numeric(result.get("rrp_gbp_cents"), errors="coerce").fillna(0) * 1.27,
        "eur_usd": pd.to_numeric(result.get("rrp_eur_cents"), errors="coerce").fillna(0) * 1.08,
        "cad_usd": pd.to_numeric(result.get("rrp_cad_cents"), errors="coerce").fillna(0) * 0.74,
        "aud_usd": pd.to_numeric(result.get("rrp_aud_cents"), errors="coerce").fillna(0) * 0.66,
    }
    prices_df = pd.DataFrame(price_cols, index=result.index).replace(0, np.nan)
    prices_mean = prices_df.mean(axis=1)
    result["usd_vs_mean"] = np.where(prices_mean > 0, rrp_raw / prices_mean, np.nan)
    result["currency_cv"] = prices_df.std(axis=1) / prices_mean

    # New features: rating, reviews, distribution, designer
    rating = pd.to_numeric(result.get("rating_value"), errors="coerce")
    reviews = pd.to_numeric(result.get("review_count"), errors="coerce")
    result["log_reviews"] = np.log1p(reviews)
    result["rating_x_reviews"] = rating * result["log_reviews"]

    dist_mean = pd.to_numeric(result.get("distribution_mean_cents"), errors="coerce")
    dist_std = pd.to_numeric(result.get("distribution_stddev_cents"), errors="coerce")
    result["dist_cv"] = np.where(dist_mean > 0, dist_std / dist_mean, np.nan)

    mfig_val = pd.to_numeric(result.get("minifig_value_cents"), errors="coerce") / 100
    result["mfig_value_to_rrp"] = np.where(
        rrp_raw > 0, mfig_val / (rrp_raw / 100), np.nan
    )
    result["has_designer"] = result.get("designer", pd.Series(dtype=str)).notna().astype(int)

    # Lifecycle features (shelf life, retirement timing)
    release_dt = pd.to_datetime(result.get("release_date"), errors="coerce")
    retired_dt = pd.to_datetime(result.get("retired_date"), errors="coerce")
    # Fallback: approximate retired_date from year_retired (July 1 of that year)
    yr_retired = pd.to_numeric(result.get("year_retired"), errors="coerce")
    retired_dt_approx = pd.to_datetime(
        yr_retired.dropna().astype(int).astype(str) + "-07-01", errors="coerce"
    ).reindex(result.index)
    retired_dt = retired_dt.fillna(retired_dt_approx)

    shelf_days = (retired_dt - release_dt).dt.days
    result["shelf_life_months"] = np.where(
        shelf_days > 0, shelf_days / 30.44, np.nan
    )
    result["retire_quarter"] = retired_dt.dt.quarter.astype(float)
    result["retires_before_q4"] = np.where(
        retired_dt.notna(), (retired_dt.dt.month < 10).astype(float), np.nan
    )

    # Cohort ranking features
    result = _add_cohort_rankings(result, training_target)

    # Theme encoding using encodings module
    if training_target is not None and theme_stats is None:
        raw_stats = compute_group_stats(result, "theme", training_target)
        # Compute per-theme growth std for theme_growth_std feature
        theme_std_map = training_target.groupby(result["theme"]).std().to_dict()
        theme_stats = {
            "global_mean": raw_stats["global_mean"],
            "alpha": 20,
            "themes": raw_stats["groups"],
            "theme_std": theme_std_map,
        }
        result["theme_bayes"] = loo_bayesian_encode(
            result["theme"], training_target, raw_stats, alpha=20
        )
        result["theme_size"] = group_size_encode(result["theme"], raw_stats, default=1)
        result["theme_growth_std"] = result["theme"].map(theme_std_map).fillna(0)
    elif theme_stats is not None:
        adapted_stats = {"global_mean": theme_stats["global_mean"], "groups": theme_stats["themes"]}
        result["theme_bayes"] = group_mean_encode(
            result["theme"], adapted_stats, alpha=theme_stats.get("alpha", 20)
        )
        result["theme_size"] = group_size_encode(result["theme"], adapted_stats, default=1)
        result["theme_growth_std"] = result["theme"].map(
            theme_stats.get("theme_std", {})
        ).fillna(0)

    # Subtheme encoding
    if training_target is not None and subtheme_stats is None:
        raw_sub_stats = compute_group_stats(
            result, "subtheme", training_target, min_count=3
        )
        subtheme_stats = {
            "global_mean": raw_sub_stats["global_mean"],
            "subthemes": raw_sub_stats["groups"],
        }
        adapted_sub = {"global_mean": raw_sub_stats["global_mean"], "groups": raw_sub_stats["groups"]}
        result["subtheme_loo"] = loo_bayesian_encode(
            result["subtheme"], training_target, adapted_sub, alpha=0
        )
        result["sub_size"] = group_size_encode(result["subtheme"], adapted_sub)
    elif subtheme_stats is not None:
        adapted_sub = {"global_mean": subtheme_stats["global_mean"], "groups": subtheme_stats["subthemes"]}
        result["subtheme_loo"] = group_mean_encode(
            result["subtheme"], adapted_sub, alpha=0
        )
        result["sub_size"] = group_size_encode(result["subtheme"], adapted_sub)

    # BrickTalk gap analysis: high price barrier reduces investor competition
    result["high_price_barrier"] = (rrp_raw > 30000).astype(int)  # >$300

    # BrickTalk gap analysis: shelf life interacts with demand (reviews as proxy)
    result["shelf_life_x_reviews"] = result["shelf_life_months"] * result["log_reviews"]

    # Feature interactions (computed after theme encoding so theme_bayes exists)
    if "theme_bayes" in result.columns:
        result["theme_x_price"] = result["theme_bayes"] * result["log_rrp"]
        result["licensed_x_parts"] = result["is_licensed"] * result["log_parts"]
        result["rating_x_price"] = pd.to_numeric(
            result.get("rating_value"), errors="coerce"
        ) * result["log_rrp"]

    return result, theme_stats, subtheme_stats


def engineer_keepa_features(
    df: pd.DataFrame,
    keepa_df: pd.DataFrame,
    *,
    cutoff_dates: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Add Tier 2 Keepa timeline features to the DataFrame.

    Args:
        cutoff_dates: Optional mapping of set_number -> cutoff date string
            (YYYY-MM). When provided, only Keepa price points BEFORE the
            cutoff are used, preventing temporal leakage from post-retirement
            data.
    """
    result = df.copy()
    keepa_feats: dict[str, dict] = {}

    rrp_lookup = dict(zip(
        result["set_number"],
        pd.to_numeric(result["rrp_usd_cents"], errors="coerce").fillna(0),
    ))

    for _, kr in keepa_df.iterrows():
        sn = kr["set_number"]
        amz_raw = kr["amazon_price_json"]
        amz = json.loads(amz_raw) if isinstance(amz_raw, str) else amz_raw
        if not isinstance(amz, list) or len(amz) < 5:
            continue

        # Apply temporal cutoff if available
        cutoff = (cutoff_dates or {}).get(sn)

        prices: list[float] = []
        oos_date: str | None = None
        last_p: float | None = None

        for point in amz:
            # Skip points after cutoff date
            if cutoff and isinstance(point[0], str) and point[0][:7] > cutoff:
                break
            if point[1] is not None and point[1] > 0:
                prices.append(float(point[1]))
                last_p = float(point[1])
            elif point[1] is None and last_p is not None and oos_date is None:
                oos_date = point[0]

        if not prices:
            continue

        set_rrp = rrp_lookup.get(sn, 0)
        if set_rrp <= 0:
            continue

        rec: dict[str, float] = {
            "kp_price_cv": float(np.std(prices) / np.mean(prices)) if np.mean(prices) > 0 else 0,
            "kp_below_rrp_pct": sum(1 for p in prices if p < set_rrp * 0.98) / len(prices) * 100,
            "kp_avg_discount": (set_rrp - np.mean(prices)) / set_rrp * 100,
            "kp_max_discount": (set_rrp - min(prices)) / set_rrp * 100,
        }

        if len(prices) >= 6:
            early = np.mean(prices[:3])
            late = np.mean(prices[-3:])
            rec["kp_price_trend"] = (late - early) / early * 100 if early > 0 else 0

        if oos_date:
            try:
                d1 = pd.to_datetime(amz[0][0])
                d2 = pd.to_datetime(oos_date)
                rec["kp_months_stock"] = (d2 - d1).days / 30
            except (ValueError, TypeError):
                pass

            # kp_bb_premium uses post-OOS data -- only include if no cutoff
            # (i.e. prediction mode for active sets, not training)
            if not cutoff:
                bb_raw = kr.get("buy_box_json")
                bb = json.loads(bb_raw) if isinstance(bb_raw, str) else (bb_raw or [])
                if isinstance(bb, list):
                    for point in bb:
                        if (len(point) >= 2 and point[0] >= oos_date
                                and point[1] and point[1] > 0):
                            rec["kp_bb_premium"] = (point[1] - set_rrp) / set_rrp * 100
                            break

        keepa_feats[sn] = rec

    for feat in ("kp_below_rrp_pct", "kp_avg_discount", "kp_max_discount",
                 "kp_price_trend", "kp_price_cv", "kp_months_stock", "kp_bb_premium"):
        result[feat] = result["set_number"].map(
            lambda sn, f=feat: keepa_feats.get(sn, {}).get(f, np.nan)
        )

    return result
