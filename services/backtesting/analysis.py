"""Statistical analysis of backtesting results.

Computes correlations, feature importance, quintile analysis,
and signal combination discovery.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from services.backtesting.types import MODIFIER_NAMES, SIGNAL_NAMES, TradeResult


@dataclass(frozen=True)
class AnalysisResults:
    """Complete analysis output for one strategy."""

    correlations: pd.DataFrame
    feature_importance: pd.Series | None
    quintile_returns: dict[str, pd.DataFrame]
    best_combinations: list[dict] | None
    sample_size: int


def trades_to_dataframe(trades: list[TradeResult]) -> pd.DataFrame:
    """Convert TradeResult list to a flat DataFrame for analysis."""
    rows = []
    for trade in trades:
        row = {
            "item_id": trade.item_id,
            "entry_year": trade.entry_year,
            "entry_month": trade.entry_month,
            "entry_price_cents": trade.entry_price_cents,
        }
        # Add signals
        for signal in SIGNAL_NAMES:
            row[signal] = getattr(trade.signals, signal)
        # Add modifiers
        for mod in MODIFIER_NAMES:
            row[mod] = getattr(trade.signals, mod)
        # Add returns
        for key, val in trade.returns.items():
            row[f"return_{key}"] = val

        rows.append(row)

    return pd.DataFrame(rows)


def compute_correlations(
    df: pd.DataFrame,
    return_columns: list[str],
) -> pd.DataFrame:
    """Compute Spearman rank correlation of each signal with return columns.

    Returns DataFrame: rows=signals, columns=return horizons.
    """
    signal_cols = [c for c in SIGNAL_NAMES if c in df.columns]
    results = {}

    for ret_col in return_columns:
        if ret_col not in df.columns:
            continue
        corrs = {}
        for sig in signal_cols:
            valid = df[[sig, ret_col]].dropna()
            if len(valid) < 5:
                corrs[sig] = np.nan
                continue
            corrs[sig] = valid[sig].corr(valid[ret_col], method="spearman")
        results[ret_col] = corrs

    return pd.DataFrame(results)


def compute_feature_importance(
    df: pd.DataFrame,
    target_col: str,
) -> pd.Series | None:
    """Compute feature importance using gradient boosted trees.

    Uses HistGradientBoostingRegressor which handles NaN natively.
    Returns Series indexed by signal names, sorted by importance.
    """
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.inspection import permutation_importance
    except ImportError:
        return None

    signal_cols = [c for c in SIGNAL_NAMES if c in df.columns]
    valid = df[signal_cols + [target_col]].dropna(subset=[target_col])

    if len(valid) < 10:
        return None

    x = valid[signal_cols].fillna(-1).values
    y = valid[target_col].values

    if len(set(y)) < 2:
        return None

    model = HistGradientBoostingRegressor(
        max_iter=100,
        max_depth=4,
        random_state=42,
    )
    model.fit(x, y)

    perm = permutation_importance(model, x, y, n_repeats=10, random_state=42)
    importance = pd.Series(
        perm.importances_mean,
        index=signal_cols,
    ).sort_values(ascending=False)

    return importance


def compute_quintile_returns(
    df: pd.DataFrame,
    signal: str,
    return_col: str,
) -> pd.DataFrame | None:
    """Split items into quintiles by signal score, compare median returns.

    A good signal shows monotonically increasing returns across quintiles.
    """
    valid = df[[signal, return_col]].dropna()
    if len(valid) < 10:
        return None

    try:
        valid = valid.copy()
        valid["quintile"] = pd.qcut(
            valid[signal], q=5, labels=["Q1(low)", "Q2", "Q3", "Q4", "Q5(high)"],
            duplicates="drop",
        )
    except ValueError:
        # Not enough unique values for 5 quintiles
        try:
            valid["quintile"] = pd.qcut(
                valid[signal], q=3, labels=["Low", "Mid", "High"],
                duplicates="drop",
            )
        except ValueError:
            return None

    result = valid.groupby("quintile", observed=True)[return_col].agg(
        ["median", "mean", "count"]
    )
    return result


def find_best_combinations(
    df: pd.DataFrame,
    target_col: str,
    top_k: int = 5,
) -> list[dict] | None:
    """Find best 2-signal combinations by correlation with returns.

    Tests equal-weighted averages of signal pairs.
    """
    signal_cols = [c for c in SIGNAL_NAMES if c in df.columns]
    valid = df[signal_cols + [target_col]].dropna(subset=[target_col])

    if len(valid) < 10:
        return None

    combos = []
    for i, sig_a in enumerate(signal_cols):
        for sig_b in signal_cols[i + 1 :]:
            pair_valid = valid[[sig_a, sig_b, target_col]].dropna()
            if len(pair_valid) < 5:
                continue

            composite = (pair_valid[sig_a] + pair_valid[sig_b]) / 2
            corr = composite.corr(pair_valid[target_col], method="spearman")

            if not np.isnan(corr):
                combos.append({
                    "signals": (sig_a, sig_b),
                    "correlation": corr,
                    "sample_size": len(pair_valid),
                })

    combos.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return combos[:top_k]


def analyze_strategy(
    df: pd.DataFrame,
    return_columns: list[str],
    primary_return: str,
) -> AnalysisResults:
    """Run complete analysis for one strategy (flip or hold)."""
    correlations = compute_correlations(df, return_columns)
    importance = compute_feature_importance(df, primary_return)

    quintiles = {}
    for signal in SIGNAL_NAMES:
        if signal in df.columns:
            result = compute_quintile_returns(df, signal, primary_return)
            if result is not None:
                quintiles[signal] = result

    combinations = find_best_combinations(df, primary_return)

    valid_count = df[primary_return].dropna().shape[0]

    return AnalysisResults(
        correlations=correlations,
        feature_importance=importance,
        quintile_returns=quintiles,
        best_combinations=combinations,
        sample_size=valid_count,
    )
