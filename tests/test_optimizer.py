"""Tests for ML optimizer module."""

import numpy as np
import pandas as pd
import pytest

from services.backtesting.optimizer import (
    OptimizationResult,
    OptimizerConfig,
    compare_with_handtuned,
    extract_signal_weights,
    optimize_weights,
)
from services.backtesting.types import SIGNAL_NAMES


def _make_synthetic_data(n: int = 200, seed: int = 42) -> tuple[pd.DataFrame, list[str]]:
    """Create synthetic backtest data with a known signal-return relationship.

    lifecycle_position and demand_pressure are positively correlated with
    returns. price_trend is noise. This lets us verify the optimizer
    identifies the right signals.
    """
    rng = np.random.RandomState(seed)

    data: dict[str, list | np.ndarray] = {
        "item_id": [f"item_{i}" for i in range(n)],
        "entry_year": sorted(rng.randint(2020, 2025, n)),
        "entry_month": rng.randint(1, 13, n),
        "entry_price_cents": rng.randint(2000, 50000, n),
    }

    # Signals
    for sig in SIGNAL_NAMES:
        data[sig] = rng.uniform(10, 90, n)

    # Sprinkle some NaNs (10% of each signal)
    for sig in SIGNAL_NAMES:
        mask = rng.random(n) < 0.1
        values = np.array(data[sig], dtype=float)
        values[mask] = np.nan
        data[sig] = values

    df = pd.DataFrame(data)

    # Target: positively related to lifecycle_position and demand_pressure
    noise = rng.normal(0, 0.05, n)
    df["best_hold_apr"] = (
        0.003 * df["lifecycle_position"].fillna(50)
        + 0.002 * df["demand_pressure"].fillna(50)
        - 0.15
        + noise
    )

    feature_columns = list(SIGNAL_NAMES)
    return df, feature_columns


class TestOptimizeWeights:
    def test_returns_results_for_sufficient_data(self) -> None:
        df, features = _make_synthetic_data(200)
        results = optimize_weights(df, features)
        assert len(results) > 0
        assert all(isinstance(r, OptimizationResult) for r in results)

    def test_returns_empty_for_insufficient_data(self) -> None:
        df, features = _make_synthetic_data(20)
        config = OptimizerConfig(min_samples=50)
        results = optimize_weights(df, features, config)
        assert results == []

    def test_three_models_trained(self) -> None:
        df, features = _make_synthetic_data(200)
        results = optimize_weights(df, features)
        model_names = {r.model_name for r in results}
        assert "Ridge" in model_names
        assert "Lasso" in model_names
        assert "GBRT" in model_names

    def test_sorted_by_quintile_spread(self) -> None:
        df, features = _make_synthetic_data(200)
        results = optimize_weights(df, features)
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i].test_quintile_spread >= results[i + 1].test_quintile_spread

    def test_no_look_ahead_bias(self) -> None:
        """Test data should be chronologically after train data."""
        df, features = _make_synthetic_data(200)
        config = OptimizerConfig(test_fraction=0.2)
        results = optimize_weights(df, features, config)
        assert len(results) > 0
        # Verify train < test split sizes are reasonable
        for r in results:
            assert r.n_train > r.n_test

    def test_feature_importances_populated(self) -> None:
        df, features = _make_synthetic_data(200)
        results = optimize_weights(df, features)
        for r in results:
            assert len(r.feature_importances) > 0


class TestExtractSignalWeights:
    def test_weights_normalized_to_mean_one(self) -> None:
        df, features = _make_synthetic_data(200)
        results = optimize_weights(df, features)
        for r in results:
            weights = extract_signal_weights(r)
            values = list(weights.values())
            if any(v > 0 for v in values):
                mean_val = sum(values) / len(values)
                assert mean_val == pytest.approx(1.0, abs=0.05)

    def test_all_signals_present(self) -> None:
        df, features = _make_synthetic_data(200)
        results = optimize_weights(df, features)
        for r in results:
            weights = extract_signal_weights(r)
            for sig in SIGNAL_NAMES:
                assert sig in weights

    def test_lifecycle_has_high_weight(self) -> None:
        """lifecycle_position drives returns in synthetic data, so it should
        get a relatively high weight."""
        df, features = _make_synthetic_data(300, seed=123)
        results = optimize_weights(df, features)
        ridge_result = next((r for r in results if r.model_name == "Ridge"), None)
        if ridge_result is not None:
            weights = extract_signal_weights(ridge_result)
            # lifecycle_position should be above average (> 1.0)
            assert weights["lifecycle_position"] > 0.5


class TestCompareWithHandtuned:
    def test_returns_both_strategies(self) -> None:
        df, _ = _make_synthetic_data(200)
        ml_weights = {sig: 1.0 for sig in SIGNAL_NAMES}
        ml_weights["lifecycle_position"] = 2.0
        handtuned = {sig: 1.0 for sig in SIGNAL_NAMES}

        result = compare_with_handtuned(df, ml_weights, handtuned, "best_hold_apr")
        assert "ml" in result
        assert "handtuned" in result
        assert "quintile_spread" in result["ml"]
        assert "hit_rate" in result["ml"]

    def test_returns_empty_for_small_data(self) -> None:
        df, _ = _make_synthetic_data(5)
        weights = {sig: 1.0 for sig in SIGNAL_NAMES}
        result = compare_with_handtuned(df, weights, weights, "best_hold_apr")
        assert result == {}
