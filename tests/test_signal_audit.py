"""Tests for signal significance audit module."""

import numpy as np
import pandas as pd
import pytest

from services.backtesting.signal_audit import Verdict, audit_signals
from services.backtesting.types import SIGNAL_NAMES


def _make_audit_data(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Create data where value_opportunity is strongly correlated with returns,
    demand_pressure is weakly correlated, and price_trend is noise."""
    rng = np.random.RandomState(seed)

    data: dict[str, np.ndarray | list] = {
        "item_id": [f"item_{i}" for i in range(n)],
    }
    for sig in SIGNAL_NAMES:
        data[sig] = rng.uniform(10, 90, n).astype(float)

    df = pd.DataFrame(data)

    # Strong signal: value_opportunity drives returns
    noise = rng.normal(0, 0.03, n)
    df["return_flip_1m"] = 0.005 * df["value_opportunity"] - 0.2 + noise

    # Make some signals have zero data (like snapshot-based ones)
    df["supply_velocity"] = np.nan
    df["stock_level"] = np.nan
    df["price_wall"] = np.nan

    return df


class TestAuditSignals:
    def test_returns_audit_results(self) -> None:
        df = _make_audit_data()
        results = audit_signals(df, "return_flip_1m")
        assert results.n_samples == 200
        assert len(results.reports) == len(SIGNAL_NAMES)

    def test_strong_signal_kept(self) -> None:
        df = _make_audit_data()
        results = audit_signals(df, "return_flip_1m")
        assert "value_opportunity" in results.keep_signals

    def test_no_data_signals_detected(self) -> None:
        df = _make_audit_data()
        results = audit_signals(df, "return_flip_1m")
        assert "supply_velocity" in results.no_data_signals
        assert "stock_level" in results.no_data_signals
        assert "price_wall" in results.no_data_signals

    def test_verdicts_cover_all_signals(self) -> None:
        df = _make_audit_data()
        results = audit_signals(df, "return_flip_1m")
        all_classified = (
            results.keep_signals
            + results.weak_signals
            + results.drop_signals
            + results.no_data_signals
        )
        for sig in SIGNAL_NAMES:
            assert sig in all_classified

    def test_p_value_present_for_covered_signals(self) -> None:
        df = _make_audit_data()
        results = audit_signals(df, "return_flip_1m")
        for r in results.reports:
            if r.coverage_pct >= 20:
                assert r.p_value is not None
                assert r.spearman_corr is not None

    def test_insufficient_data(self) -> None:
        df = _make_audit_data(n=5)
        results = audit_signals(df, "return_flip_1m")
        assert results.n_samples == 5
        assert len(results.no_data_signals) == len(SIGNAL_NAMES)

    def test_value_opportunity_significant(self) -> None:
        """value_opportunity should be statistically significant."""
        df = _make_audit_data(n=200)
        results = audit_signals(df, "return_flip_1m")
        vo_report = next(r for r in results.reports if r.signal == "value_opportunity")
        assert vo_report.is_significant
        assert vo_report.p_value is not None and vo_report.p_value < 0.05
