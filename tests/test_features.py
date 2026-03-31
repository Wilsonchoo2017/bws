"""Tests for feature engineering module."""

import numpy as np
import pandas as pd
import pytest

from services.backtesting.features import (
    DEFAULT_INTERACTION_PAIRS,
    FeatureConfig,
    engineer_features,
    get_feature_columns,
)
from services.backtesting.types import MODIFIER_NAMES, SIGNAL_NAMES


def _make_signal_df() -> pd.DataFrame:
    """Create a minimal DataFrame with all signal + modifier columns."""
    data: dict[str, list] = {
        "item_id": ["A", "B", "C"],
        "entry_price_cents": [5000, 15000, 0],
    }
    for sig in SIGNAL_NAMES:
        data[sig] = [50.0, 80.0, None]
    for mod in MODIFIER_NAMES:
        data[mod] = [1.0, 1.15, 0.90]
    return pd.DataFrame(data)


class TestEngineerFeatures:
    def test_interaction_columns_created(self) -> None:
        df = _make_signal_df()
        result, features = engineer_features(df)
        for _, _, output_name in DEFAULT_INTERACTION_PAIRS:
            assert output_name in result.columns
            assert output_name in features

    def test_interaction_values_correct(self) -> None:
        df = _make_signal_df()
        result, _ = engineer_features(df)
        # lifecycle_demand = lifecycle_position * demand_pressure / 100
        expected = 50.0 * 50.0 / 100.0
        assert result["lifecycle_demand"].iloc[0] == pytest.approx(expected)

    def test_interaction_nan_propagation(self) -> None:
        df = _make_signal_df()
        result, _ = engineer_features(df)
        # Row C has None signals -> interactions should be NaN
        assert pd.isna(result["lifecycle_demand"].iloc[2])

    def test_log_entry_price_created(self) -> None:
        df = _make_signal_df()
        result, features = engineer_features(df)
        assert "log_entry_price" in result.columns
        assert "log_entry_price" in features
        assert result["log_entry_price"].iloc[0] == pytest.approx(
            np.log1p(5000), rel=1e-6
        )

    def test_log_entry_price_zero_is_nan(self) -> None:
        df = _make_signal_df()
        result, _ = engineer_features(df)
        # entry_price_cents=0 for row C -> should be NaN
        assert pd.isna(result["log_entry_price"].iloc[2])

    def test_signal_count_created(self) -> None:
        df = _make_signal_df()
        result, features = engineer_features(df)
        assert "signal_count" in result.columns
        assert "signal_count" in features
        # Row A: all signals are 50.0 (not None)
        assert result["signal_count"].iloc[0] == len(SIGNAL_NAMES)
        # Row C: all signals are None
        assert result["signal_count"].iloc[2] == 0

    def test_all_signal_names_in_features(self) -> None:
        df = _make_signal_df()
        _, features = engineer_features(df)
        for sig in SIGNAL_NAMES:
            assert sig in features
        for mod in MODIFIER_NAMES:
            assert mod in features

    def test_no_mutation(self) -> None:
        df = _make_signal_df()
        original_cols = list(df.columns)
        engineer_features(df)
        assert list(df.columns) == original_cols

    def test_disable_interactions(self) -> None:
        df = _make_signal_df()
        config = FeatureConfig(include_interactions=False)
        result, features = engineer_features(df, config)
        for _, _, output_name in DEFAULT_INTERACTION_PAIRS:
            assert output_name not in result.columns
            assert output_name not in features

    def test_disable_all_derived(self) -> None:
        df = _make_signal_df()
        config = FeatureConfig(
            include_interactions=False,
            include_log_price=False,
            include_signal_count=False,
        )
        _, features = engineer_features(df, config)
        # Only raw signals and modifiers
        expected = len(SIGNAL_NAMES) + len(MODIFIER_NAMES)
        assert len(features) == expected


class TestGetFeatureColumns:
    def test_recovers_feature_list(self) -> None:
        df = _make_signal_df()
        result, original_features = engineer_features(df)
        recovered = get_feature_columns(result)
        # All original features should be recovered
        for feat in original_features:
            assert feat in recovered
