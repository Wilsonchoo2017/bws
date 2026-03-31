"""Evaluation framework for comparing scoring strategies.

Computes standardized metrics (APR, hit rate, Sharpe ratio, quintile
spread) across different weight strategies, enabling data-driven
comparison between hand-tuned and ML-optimized approaches.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from services.backtesting.types import SIGNAL_NAMES


@dataclass(frozen=True)
class StrategyMetrics:
    """Evaluation metrics for one scoring strategy."""

    name: str
    mean_apr: float
    median_apr: float
    hit_rate: float
    sharpe_ratio: float
    quintile_spread: float
    top_quintile_mean_apr: float
    bottom_quintile_mean_apr: float
    n_samples: int


def evaluate_strategy(
    df: pd.DataFrame,
    weights: dict[str, float],
    target_column: str,
    strategy_name: str,
) -> StrategyMetrics:
    """Score all items using given weights, compute quintile metrics.

    Args:
        df: DataFrame with signal columns and target_column.
        weights: Signal name -> weight mapping.
        target_column: Column with actual APR values.
        strategy_name: Label for this strategy.

    Returns:
        StrategyMetrics with evaluation results.
    """
    valid = df.dropna(subset=[target_column]).copy()
    if valid.empty:
        return _empty_metrics(strategy_name)

    # Score each item
    valid = valid.copy()
    valid["_score"] = _weighted_score(valid, weights)
    actual = valid[target_column].values

    # Overall metrics
    mean_apr = float(np.nanmean(actual))
    median_apr = float(np.nanmedian(actual))
    std_apr = float(np.nanstd(actual))
    sharpe = mean_apr / std_apr if std_apr > 0 else 0.0

    # Quintile analysis: sort by score, split into 5 bins
    order = np.argsort(valid["_score"].values)[::-1]
    sorted_actual = actual[order]

    n = len(sorted_actual)
    if n < 5:
        return _empty_metrics(strategy_name, n_samples=n)

    q_size = max(1, n // 5)
    top_q = sorted_actual[:q_size]
    bottom_q = sorted_actual[-q_size:]

    top_mean = float(np.nanmean(top_q))
    bottom_mean = float(np.nanmean(bottom_q))
    hit_rate = float(np.nanmean(top_q > 0)) if len(top_q) > 0 else 0.0

    return StrategyMetrics(
        name=strategy_name,
        mean_apr=mean_apr,
        median_apr=median_apr,
        hit_rate=hit_rate,
        sharpe_ratio=sharpe,
        quintile_spread=top_mean - bottom_mean,
        top_quintile_mean_apr=top_mean,
        bottom_quintile_mean_apr=bottom_mean,
        n_samples=n,
    )


def evaluate_all_strategies(
    df: pd.DataFrame,
    strategies: dict[str, dict[str, float]],
    target_column: str,
) -> list[StrategyMetrics]:
    """Evaluate multiple weight strategies and return sorted by quintile spread.

    Args:
        df: DataFrame with signal columns and target_column.
        strategies: Name -> weights mapping for each strategy.
        target_column: Column with actual APR values.

    Returns:
        List of StrategyMetrics sorted by quintile_spread descending.
    """
    results = [
        evaluate_strategy(df, weights, target_column, name)
        for name, weights in strategies.items()
    ]
    results.sort(key=lambda m: m.quintile_spread, reverse=True)
    return results


def print_evaluation_report(metrics_list: list[StrategyMetrics]) -> None:
    """Print a formatted comparison table of strategy metrics."""
    if not metrics_list:
        print("  No strategies to compare.")
        return

    # Header
    print(f"\n  {'Strategy':15s}  {'Top Q APR':>10s}  {'Bot Q APR':>10s}  "
          f"{'Spread':>8s}  {'Hit Rate':>9s}  {'Sharpe':>7s}  {'N':>5s}")
    print(f"  {'-' * 15}  {'-' * 10}  {'-' * 10}  "
          f"{'-' * 8}  {'-' * 9}  {'-' * 7}  {'-' * 5}")

    for m in metrics_list:
        print(
            f"  {m.name:15s}  {m.top_quintile_mean_apr:>+9.1%}  "
            f"{m.bottom_quintile_mean_apr:>+9.1%}  "
            f"{m.quintile_spread:>+7.1%}  "
            f"{m.hit_rate:>8.0%}  "
            f"{m.sharpe_ratio:>7.2f}  "
            f"{m.n_samples:>5d}"
        )

    # Winner annotation
    if len(metrics_list) >= 2:
        best = metrics_list[0]
        second = metrics_list[1]
        spread_diff = best.quintile_spread - second.quintile_spread
        print(f"\n  Winner: {best.name} "
              f"(+{spread_diff:.1%} quintile spread over {second.name})")


def print_weight_comparison(
    handtuned: dict[str, float],
    ml_weights: dict[str, float],
    model_name: str,
) -> None:
    """Print side-by-side weight comparison."""
    print(f"\n  {'Signal':25s}  {'Hand-tuned':>10s}  {model_name:>10s}  {'Delta':>8s}")
    print(f"  {'-' * 25}  {'-' * 10}  {'-' * 10}  {'-' * 8}")

    all_signals = sorted(
        set(handtuned.keys()) | set(ml_weights.keys()),
        key=lambda s: abs(ml_weights.get(s, 0) - handtuned.get(s, 0)),
        reverse=True,
    )

    for signal in all_signals:
        ht = handtuned.get(signal, 1.0)
        ml = ml_weights.get(signal, 1.0)
        delta = ml - ht
        marker = " *" if abs(delta) > 0.3 else ""
        print(f"  {signal:25s}  {ht:>10.2f}  {ml:>10.2f}  {delta:>+7.2f}{marker}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _weighted_score(
    df: pd.DataFrame,
    weights: dict[str, float],
) -> np.ndarray:
    """Compute weighted composite score for each row."""
    scores = np.zeros(len(df))
    weight_sum = 0.0

    for signal, weight in weights.items():
        if signal not in df.columns:
            continue
        values = df[signal].fillna(0).values
        scores += values * weight
        weight_sum += abs(weight)

    if weight_sum > 0:
        scores /= weight_sum

    return scores


def _empty_metrics(name: str, n_samples: int = 0) -> StrategyMetrics:
    """Return zeroed-out metrics for edge cases."""
    return StrategyMetrics(
        name=name,
        mean_apr=0.0,
        median_apr=0.0,
        hit_rate=0.0,
        sharpe_ratio=0.0,
        quintile_spread=0.0,
        top_quintile_mean_apr=0.0,
        bottom_quintile_mean_apr=0.0,
        n_samples=n_samples,
    )
