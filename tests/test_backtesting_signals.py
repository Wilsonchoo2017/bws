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
    compute_demand_pressure,
    compute_lifecycle_position,
    compute_listing_ratio,
    compute_new_used_spread,
    compute_price_trend,
    compute_price_vs_rrp,
    compute_price_wall,
    compute_stock_level,
    compute_supply_velocity,
    compute_volume_price_confirm,
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
# Signal: Demand Pressure
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
# Signal: Collector Premium
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


# ---------------------------------------------------------------------------
# Helpers to build snapshot DataFrames
# ---------------------------------------------------------------------------


def _make_snapshot(
    item_id: str,
    scraped_at: str,
    current_new: dict,
    current_used: dict | None = None,
) -> pd.DataFrame:
    """Build a single-row price history snapshot DataFrame."""
    import json

    row: dict = {
        "item_id": item_id,
        "scraped_at": pd.Timestamp(scraped_at),
        "current_new": json.dumps(current_new),
    }
    if current_used is not None:
        row["current_used"] = json.dumps(current_used)
    return pd.DataFrame([row])


def _make_current_new_box(
    avg_price: int = 10000,
    qty_avg_price: int = 10000,
    min_price: int = 8000,
    max_price: int = 12000,
    total_lots: int = 20,
    total_qty: int = 30,
    times_sold: int = 10,
) -> dict:
    """Build a current_new pricing box dict."""
    return {
        "avg_price": {"currency": "USD", "amount": avg_price},
        "qty_avg_price": {"currency": "USD", "amount": qty_avg_price},
        "min_price": {"currency": "USD", "amount": min_price},
        "max_price": {"currency": "USD", "amount": max_price},
        "total_lots": total_lots,
        "total_qty": total_qty,
        "times_sold": times_sold,
    }


# ---------------------------------------------------------------------------
# Signal 15: Price Wall
# ---------------------------------------------------------------------------


class TestPriceWall:
    def test_returns_none_without_snapshots(self) -> None:
        assert compute_price_wall(None, "TEST-1", 2025, 3) is None

    def test_returns_none_with_empty_snapshots(self) -> None:
        assert compute_price_wall(pd.DataFrame(), "TEST-1", 2025, 3) is None

    def test_strong_support_above(self) -> None:
        """qty_avg well above avg = bullish support."""
        box = _make_current_new_box(
            avg_price=10000, qty_avg_price=12000,
            min_price=8000, max_price=14000,
        )
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        score = compute_price_wall(snaps, "TEST-1", 2025, 3)
        assert score is not None
        assert score >= 75.0

    def test_neutral_divergence(self) -> None:
        """qty_avg roughly equal to avg."""
        box = _make_current_new_box(
            avg_price=10000, qty_avg_price=10200,
            min_price=8000, max_price=12000,
        )
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        score = compute_price_wall(snaps, "TEST-1", 2025, 3)
        assert score == 55.0

    def test_bearish_dumping(self) -> None:
        """qty_avg well below avg = dumping."""
        box = _make_current_new_box(
            avg_price=10000, qty_avg_price=8000,
            min_price=7000, max_price=14000,
        )
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        score = compute_price_wall(snaps, "TEST-1", 2025, 3)
        assert score is not None
        assert score <= 35.0

    def test_missing_qty_avg_price(self) -> None:
        """Returns None when qty_avg_price is missing."""
        box = _make_current_new_box()
        del box["qty_avg_price"]
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        assert compute_price_wall(snaps, "TEST-1", 2025, 3) is None

    def test_respects_time_cutoff(self) -> None:
        """Snapshot after the eval date should be ignored."""
        box = _make_current_new_box(
            avg_price=10000, qty_avg_price=12000,
            min_price=8000, max_price=14000,
        )
        snaps = _make_snapshot("TEST-1", "2025-04-15", box)
        assert compute_price_wall(snaps, "TEST-1", 2025, 3) is None


# ---------------------------------------------------------------------------
# Signal 16: Listing Ratio
# ---------------------------------------------------------------------------


class TestListingRatio:
    def test_returns_none_without_snapshots(self) -> None:
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [10000, 10000, 10000],
        )
        assert compute_listing_ratio(None, "TEST-1", sales, 2025, 3) is None

    def test_undersupply_high_score(self) -> None:
        """Few listings relative to sales = bullish."""
        box = _make_current_new_box(total_qty=5, total_lots=3)
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [10000, 10000, 10000],
            total_qty=[20, 25, 30],
            times_sold=[15, 20, 18],
        )
        score = compute_listing_ratio(snaps, "TEST-1", sales, 2025, 3)
        assert score is not None
        assert score >= 80.0  # 5 / 25 avg = 0.2 months

    def test_oversupply_low_score(self) -> None:
        """Many listings relative to sales = bearish."""
        box = _make_current_new_box(total_qty=500, total_lots=80)
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [10000, 10000, 10000],
            total_qty=[2, 3, 1],
            times_sold=[2, 1, 2],
        )
        score = compute_listing_ratio(snaps, "TEST-1", sales, 2025, 3)
        assert score is not None
        assert score <= 20.0  # 500 / 2 avg = 250 months

    def test_zero_sales_returns_10(self) -> None:
        """Listings exist but zero sales = extreme oversupply."""
        box = _make_current_new_box(total_qty=50, total_lots=10)
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [10000, 10000, 10000],
            total_qty=[0, 0, 0],
            times_sold=[0, 0, 0],
        )
        score = compute_listing_ratio(snaps, "TEST-1", sales, 2025, 3)
        assert score == 10.0

    def test_neutral_range(self) -> None:
        """Balanced supply/demand."""
        box = _make_current_new_box(total_qty=30, total_lots=15)
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [10000, 10000, 10000],
            total_qty=[8, 10, 12],
            times_sold=[6, 8, 7],
        )
        score = compute_listing_ratio(snaps, "TEST-1", sales, 2025, 3)
        assert score is not None
        assert 45.0 <= score <= 70.0  # ~30/10 = 3 months

    def test_no_sales_data_with_listings(self) -> None:
        """No sales rows at all but snapshots exist."""
        box = _make_current_new_box(total_qty=20, total_lots=5)
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        empty_sales = pd.DataFrame(columns=[
            "item_id", "year", "month", "condition",
            "times_sold", "total_quantity", "min_price",
            "avg_price", "max_price", "currency",
        ])
        score = compute_listing_ratio(snaps, "TEST-1", empty_sales, 2025, 3)
        assert score == 10.0


# ---------------------------------------------------------------------------
# Signal 17: Volume-Price Confirmation
# ---------------------------------------------------------------------------


class TestVolumePriceConfirm:
    def test_insufficient_data(self) -> None:
        sales = _make_sales(
            [(2025, 1), (2025, 2), (2025, 3)],
            [100, 110, 120],
        )
        assert compute_volume_price_confirm(sales, 2025, 3) is None

    def test_confirmed_rally(self) -> None:
        """Price up + volume up = high score."""
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 100, 100, 110, 120, 130],
            total_qty=[10, 10, 10, 15, 20, 25],
        )
        score = compute_volume_price_confirm(sales, 2025, 6)
        assert score is not None
        assert score >= 75.0

    def test_weak_rally_distribution(self) -> None:
        """Price up + volume down = low-moderate score."""
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 100, 100, 110, 120, 130],
            total_qty=[30, 30, 30, 10, 8, 5],
        )
        score = compute_volume_price_confirm(sales, 2025, 6)
        assert score is not None
        assert score == 40.0

    def test_capitulation(self) -> None:
        """Price down + volume up = moderate score (potential reversal)."""
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 100, 100, 90, 80, 70],
            total_qty=[10, 10, 10, 20, 30, 40],
        )
        score = compute_volume_price_confirm(sales, 2025, 6)
        assert score is not None
        assert score == 45.0

    def test_apathy(self) -> None:
        """Price down + volume down = low score."""
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 100, 100, 90, 80, 70],
            total_qty=[30, 30, 30, 10, 8, 5],
        )
        score = compute_volume_price_confirm(sales, 2025, 6)
        assert score is not None
        assert score == 25.0

    def test_neutral_zone(self) -> None:
        """Flat price and volume = neutral."""
        sales = _make_sales(
            [(2025, m) for m in range(1, 7)],
            [100, 100, 100, 101, 100, 101],
            total_qty=[10, 10, 10, 10, 10, 10],
        )
        score = compute_volume_price_confirm(sales, 2025, 6)
        assert score == 55.0


# ---------------------------------------------------------------------------
# Signal 18: New-Used Spread
# ---------------------------------------------------------------------------


def _make_pricing_box(avg_price: int) -> dict:
    """Build a minimal pricing box with just avg_price."""
    return {
        "avg_price": {"currency": "USD", "amount": avg_price},
        "total_lots": 10,
        "total_qty": 20,
    }


def _make_dual_snapshot(
    item_id: str,
    scraped_at: str,
    new_price: int,
    used_price: int,
) -> pd.DataFrame:
    """Build a snapshot with both new and used pricing."""
    return _make_snapshot(
        item_id,
        scraped_at,
        current_new=_make_pricing_box(new_price),
        current_used=_make_pricing_box(used_price),
    )


class TestNewUsedSpread:
    def test_returns_none_without_snapshots(self) -> None:
        assert compute_new_used_spread(None, "TEST-1", 2025, 3) is None

    def test_used_exceeds_new(self) -> None:
        """Used > new = extreme sealed scarcity."""
        snaps = _make_dual_snapshot("TEST-1", "2025-03-15", 10000, 11000)
        score = compute_new_used_spread(snaps, "TEST-1", 2025, 3)
        assert score == 95.0

    def test_tight_spread_static(self) -> None:
        """Used at 85% of new = strong collector market."""
        snaps = _make_dual_snapshot("TEST-1", "2025-03-15", 10000, 8500)
        score = compute_new_used_spread(snaps, "TEST-1", 2025, 3)
        assert score == 80.0

    def test_wide_spread_static(self) -> None:
        """Used at 30% of new = casual market."""
        snaps = _make_dual_snapshot("TEST-1", "2025-03-15", 10000, 3000)
        score = compute_new_used_spread(snaps, "TEST-1", 2025, 3)
        assert score == 20.0

    def test_narrowing_spread_bullish(self) -> None:
        """Spread narrowing over two snapshots = bullish."""
        import json

        snap1 = _make_dual_snapshot("TEST-1", "2025-02-15", 10000, 6000)
        snap2 = _make_dual_snapshot("TEST-1", "2025-03-15", 10000, 8500)
        snaps = pd.concat([snap1, snap2], ignore_index=True)
        score = compute_new_used_spread(snaps, "TEST-1", 2025, 3)
        assert score is not None
        assert score >= 75.0

    def test_widening_spread_bearish(self) -> None:
        """Spread widening over two snapshots = bearish."""
        snap1 = _make_dual_snapshot("TEST-1", "2025-02-15", 10000, 7000)
        snap2 = _make_dual_snapshot("TEST-1", "2025-03-15", 10000, 4000)
        snaps = pd.concat([snap1, snap2], ignore_index=True)
        score = compute_new_used_spread(snaps, "TEST-1", 2025, 3)
        assert score is not None
        assert score <= 35.0

    def test_missing_used_price(self) -> None:
        """Returns None when used pricing unavailable."""
        box = _make_current_new_box()
        snaps = _make_snapshot("TEST-1", "2025-03-15", box)
        assert compute_new_used_spread(snaps, "TEST-1", 2025, 3) is None
