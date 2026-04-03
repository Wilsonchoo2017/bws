"""Red flag signal computation for Munger inversion model.

Each function computes a danger score (0-100) using only data available
up to the given month T. No look-ahead bias. 100 = maximum danger.

These are inverted from the bullish signals in signals.py to identify
sets that will lose value, stagnate, or underperform.
"""

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config.value_investing import get_theme_annual_growth

# Score threshold for counting a signal as a "high danger" flag
HIGH_DANGER_THRESHOLD = 60.0


@dataclass(frozen=True)
class RedFlagSnapshot:
    """All red flag scores at a point in time."""

    dead_demand: float | None = None
    supply_flood: float | None = None
    price_collapse: float | None = None
    oversaturation: float | None = None
    theme_decay: float | None = None
    retail_overhang: float | None = None
    collector_apathy: float | None = None

    @property
    def composite_score(self) -> float | None:
        """Weighted average of all available red flags (0-100)."""
        weights = {
            "dead_demand": 0.20,
            "supply_flood": 0.15,
            "price_collapse": 0.20,
            "oversaturation": 0.10,
            "theme_decay": 0.10,
            "retail_overhang": 0.10,
            "collector_apathy": 0.15,
        }
        total_weight = 0.0
        weighted_sum = 0.0
        for field, weight in weights.items():
            value = getattr(self, field)
            if value is not None:
                weighted_sum += value * weight
                total_weight += weight

        if total_weight == 0:
            return None
        return weighted_sum / total_weight

    @property
    def flag_count(self) -> int:
        """Number of red flags that score above 60 (high danger)."""
        count = 0
        for field in (
            "dead_demand",
            "supply_flood",
            "price_collapse",
            "oversaturation",
            "theme_decay",
            "retail_overhang",
            "collector_apathy",
        ):
            value = getattr(self, field)
            if value is not None and value >= HIGH_DANGER_THRESHOLD:
                count += 1
        return count

    @property
    def top_risks(self) -> list[tuple[str, float]]:
        """Top 3 risk factors sorted by score descending."""
        risks: list[tuple[str, float]] = []
        for field in (
            "dead_demand",
            "supply_flood",
            "price_collapse",
            "oversaturation",
            "theme_decay",
            "retail_overhang",
            "collector_apathy",
        ):
            value = getattr(self, field)
            if value is not None:
                risks.append((field, value))
        risks.sort(key=lambda x: x[1], reverse=True)
        return risks[:3]


def compute_dead_demand(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Red flag: Sales velocity near zero for 3+ consecutive months.

    Inverted from demand_pressure. High score = dangerously low demand.
    """
    sales = _filter_up_to(item_sales, year, month)
    recent = sales.tail(3)
    if len(recent) == 0:
        return None

    avg_monthly = recent["total_quantity"].mean()

    if avg_monthly < 1:
        return 95.0  # Dead market
    if avg_monthly < 3:
        return 80.0  # Barely alive
    if avg_monthly < 5:
        return 60.0  # Weak demand
    if avg_monthly < 10:
        return 40.0  # Below average
    if avg_monthly < 20:
        return 20.0  # Moderate
    return 5.0  # Healthy demand -- no red flag


def compute_supply_flood(
    snapshots: pd.DataFrame | None,
    item_id: str,
    year: int,
    month: int,
) -> float | None:
    """Red flag: Available supply increasing month-over-month.

    Inverted from supply_velocity. High score = supply flooding the market.
    """
    if snapshots is None or snapshots.empty:
        return None

    item_snaps = snapshots[snapshots["item_id"] == item_id].copy()
    if len(item_snaps) < 2:
        return None

    cutoff = pd.Timestamp(year=year, month=month, day=28)
    item_snaps = item_snaps[item_snaps["scraped_at"] <= cutoff]
    if len(item_snaps) < 2:
        return None

    item_snaps = item_snaps.sort_values("scraped_at")

    older_qty = _extract_snapshot_qty(item_snaps.iloc[-2])
    newer_qty = _extract_snapshot_qty(item_snaps.iloc[-1])

    if older_qty is None or newer_qty is None:
        return None
    if older_qty == 0:
        return 50.0  # Can't compute change

    change_pct = ((newer_qty - older_qty) / older_qty) * 100

    # Increasing supply = danger
    if change_pct >= 50:
        return 95.0  # Supply surging
    if change_pct >= 25:
        return 80.0  # Supply rising fast
    if change_pct >= 10:
        return 65.0  # Supply trending up
    if change_pct >= 0:
        return 45.0  # Stable/slight increase
    if change_pct >= -15:
        return 25.0  # Slightly decreasing (good)
    return 10.0  # Supply dropping -- no red flag


def compute_price_collapse(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Red flag: 6-month price trend is strongly negative.

    Inverted from price_trend. High score = prices in freefall.
    """
    sales = _filter_up_to(item_sales, year, month)
    if len(sales) < 3:
        return None

    recent = sales.tail(6)
    if len(recent) < 3:
        return None

    prices = recent["avg_price"].dropna().values
    if len(prices) < 3:
        return None

    # Linear regression slope
    x = np.arange(len(prices), dtype=float)
    slope = float(np.polyfit(x, prices, 1)[0])

    # Normalize slope as % of mean price
    mean_price = float(np.mean(prices))
    if mean_price <= 0:
        return None
    slope_pct = (slope / mean_price) * 100

    # Negative slope = danger
    if slope_pct <= -10:
        return 95.0  # Price collapse
    if slope_pct <= -5:
        return 80.0  # Strong decline
    if slope_pct <= -2:
        return 65.0  # Moderate decline
    if slope_pct <= 0:
        return 45.0  # Flat/slight decline
    if slope_pct <= 3:
        return 25.0  # Slight growth
    return 10.0  # Price rising -- no red flag


def compute_oversaturation(
    saturation_data: dict | None,
) -> float | None:
    """Red flag: Too many sellers with tight price spread (race to bottom).

    Uses Shopee saturation data. High score = oversaturated market.
    """
    if saturation_data is None:
        return None

    listings = saturation_data.get("listings_count", 0)
    price_spread = saturation_data.get("price_spread_pct", 0)
    unique_sellers = saturation_data.get("unique_sellers", 0)

    if listings == 0:
        return None

    # Many sellers + tight spread = race to bottom
    if listings >= 50 and price_spread < 15:
        return 90.0
    if listings >= 30 and price_spread < 20:
        return 75.0
    if listings >= 20:
        return 60.0
    if listings >= 10:
        return 40.0
    if unique_sellers >= 5:
        return 25.0
    return 10.0


def compute_theme_decay(
    theme: str | None,
) -> float | None:
    """Red flag: Theme has historically low annual growth rate.

    High score = theme is a known underperformer.
    """
    if theme is None:
        return None

    growth = get_theme_annual_growth(theme)

    if growth < 2:
        return 90.0  # Theme barely appreciates
    if growth < 4:
        return 70.0  # Below-average theme
    if growth < 6:
        return 50.0  # Average theme
    if growth < 8:
        return 30.0  # Above average
    return 10.0  # Strong theme -- no red flag


def compute_retail_overhang(
    year: int,
    month: int,
    year_retired: int | None,
    retiring_soon: bool | None,
    stock_level_score: float | None,
) -> float | None:
    """Red flag: Set still widely available at or near retail despite retirement.

    Post-retirement oversupply suppresses secondary market prices.
    High score = retail stock still flooding market.
    """
    if year_retired is None:
        if retiring_soon:
            return 40.0  # About to retire, some risk
        return 20.0  # Active set, moderate risk

    # Years post-retirement
    years_post = year - year_retired + (month / 12.0)

    if years_post < 0:
        return 20.0  # Not retired yet

    # If stock level is available, use it
    if stock_level_score is not None:
        # stock_level from signals.py: high = scarce (bullish)
        # Invert: low stock_level score = still plenty available = danger
        if years_post < 1 and stock_level_score < 40:
            return 85.0  # Just retired but still everywhere
        if years_post < 2 and stock_level_score < 50:
            return 65.0  # 1-2 years out, still available
        if stock_level_score < 30:
            return 50.0  # Lots of supply regardless of age

    # Without stock data, use time-based heuristic
    if years_post < 0.5:
        return 70.0  # Peak oversupply period
    if years_post < 1:
        return 55.0  # Still clearing retail stock
    if years_post < 2:
        return 35.0  # Supply normalizing
    return 15.0  # Retail stock likely cleared


def compute_collector_apathy(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Red flag: Minimal new/used price spread indicates no collector premium.

    When new and used prices converge, collectors see no premium in sealed sets.
    High score = no collector interest.
    """
    sales = _filter_up_to(item_sales, year, month)

    # Need both new and used data at the same month
    if sales.empty:
        return None

    # Get latest month with both conditions
    latest = sales.tail(6)
    if latest.empty:
        return None

    # Compute new vs used spread from avg_price
    # The sales dataframe has condition column if available
    if "condition" in latest.columns:
        new_prices = latest[latest["condition"] == "N"]["avg_price"].values
        used_prices = latest[latest["condition"] == "U"]["avg_price"].values
        if len(new_prices) == 0 or len(used_prices) == 0:
            return None
        avg_new = float(np.mean(new_prices))
        avg_used = float(np.mean(used_prices))
    else:
        # Without condition split, check price variance as proxy
        prices = latest["avg_price"].dropna().values
        if len(prices) < 3:
            return None
        cv = float(np.std(prices) / np.mean(prices)) if np.mean(prices) > 0 else 0
        # Low coefficient of variation = stagnant, no collector activity
        if cv < 0.05:
            return 80.0
        if cv < 0.10:
            return 55.0
        if cv < 0.20:
            return 35.0
        return 15.0

    if avg_new <= 0:
        return None

    spread_pct = ((avg_new - avg_used) / avg_new) * 100

    if spread_pct < 5:
        return 90.0  # No collector premium at all
    if spread_pct < 10:
        return 70.0  # Minimal spread
    if spread_pct < 20:
        return 45.0  # Modest spread
    if spread_pct < 35:
        return 25.0  # Healthy spread
    return 10.0  # Strong collector premium -- no red flag


def compute_all_red_flags(
    *,
    item_sales: pd.DataFrame,
    snapshots: pd.DataFrame | None,
    item_id: str,
    year: int,
    month: int,
    theme: str | None = None,
    year_retired: int | None = None,
    retiring_soon: bool | None = None,
    stock_level_score: float | None = None,
    saturation_data: dict | None = None,
) -> RedFlagSnapshot:
    """Compute all 7 red flag signals for an item at a point in time."""
    return RedFlagSnapshot(
        dead_demand=compute_dead_demand(item_sales, year, month),
        supply_flood=compute_supply_flood(snapshots, item_id, year, month),
        price_collapse=compute_price_collapse(item_sales, year, month),
        oversaturation=compute_oversaturation(saturation_data),
        theme_decay=compute_theme_decay(theme),
        retail_overhang=compute_retail_overhang(
            year, month, year_retired, retiring_soon, stock_level_score
        ),
        collector_apathy=compute_collector_apathy(item_sales, year, month),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_up_to(
    sales: pd.DataFrame,
    year: int,
    month: int,
) -> pd.DataFrame:
    """Filter sales data to rows at or before (year, month)."""
    if sales.empty:
        return sales
    mask = (sales["year"] < year) | (
        (sales["year"] == year) & (sales["month"] <= month)
    )
    return sales[mask]


def _extract_snapshot_qty(row: pd.Series) -> int | None:
    """Extract total_lots from a price history snapshot row."""
    for field in ("six_month_new", "current_new"):
        raw = row.get(field)
        if raw is None:
            continue
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict):
                qty = data.get("total_lots")
                if qty is not None:
                    return int(qty)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return None
