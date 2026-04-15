"""Tests for Q4 seasonal feature engineering."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from services.ml.growth.seasonality_features import (
    MIN_Q4_POINTS,
    Q4_FEATURE_NAMES,
    engineer_q4_seasonal_features,
)

RRP_CENTS = 10_000  # $100 RRP


def _monthly_timeline(entries: list[tuple[str, float | None]]) -> str:
    """Build an amazon_price_json-style string from (timestamp, price) tuples."""
    return json.dumps([[ts, price] for ts, price in entries])


def _df(
    *,
    amazon: str | None = None,
    fba: str | None = None,
    fbm: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = pd.DataFrame(
        [{"set_number": "S-1", "rrp_usd_cents": RRP_CENTS}]
    )
    keepa = pd.DataFrame(
        [
            {
                "set_number": "S-1",
                "amazon_price_json": amazon,
                "new_3p_fba_json": fba,
                "new_3p_fbm_json": fbm,
            }
        ]
    )
    return base, keepa


def _q4_points_for_year(year: int, price: float) -> list[tuple[str, float]]:
    """Generate >=10 Q4 points for a single year (meets MIN_Q4_POINTS gate)."""
    days = [1, 5, 10, 15, 20, 25, 28]
    return [
        (f"{year:04d}-{month:02d}-{day:02d}", price)
        for month in (10, 11, 12)
        for day in days[: 4 if month == 10 else 3]
    ]


class TestGroupAPricing:
    def test_sparse_q4_emits_nan(self):
        # Only 3 Q4 points — below MIN_Q4_POINTS (10). All features NaN.
        tl = _monthly_timeline(
            [
                ("2023-10-01", 9500),
                ("2023-11-01", 9400),
                ("2023-12-01", 9600),
            ]
        )
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert pd.isna(row["kp_q4_avg_discount"])
        assert pd.isna(row["kp_q4_max_discount"])

    def test_q4_avg_and_max_discount(self):
        # 10 Q4 points at $90 (10% disc), one at $80 (20% disc)
        entries = [(f"2023-10-{d:02d}", 9000) for d in range(1, 11)]
        entries.append(("2023-12-01", 8000))
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        # mean price ≈ (9000*10 + 8000)/11 = 8909.1, disc ≈ 10.91%
        assert row["kp_q4_avg_discount"] == pytest.approx(10.91, rel=0.01)
        assert row["kp_q4_max_discount"] == pytest.approx(20.0, rel=0.01)

    def test_q4_vs_nonq4_delta_positive_when_q4_discounts_more(self):
        # Non-Q4 at $100 (no discount), Q4 at $80 (20% discount)
        entries = [(f"2023-{m:02d}-15", 10000) for m in range(1, 10)]
        entries.extend(_q4_points_for_year(2023, 8000))
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        # Q4 disc = 20, non-Q4 disc ≈ 0, delta ≈ +20
        assert row["kp_q4_vs_nonq4_disc_delta"] == pytest.approx(20.0, abs=0.1)

    def test_fba_floor_vs_rrp(self):
        # Q4 FBA prices: $105, $108, $110 — floor 5% above RRP (bullish)
        tl = _monthly_timeline(
            [("2023-10-15", 10500), ("2023-11-15", 10800), ("2023-12-15", 11000)]
        )
        base, keepa = _df(fba=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_q4_fba_floor_vs_rrp"] == pytest.approx(5.0, rel=0.01)

    def test_oct_dec_trajectory(self):
        entries = []
        entries += [(f"2023-10-{d:02d}", 10000) for d in (5, 10, 15, 20, 25)]
        entries += [(f"2023-11-15", 9500)]
        entries += [(f"2023-12-{d:02d}", 9000) for d in (1, 10, 20, 30)]
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        # (9000 - 10000)/10000 = -10%
        assert row["kp_q4_oct_dec_trajectory"] == pytest.approx(-10.0, abs=0.1)


class TestGroupBYoY:
    def _build_two_q4s(self, y1_price: float, y2_price: float) -> str:
        entries = _q4_points_for_year(2023, y1_price) + _q4_points_for_year(2024, y2_price)
        return _monthly_timeline(entries)

    def test_yoy_price_delta_and_cagr(self):
        # 2023 Q4 at $100, 2024 Q4 at $110 (+10%)
        tl = self._build_two_q4s(10000, 11000)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_yoy_q4_count"] == 2
        assert row["kp_yoy_q4_price_delta_pct"] == pytest.approx(10.0, rel=0.01)
        # CAGR across 1-year span should equal single-step delta
        assert row["kp_q4_price_cagr"] == pytest.approx(10.0, rel=0.01)

    def test_cagr_multi_year(self):
        # 3 Q4 years: $100 → $121 over 2 years → CAGR 10%
        entries = (
            _q4_points_for_year(2022, 10000)
            + _q4_points_for_year(2023, 11000)
            + _q4_points_for_year(2024, 12100)
        )
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_q4_price_cagr"] == pytest.approx(10.0, abs=0.1)

    def test_disc_slope_deepening(self):
        # 2022 Q4 avg disc 0%, 2023 Q4 avg disc 5%, 2024 Q4 avg disc 10%
        entries = (
            _q4_points_for_year(2022, 10000)
            + _q4_points_for_year(2023, 9500)
            + _q4_points_for_year(2024, 9000)
        )
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        # (10% - 0%) / 2 years = 5 pp/yr
        assert row["kp_q4_disc_slope"] == pytest.approx(5.0, abs=0.1)

    def test_yoy_missing_when_single_q4(self):
        tl = _monthly_timeline(_q4_points_for_year(2023, 9000))
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_yoy_q4_count"] == 1
        assert pd.isna(row["kp_q4_price_cagr"])
        assert pd.isna(row["kp_q4_disc_slope"])


class TestGroupDClearance:
    def test_clearance_signal_fires_on_large_discount_jump(self):
        # prior Q4 max disc 5%, latest Q4 max disc 25% → jump > 10pp
        entries = _q4_points_for_year(2022, 9500)  # 5% disc
        entries += _q4_points_for_year(2023, 9500)  # another 5%
        entries += [
            (f"2024-10-{d:02d}", 9500) for d in (5, 10, 15)
        ]
        entries += [("2024-12-01", 7500)]  # 25% disc spike
        entries += [(f"2024-11-{d:02d}", 9500) for d in (5, 15, 25)]
        entries += [(f"2024-12-{d:02d}", 9500) for d in (10, 20, 30)]
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_q4_clearance_signal"] == 1.0

    def test_clearance_signal_quiet_when_flat(self):
        # All three Q4s at same price, no jump
        entries = (
            _q4_points_for_year(2022, 9500)
            + _q4_points_for_year(2023, 9500)
            + _q4_points_for_year(2024, 9500)
        )
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_q4_clearance_signal"] == 0.0

    def test_oos_in_q4_flag(self):
        # Price goes null in November → OOS in Q4
        entries = [(f"2023-{m:02d}-15", 9500) for m in range(1, 11)]
        entries.append(("2023-11-15", None))
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        row = out.iloc[0]
        assert row["kp_amazon_oos_in_q4"] == 1.0


class TestCutoffEnforcement:
    def test_points_after_cutoff_are_ignored(self):
        # 2022 Q4 at $100 (14% disc), 2023 Q4 at $80 (20% disc)
        # With cutoff '2022-12' only the first Q4 should count
        entries = _q4_points_for_year(2022, 9000) + _q4_points_for_year(2023, 8000)
        tl = _monthly_timeline(entries)
        base, keepa = _df(amazon=tl)
        out = engineer_q4_seasonal_features(
            base, keepa, cutoff_dates={"S-1": "2022-12"}
        )
        row = out.iloc[0]
        assert row["kp_yoy_q4_count"] == 1
        assert pd.isna(row["kp_q4_price_cagr"])  # needs 2 years
        assert row["kp_q4_avg_discount"] == pytest.approx(10.0, abs=0.1)


class TestFeatureList:
    def test_all_feature_columns_present_even_when_empty(self):
        # Empty keepa → every feature column still exists on output, filled NaN
        base = pd.DataFrame([{"set_number": "S-1", "rrp_usd_cents": RRP_CENTS}])
        keepa = pd.DataFrame(columns=["set_number", "amazon_price_json", "new_3p_fba_json", "new_3p_fbm_json"])
        out = engineer_q4_seasonal_features(base, keepa, cutoff_dates={})
        for feat in Q4_FEATURE_NAMES:
            assert feat in out.columns, f"{feat} missing from output"
            assert pd.isna(out.iloc[0][feat])
