"""Tests for APR calculation module."""

import math

import numpy as np
import pandas as pd
import pytest

from services.backtesting.returns import (
    MAX_FLIP_APR,
    add_apr_columns,
    compute_apr,
    compute_best_apr,
)


class TestComputeApr:
    def test_12m_identity(self) -> None:
        """50% in 12 months = 50% APR."""
        assert compute_apr(0.50, 12) == pytest.approx(0.50)

    def test_24m_compounding(self) -> None:
        """100% in 24 months = ~41.4% APR."""
        expected = math.sqrt(2.0) - 1.0  # (1+1)^(12/24) - 1
        assert compute_apr(1.0, 24) == pytest.approx(expected, rel=1e-6)

    def test_36m(self) -> None:
        """80% in 36 months = ~21.4% APR."""
        expected = 1.80 ** (12.0 / 36.0) - 1.0
        assert compute_apr(0.80, 36) == pytest.approx(expected, rel=1e-6)

    def test_negative_return(self) -> None:
        """-20% in 12 months = -20% APR."""
        assert compute_apr(-0.20, 12) == pytest.approx(-0.20)

    def test_1m_annualized(self) -> None:
        """5% in 1 month annualizes to ~79.6% APR."""
        expected = 1.05**12 - 1.0
        assert compute_apr(0.05, 1) == pytest.approx(expected, rel=1e-4)

    def test_total_loss(self) -> None:
        """-100% loss returns -100% APR."""
        assert compute_apr(-1.0, 12) == pytest.approx(-1.0)

    def test_worse_than_total_loss(self) -> None:
        """Returns worse than -100% clamp to -100% APR."""
        assert compute_apr(-1.5, 12) == pytest.approx(-1.0)

    def test_zero_months_raises(self) -> None:
        with pytest.raises(ValueError, match="months must be positive"):
            compute_apr(0.10, 0)

    def test_negative_months_raises(self) -> None:
        with pytest.raises(ValueError, match="months must be positive"):
            compute_apr(0.10, -3)

    def test_zero_return(self) -> None:
        """0% return at any horizon = 0% APR."""
        assert compute_apr(0.0, 12) == pytest.approx(0.0)
        assert compute_apr(0.0, 36) == pytest.approx(0.0)


class TestAddAprColumns:
    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "item_id": ["A", "B", "C"],
            "return_hold_12m": [0.50, -0.20, None],
            "return_hold_24m": [1.00, 0.30, 0.10],
            "return_hold_36m": [0.80, None, 0.60],
            "return_flip_1m": [0.05, 0.10, None],
        })

    def test_apr_columns_created(self) -> None:
        df = self._make_df()
        result = add_apr_columns(df)
        assert "apr_hold_12m" in result.columns
        assert "apr_hold_24m" in result.columns
        assert "apr_hold_36m" in result.columns
        assert "apr_flip_1m" in result.columns

    def test_no_mutation(self) -> None:
        df = self._make_df()
        original_cols = list(df.columns)
        add_apr_columns(df)
        assert list(df.columns) == original_cols

    def test_hold_12m_values(self) -> None:
        result = add_apr_columns(self._make_df())
        assert result["apr_hold_12m"].iloc[0] == pytest.approx(0.50)
        assert result["apr_hold_12m"].iloc[1] == pytest.approx(-0.20)
        assert pd.isna(result["apr_hold_12m"].iloc[2])

    def test_flip_apr_capped(self) -> None:
        df = pd.DataFrame({
            "return_flip_1m": [0.50],  # 50% in 1m -> extreme APR
        })
        result = add_apr_columns(df)
        assert result["apr_flip_1m"].iloc[0] <= MAX_FLIP_APR

    def test_none_returns_stay_none(self) -> None:
        result = add_apr_columns(self._make_df())
        assert pd.isna(result["apr_hold_12m"].iloc[2])
        assert pd.isna(result["apr_flip_1m"].iloc[2])


class TestComputeBestApr:
    def test_picks_highest_apr(self) -> None:
        df = pd.DataFrame({
            "apr_hold_12m": [0.50, 0.10],
            "apr_hold_24m": [0.30, 0.40],
            "apr_hold_36m": [0.20, 0.15],
        })
        result = compute_best_apr(df)
        assert result["best_hold_apr"].iloc[0] == pytest.approx(0.50)
        assert result["best_hold_apr"].iloc[1] == pytest.approx(0.40)

    def test_handles_nans(self) -> None:
        df = pd.DataFrame({
            "apr_hold_12m": [None, 0.10],
            "apr_hold_24m": [0.30, None],
        })
        result = compute_best_apr(df)
        assert result["best_hold_apr"].iloc[0] == pytest.approx(0.30)
        assert result["best_hold_apr"].iloc[1] == pytest.approx(0.10)

    def test_all_nan_returns_nan(self) -> None:
        df = pd.DataFrame({
            "apr_hold_12m": [None],
            "apr_hold_24m": [None],
        })
        result = compute_best_apr(df)
        assert pd.isna(result["best_hold_apr"].iloc[0])

    def test_no_mutation(self) -> None:
        df = pd.DataFrame({
            "apr_hold_12m": [0.50],
            "apr_hold_24m": [0.30],
        })
        original_cols = list(df.columns)
        compute_best_apr(df)
        assert list(df.columns) == original_cols

    def test_no_hold_columns(self) -> None:
        df = pd.DataFrame({"apr_flip_1m": [0.50]})
        result = compute_best_apr(df)
        assert "best_hold_apr" in result.columns
        assert pd.isna(result["best_hold_apr"].iloc[0])
