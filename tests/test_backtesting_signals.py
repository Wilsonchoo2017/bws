"""Unit tests for backtesting signal computations."""

import numpy as np
import pandas as pd
import pytest

from services.backtesting.modifiers import (
    compute_niche_penalty,
    compute_shelf_life,
    compute_subtheme_premium,
)
from services.backtesting.signals import (
    _extract_avg_price,
    _extract_price,
    _filter_up_to,
    compute_collector_premium,
    compute_community_quality,
    compute_demand_pressure,
    compute_lifecycle_position,
    compute_momentum,
    compute_peer_appreciation,
    compute_price_trend,
    compute_price_vs_rrp,
    compute_stock_level,
    compute_supply_velocity,
    compute_theme_quality,
)


# ---------------------------------------------------------------------------
# Helpers to build test DataFrames
# ---------------------------------------------------------------------------


def _make_sales(
    months: list[tuple[int, int]],
    avg_prices: list[int],
    times_sold: list[int] | None = None,
    total_qty: list[int] | None = None,
    min_prices: list[int] | None = None,
    max_prices: list[int] | None = None,
) -> pd.DataFrame:
    """Build a monthly sales DataFrame for testing."""
    n = len(months)
    if times_sold is None:
        times_sold = [10] * n
    if total_qty is None:
        total_qty = [10] * n
    if min_prices is None:
        min_prices = [int(p * 0.8) for p in avg_prices]
    if max_prices is None:
        max_prices = [int(p * 1.2) for p in avg_prices]

    return pd.DataFrame({
        "item_id": ["TEST-1"] * n,
        "year": [m[0] for m in months],
        "month": [m[1] for m in months],
        "condition": ["new"] * n,
        "times_sold": times_sold,
        "total_quantity": total_qty,
        "min_price": min_prices,
        "avg_price": avg_prices,
        "max_price": max_prices,
        "currency": ["USD"] * n,
    })


# ---------------------------------------------------------------------------
# _extract_avg_price
# ---------------------------------------------------------------------------


class TestExtractAvgPrice:
    def test_python_int(self) -> None:
        row = pd.Series({"avg_price": 5000})
        assert _extract_avg_price(row) == 5000.0

    def test_python_float(self) -> None:
        row = pd.Series({"avg_price": 5000.5})
        assert _extract_avg_price(row) == 5000.5

    def test_numpy_int32(self) -> None:
        row = pd.Series({"avg_price": np.int32(7999)})
        assert _extract_avg_price(row) == 7999.0

    def test_numpy_int64(self) -> None:
        row = pd.Series({"avg_price": np.int64(12345)})
        assert _extract_avg_price(row) == 12345.0

    def test_numpy_float64(self) -> None:
        row = pd.Series({"avg_price": np.float64(9999.0)})
        assert _extract_avg_price(row) == 9999.0

    def test_json_string(self) -> None:
        row = pd.Series({"avg_price": '{"amount": 7999}'})
        assert _extract_avg_price(row) == 7999.0

    def test_dict(self) -> None:
        row = pd.Series({"avg_price": {"amount": 7999}})
        assert _extract_avg_price(row) == 7999.0

    def test_none(self) -> None:
        row = pd.Series({"avg_price": None})
        assert _extract_avg_price(row) is None

    def test_nan(self) -> None:
        row = pd.Series({"avg_price": float("nan")})
        assert _extract_avg_price(row) is None

    def test_zero(self) -> None:
        row = pd.Series({"avg_price": 0})
        assert _extract_avg_price(row) == 0.0


class TestExtractPrice:
    def test_min_price_numpy_int(self) -> None:
        row = pd.Series({"min_price": np.int32(3000)})
        assert _extract_price(row, "min_price") == 3000.0

    def test_missing_field(self) -> None:
        row = pd.Series({"avg_price": 5000})
        assert _extract_price(row, "min_price") is None


# ---------------------------------------------------------------------------
# _filter_up_to
# ---------------------------------------------------------------------------


class TestFilterUpTo:
    def test_filters_correctly(self) -> None:
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3), (2025, 4)],
            [100, 200, 300, 400],
        )
        result = _filter_up_to(sales, 2025, 2)
        assert len(result) == 2
        assert list(result["month"]) == [1, 2]

    def test_includes_earlier_years(self) -> None:
        sales = _make_sales(
            [(2024, 11), (2024, 12), (2025, 1)],
            [100, 200, 300],
        )
        result = _filter_up_to(sales, 2025, 1)
        assert len(result) == 3

    def test_no_look_ahead(self) -> None:
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [100, 200, 300],
        )
        result = _filter_up_to(sales, 2025, 1)
        assert len(result) == 1
        assert result.iloc[0]["avg_price"] == 100


# ---------------------------------------------------------------------------
# Signal 1: Peer Appreciation
# ---------------------------------------------------------------------------


class TestPeerAppreciation:
    def test_appreciating_price(self) -> None:
        # Price rises 50% above trailing avg
        sales = _make_sales(
            [(2025, m) for m in range(1, 8)],
            [100, 100, 100, 100, 100, 100, 200],
        )
        score = compute_peer_appreciation(sales, 2025, 7)
        assert score is not None
        assert score >= 75.0  # +100% above trailing

    def test_stable_price(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 8)],
            [100, 100, 100, 100, 100, 100, 100],
        )
        score = compute_peer_appreciation(sales, 2025, 7)
        assert score == 50.0  # Stable

    def test_declining_price(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 8)],
            [200, 200, 200, 200, 200, 200, 100],
        )
        score = compute_peer_appreciation(sales, 2025, 7)
        assert score is not None
        assert score <= 35.0

    def test_insufficient_data(self) -> None:
        sales = _make_sales([(2025, 1)], [100])
        assert compute_peer_appreciation(sales, 2025, 1) is None


# ---------------------------------------------------------------------------
# Signal 2: Demand Pressure
# ---------------------------------------------------------------------------


class TestDemandPressure:
    def test_high_demand(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            total_qty=[60, 60, 60],
        )
        assert compute_demand_pressure(sales, 2025, 3) == 95.0

    def test_low_demand(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            total_qty=[1, 1, 1],
        )
        assert compute_demand_pressure(sales, 2025, 3) == 30.0

    def test_zero_demand(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            total_qty=[0, 0, 0],
        )
        assert compute_demand_pressure(sales, 2025, 3) == 15.0


# ---------------------------------------------------------------------------
# Signal 3: Supply Velocity
# ---------------------------------------------------------------------------


class TestSupplyVelocity:
    def test_returns_none_without_snapshots(self) -> None:
        assert compute_supply_velocity(None, "TEST-1", 2025, 3) is None

    def test_returns_none_with_empty_snapshots(self) -> None:
        assert compute_supply_velocity(pd.DataFrame(), "TEST-1", 2025, 3) is None


# ---------------------------------------------------------------------------
# Signal 4: Price Trend
# ---------------------------------------------------------------------------


class TestPriceTrend:
    def test_upward_trend(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 120, 140, 160, 180, 200],
        )
        score = compute_price_trend(sales, 2025, 6)
        assert score is not None
        assert score >= 60.0

    def test_flat_trend(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 100, 100, 100, 100, 100],
        )
        score = compute_price_trend(sales, 2025, 6)
        assert score == 50.0

    def test_downward_trend(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [200, 180, 160, 140, 120, 100],
        )
        score = compute_price_trend(sales, 2025, 6)
        assert score is not None
        assert score <= 40.0

    def test_insufficient_data(self) -> None:
        sales = _make_sales([(2025, 1), (2025, 2)], [100, 200])
        assert compute_price_trend(sales, 2025, 2) is None


# ---------------------------------------------------------------------------
# Signal 5: Price vs RRP
# ---------------------------------------------------------------------------


class TestPriceVsRRP:
    def test_above_rrp(self) -> None:
        sales = _make_sales([(2025, 1)], [20000])
        score = compute_price_vs_rrp(sales, 2025, 1, 10000, "USD")
        assert score is not None
        assert score >= 85.0  # 2x RRP

    def test_at_rrp(self) -> None:
        sales = _make_sales([(2025, 1)], [10000])
        score = compute_price_vs_rrp(sales, 2025, 1, 10000, "USD")
        assert score == 55.0

    def test_below_rrp(self) -> None:
        sales = _make_sales([(2025, 1)], [5000])
        score = compute_price_vs_rrp(sales, 2025, 1, 10000, "USD")
        assert score is not None
        assert score <= 30.0

    def test_no_rrp(self) -> None:
        sales = _make_sales([(2025, 1)], [10000])
        assert compute_price_vs_rrp(sales, 2025, 1, None, None) is None

    def test_zero_rrp(self) -> None:
        sales = _make_sales([(2025, 1)], [10000])
        assert compute_price_vs_rrp(sales, 2025, 1, 0, "USD") is None


# ---------------------------------------------------------------------------
# Signal 6: Lifecycle Position
# ---------------------------------------------------------------------------


class TestLifecyclePosition:
    def test_recently_retired(self) -> None:
        score = compute_lifecycle_position(2020, 2023, 2024)
        assert score is not None
        assert score > 0

    def test_long_retired(self) -> None:
        score = compute_lifecycle_position(2010, 2012, 2025)
        assert score is not None
        assert score > 50.0  # 13 years post-retirement

    def test_no_release_year(self) -> None:
        assert compute_lifecycle_position(None, None, 2025) is None

    def test_score_in_range(self) -> None:
        score = compute_lifecycle_position(2015, 2018, 2025)
        assert score is not None
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Signal 7: Stock Level
# ---------------------------------------------------------------------------


class TestStockLevel:
    def test_returns_none_without_snapshots(self) -> None:
        assert compute_stock_level(None, "TEST-1", 2025, 3) is None


# ---------------------------------------------------------------------------
# Signal 8: Momentum
# ---------------------------------------------------------------------------


class TestMomentum:
    def test_accelerating(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100] * 6,
            total_qty=[5, 5, 5, 20, 20, 20],
        )
        score = compute_momentum(sales, 2025, 6)
        assert score is not None
        assert score >= 80.0

    def test_decelerating(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100] * 6,
            total_qty=[20, 20, 20, 5, 5, 5],
        )
        score = compute_momentum(sales, 2025, 6)
        assert score is not None
        assert score <= 40.0

    def test_insufficient_data(self) -> None:
        sales = _make_sales([(2025, 1), (2025, 2), (2025, 3)], [100, 100, 100])
        assert compute_momentum(sales, 2025, 3) is None


# ---------------------------------------------------------------------------
# Signal 9: Theme Quality
# ---------------------------------------------------------------------------


class TestThemeQuality:
    def test_premium_theme(self) -> None:
        score = compute_theme_quality("Star Wars")
        assert score is not None
        assert score > 50.0

    def test_low_demand_theme(self) -> None:
        score = compute_theme_quality("Vidiyo")
        assert score is not None
        assert score < 20.0

    def test_none_theme(self) -> None:
        assert compute_theme_quality(None) is None


# ---------------------------------------------------------------------------
# Signal 10: Community Quality
# ---------------------------------------------------------------------------


class TestCommunityQuality:
    def test_high_liquidity(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            times_sold=[200, 200, 200],
        )
        assert compute_community_quality(sales, 2025, 3) == 95.0

    def test_low_liquidity(self) -> None:
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            times_sold=[1, 1, 1],
        )
        assert compute_community_quality(sales, 2025, 3) == 15.0


# ---------------------------------------------------------------------------
# Signal 11: Collector Premium
# ---------------------------------------------------------------------------


class TestCollectorPremium:
    def test_healthy_spread(self) -> None:
        # spread = (120 - 80) / 100 = 0.4 → in (0.05, 0.5) range → 70.0
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            min_prices=[80, 80, 80],
            max_prices=[120, 120, 120],
        )
        score = compute_collector_premium(sales, 2025, 3)
        assert score is not None
        assert score >= 70.0

    def test_tight_spread(self) -> None:
        # spread = (102 - 98) / 100 = 0.04 → tight → 40.0
        sales = _make_sales(
            [(2025, m) for m in range(1, 4)],
            [100, 100, 100],
            min_prices=[98, 98, 98],
            max_prices=[102, 102, 102],
        )
        score = compute_collector_premium(sales, 2025, 3)
        assert score == 40.0


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------


class TestModifiers:
    def test_shelf_life_short(self) -> None:
        assert compute_shelf_life(2020, 2021) == 1.15

    def test_shelf_life_typical(self) -> None:
        assert compute_shelf_life(2020, 2023) == 1.0

    def test_shelf_life_long(self) -> None:
        assert compute_shelf_life(2015, 2025) == 0.90

    def test_shelf_life_missing(self) -> None:
        assert compute_shelf_life(None, None) == 1.0

    def test_subtheme_ucs(self) -> None:
        assert compute_subtheme_premium("UCS") == 1.20

    def test_subtheme_unknown(self) -> None:
        assert compute_subtheme_premium("City") == 1.0

    def test_subtheme_none(self) -> None:
        assert compute_subtheme_premium(None) == 1.0

    def test_niche_vidiyo(self) -> None:
        assert compute_niche_penalty("Vidiyo") == 0.70

    def test_niche_normal(self) -> None:
        assert compute_niche_penalty("Technic") == 1.0

    def test_niche_none(self) -> None:
        assert compute_niche_penalty(None) == 1.0
