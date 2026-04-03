"""Encoding utilities for categorical features.

Pure functions for LOO (leave-one-out) Bayesian encoding and
group statistics computation. Used by the growth model for
theme and subtheme encoding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_group_stats(
    df: pd.DataFrame,
    group_col: str,
    target: pd.Series,
    *,
    min_count: int = 1,
) -> dict:
    """Compute group-level statistics for encoding.

    Args:
        df: DataFrame with the group column.
        group_col: Column name to group by.
        target: Target values (same length as df).
        min_count: Minimum group size to include.

    Returns:
        Dict with 'global_mean' and 'groups' mapping group -> {sum, count}.
    """
    gm = float(target.mean())
    group_df = pd.DataFrame({group_col: df[group_col], "target": target})
    agg = group_df.groupby(group_col)["target"].agg(["sum", "count"])

    groups: dict[str, dict] = {}
    for group, row in agg.iterrows():
        if row["count"] >= min_count:
            groups[group] = {
                "sum": float(row["sum"]),
                "count": int(row["count"]),
            }

    return {"global_mean": gm, "groups": groups}


def loo_bayesian_encode(
    series: pd.Series,
    target: pd.Series,
    stats: dict,
    *,
    alpha: int = 20,
) -> pd.Series:
    """Leave-one-out Bayesian encoding (training mode).

    For each row, computes the group mean excluding that row's target,
    regularized toward the global mean with strength alpha.

    Args:
        series: Group labels (e.g. theme names).
        target: Target values for LOO computation.
        stats: Group statistics from compute_group_stats().
        alpha: Regularization strength (higher = more shrinkage to global mean).

    Returns:
        Series of encoded values.
    """
    gm = stats["global_mean"]
    groups = stats["groups"]

    group_sum = series.map({g: d["sum"] for g, d in groups.items()})
    group_cnt = series.map({g: d["count"] for g, d in groups.items()})

    loo_sum = group_sum - target.values
    loo_cnt = group_cnt - 1

    return pd.Series(
        np.where(
            loo_cnt > 0,
            (loo_sum + alpha * gm) / (loo_cnt + alpha),
            gm,
        ),
        index=series.index,
    )


def group_mean_encode(
    series: pd.Series,
    stats: dict,
    *,
    alpha: int = 20,
) -> pd.Series:
    """Group mean encoding (prediction mode -- no LOO).

    Uses pre-computed statistics to encode group labels.

    Args:
        series: Group labels to encode.
        stats: Group statistics from compute_group_stats().
        alpha: Regularization strength.

    Returns:
        Series of encoded values.
    """
    gm = stats["global_mean"]
    groups = stats["groups"]

    return series.map(
        {g: (d["sum"] + alpha * gm) / (d["count"] + alpha) for g, d in groups.items()}
    ).fillna(gm)


def group_size_encode(
    series: pd.Series,
    stats: dict,
    default: float = 0,
) -> pd.Series:
    """Encode group sizes from pre-computed statistics.

    Args:
        series: Group labels.
        stats: Group statistics from compute_group_stats().
        default: Default value for unknown groups.

    Returns:
        Series of group sizes.
    """
    groups = stats["groups"]
    return series.map({g: d["count"] for g, d in groups.items()}).fillna(default)
