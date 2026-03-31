"""Signal computation functions for backtesting.

Each function computes a signal score (0-100) using only data available
up to the given month T. No look-ahead bias.
"""

import json

import numpy as np
import pandas as pd

from config.value_investing import (
    DEFAULT_THEME_ANNUAL_GROWTH,
    DEFAULT_THEME_MULTIPLIER,
    RETIREMENT_MULTIPLIERS,
    THEME_MULTIPLIERS,
    get_retirement_multiplier,
    get_subtheme_annual_growth,
    get_theme_annual_growth,
    get_theme_multiplier,
)


def compute_peer_appreciation(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 1: Price at T vs trailing 6-month average.

    High score = price is appreciating above its recent average.
    """
    sales = _filter_up_to(item_sales, year, month)
    if len(sales) < 2:
        return None

    current_row = sales.iloc[-1]
    current_price = _extract_avg_price(current_row)
    if current_price is None or current_price == 0:
        return None

    trailing = sales.iloc[:-1].tail(6)
    trailing_prices = [_extract_avg_price(r) for _, r in trailing.iterrows()]
    trailing_prices = [p for p in trailing_prices if p is not None and p > 0]
    if not trailing_prices:
        return None

    trailing_avg = sum(trailing_prices) / len(trailing_prices)
    if trailing_avg == 0:
        return None

    change_pct = ((current_price - trailing_avg) / trailing_avg) * 100

    if change_pct >= 30:
        return 90.0
    if change_pct >= 15:
        return 75.0
    if change_pct >= 5:
        return 60.0
    if change_pct >= -5:
        return 50.0
    if change_pct >= -15:
        return 35.0
    return 20.0


def compute_demand_pressure(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 2: Trailing 3-month average sales volume.

    High score = high demand.
    """
    sales = _filter_up_to(item_sales, year, month)
    recent = sales.tail(3)
    if len(recent) == 0:
        return None

    avg_monthly = recent["total_quantity"].mean()

    if avg_monthly >= 50:
        return 95.0
    if avg_monthly >= 20:
        return 80.0
    if avg_monthly >= 10:
        return 65.0
    if avg_monthly >= 5:
        return 50.0
    if avg_monthly >= 1:
        return 30.0
    return 15.0


def compute_supply_velocity(
    snapshots: pd.DataFrame | None,
    item_id: str,
    year: int,
    month: int,
) -> float | None:
    """Signal 3: Rate of change in available supply.

    High score = supply is decreasing (bullish).
    """
    if snapshots is None or snapshots.empty:
        return None

    item_snaps = snapshots[snapshots["item_id"] == item_id].copy()
    if len(item_snaps) < 2:
        return None

    # Filter to snapshots before or at month T
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
        return 50.0

    change_pct = ((newer_qty - older_qty) / older_qty) * 100

    # Decreasing supply = high score
    if change_pct <= -30:
        return 90.0
    if change_pct <= -15:
        return 75.0
    if change_pct <= -5:
        return 60.0
    if change_pct <= 5:
        return 50.0
    if change_pct <= 15:
        return 40.0
    return 25.0


def compute_price_trend(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 4: Linear regression slope of avg_price over trailing 6 months.

    High score = upward price trend.
    """
    sales = _filter_up_to(item_sales, year, month).tail(6)
    if len(sales) < 3:
        return None

    prices = [_extract_avg_price(r) for _, r in sales.iterrows()]
    prices = [p for p in prices if p is not None and p > 0]
    if len(prices) < 3:
        return None

    x = np.arange(len(prices), dtype=float)
    y = np.array(prices, dtype=float)
    slope = np.polyfit(x, y, 1)[0]

    avg_price = np.mean(y)
    if avg_price == 0:
        return None

    # Normalize slope as percentage of average price per month
    monthly_change_pct = (slope / avg_price) * 100

    if monthly_change_pct >= 5:
        return 90.0
    if monthly_change_pct >= 2:
        return 75.0
    if monthly_change_pct >= 0.5:
        return 60.0
    if monthly_change_pct >= -0.5:
        return 50.0
    if monthly_change_pct >= -2:
        return 40.0
    return 20.0


def compute_price_vs_rrp(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
    rrp_cents: int | None,
    rrp_currency: str | None,
) -> float | None:
    """Signal 5: Current BrickLink price relative to RRP.

    Below RRP = flip opportunity. Above RRP = appreciation.
    """
    if rrp_cents is None or rrp_cents == 0:
        return None

    sales = _filter_up_to(item_sales, year, month)
    if sales.empty:
        return None

    current_price = _extract_avg_price(sales.iloc[-1])
    if current_price is None or current_price == 0:
        return None

    # Convert RRP to same unit (cents)
    ratio = current_price / rrp_cents

    # Below RRP is interesting for flipping; above shows appreciation
    if ratio >= 2.0:
        return 95.0  # 2x+ RRP, strong appreciation
    if ratio >= 1.5:
        return 85.0
    if ratio >= 1.2:
        return 70.0
    if ratio >= 1.0:
        return 55.0
    if ratio >= 0.8:
        return 40.0  # Below RRP but not deeply
    if ratio >= 0.6:
        return 30.0  # Good flip opportunity
    return 20.0  # Deep discount - investigate why


def compute_lifecycle_position(
    year_released: int | None,
    year_retired: int | None,
    eval_year: int,
    retiring_soon: bool = False,
) -> float | None:
    """Signal 6: Lifecycle position based on retirement status.

    High score = post-retirement (J-curve appreciation zone).
    retiring_soon acts as a leading indicator, boosting active sets
    that are about to retire.
    """
    if year_released is None:
        return None

    if year_retired is not None:
        years_post = eval_year - year_retired
        multiplier = get_retirement_multiplier(years_post)
    elif retiring_soon:
        multiplier = RETIREMENT_MULTIPLIERS.retiring_soon
    else:
        age = eval_year - year_released
        if age >= 4:
            # Likely retired, estimate
            multiplier = get_retirement_multiplier(age - 2)
        else:
            multiplier = get_retirement_multiplier(None)

    # Convert multiplier (0.95-2.0) to 0-100 score
    return min(100.0, max(0.0, (multiplier - 0.90) / (2.0 - 0.90) * 100))


def compute_stock_level(
    snapshots: pd.DataFrame | None,
    item_id: str,
    year: int,
    month: int,
) -> float | None:
    """Signal 7: Current inventory level.

    High score = low stock (scarce).
    """
    if snapshots is None or snapshots.empty:
        return None

    item_snaps = snapshots[snapshots["item_id"] == item_id]
    if item_snaps.empty:
        return None

    cutoff = pd.Timestamp(year=year, month=month, day=28)
    item_snaps = item_snaps[item_snaps["scraped_at"] <= cutoff]
    if item_snaps.empty:
        return None

    latest = item_snaps.sort_values("scraped_at").iloc[-1]
    total_lots = _extract_snapshot_lots(latest)

    if total_lots is None:
        return None

    if total_lots == 0:
        return 95.0
    if total_lots <= 5:
        return 85.0
    if total_lots <= 20:
        return 65.0
    if total_lots <= 50:
        return 45.0
    if total_lots <= 100:
        return 30.0
    return 15.0


def compute_momentum(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 8: Sales acceleration (month-over-month change in velocity).

    High score = accelerating sales.
    """
    sales = _filter_up_to(item_sales, year, month)
    if len(sales) < 4:
        return None

    recent_3 = sales.tail(3)["total_quantity"].values
    prior_3 = sales.tail(6).head(3)["total_quantity"].values

    if len(prior_3) < 2:
        return None

    recent_avg = float(np.mean(recent_3))
    prior_avg = float(np.mean(prior_3))

    if prior_avg == 0:
        return 60.0 if recent_avg > 0 else 50.0

    change_pct = ((recent_avg - prior_avg) / prior_avg) * 100

    if change_pct >= 50:
        return 95.0
    if change_pct >= 20:
        return 80.0
    if change_pct >= -10:
        return 60.0
    if change_pct >= -30:
        return 40.0
    return 20.0


def compute_theme_quality(theme: str | None) -> float | None:
    """Signal 9: Theme-based collector appeal.

    High score = premium theme.
    """
    if theme is None:
        return None

    multiplier = get_theme_multiplier(theme)
    # Convert multiplier (0.50-1.45) to 0-100 score
    return min(100.0, max(0.0, (multiplier - 0.50) / (1.45 - 0.50) * 100))


def compute_theme_growth(
    theme: str | None,
    subtheme: str | None = None,
) -> float | None:
    """Signal 12: Theme-level annual price growth rate.

    High score = theme prices are appreciating strongly year-over-year.
    Based on historical BrickLink market data across all sets in a theme.
    Uses sub-theme growth when available for higher granularity.
    """
    if theme is None:
        return None

    # Prefer sub-theme growth (more granular) when available
    subtheme_growth = get_subtheme_annual_growth(theme, subtheme)
    growth_pct = subtheme_growth if subtheme_growth is not None else get_theme_annual_growth(theme)

    # Map annual growth % to 0-100 score
    if growth_pct >= 15.0:
        return 95.0
    if growth_pct >= 10.0:
        return 80.0
    if growth_pct >= 7.0:
        return 65.0
    if growth_pct >= 5.0:
        return 50.0
    if growth_pct >= 3.0:
        return 35.0
    return 20.0


def compute_community_quality(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 10: Transaction count (market liquidity).

    High score = liquid market (many transactions).
    """
    sales = _filter_up_to(item_sales, year, month)
    recent = sales.tail(3)
    if recent.empty:
        return None

    total_transactions = recent["times_sold"].sum()

    if total_transactions >= 300:
        return 95.0
    if total_transactions >= 150:
        return 80.0
    if total_transactions >= 50:
        return 65.0
    if total_transactions >= 20:
        return 50.0
    if total_transactions >= 5:
        return 30.0
    return 15.0


def compute_collector_premium(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 11: Price spread health.

    Healthy spread (10-50%) indicates a well-functioning market.
    """
    sales = _filter_up_to(item_sales, year, month).tail(3)
    if sales.empty:
        return None

    spreads = []
    for _, row in sales.iterrows():
        avg_p = _extract_avg_price(row)
        min_p = _extract_price(row, "min_price")
        max_p = _extract_price(row, "max_price")
        if avg_p and min_p and max_p and avg_p > 0:
            spread = (max_p - min_p) / avg_p
            spreads.append(spread)

    if not spreads:
        return None

    avg_spread = sum(spreads) / len(spreads)

    # Healthy spread = good collector market
    if 0.1 <= avg_spread <= 0.3:
        return 85.0  # Ideal
    if 0.05 <= avg_spread <= 0.5:
        return 70.0  # Good
    if avg_spread < 0.05:
        return 40.0  # Too tight (no premium being paid)
    if avg_spread <= 1.0:
        return 50.0  # Moderate volatility
    return 25.0  # High volatility


def compute_value_opportunity(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 13: Value opportunity (contrarian to peer appreciation).

    High score = price is below trailing average (buying opportunity).
    Implements value investing logic: buy when price is depressed.
    """
    sales = _filter_up_to(item_sales, year, month)
    if len(sales) < 2:
        return None

    current_row = sales.iloc[-1]
    current_price = _extract_avg_price(current_row)
    if current_price is None or current_price == 0:
        return None

    trailing = sales.iloc[:-1].tail(6)
    trailing_prices = [_extract_avg_price(r) for _, r in trailing.iterrows()]
    trailing_prices = [p for p in trailing_prices if p is not None and p > 0]
    if not trailing_prices:
        return None

    trailing_avg = sum(trailing_prices) / len(trailing_prices)
    if trailing_avg == 0:
        return None

    change_pct = ((current_price - trailing_avg) / trailing_avg) * 100

    # INVERTED scoring: below average = high score (buying opportunity)
    if change_pct <= -30:
        return 90.0
    if change_pct <= -15:
        return 75.0
    if change_pct <= -5:
        return 60.0
    if change_pct <= 5:
        return 50.0
    if change_pct <= 15:
        return 35.0
    return 20.0


def compute_minifig_appeal(
    minifig_data: object | None,
    entry_price_cents: int | None,
) -> float | None:
    """Signal 14: Minifigure value and rarity appeal.

    Combines three factors:
    1. Value floor: minifig value as fraction of set price
    2. Exclusivity: % of minifigs exclusive to this set (rare = valuable)
    3. Arbitrage: if shared minifigs can be obtained cheaper elsewhere,
       that LOWERS this set's appeal; if THIS set is the cheapest way
       to get them, that's a bonus.

    Returns None when minifig data is unavailable.
    """
    if minifig_data is None:
        return None
    if entry_price_cents is None or entry_price_cents <= 0:
        return None

    total_value = getattr(minifig_data, "total_value_cents", 0)
    exclusive_count = getattr(minifig_data, "exclusive_count", 0)
    total_count = getattr(minifig_data, "total_count", 0)
    exclusive_value = getattr(minifig_data, "exclusive_value_cents", 0)
    cheapest_alt_price = getattr(
        minifig_data, "cheapest_alternative_price_cents", None
    )

    if total_value <= 0 or total_count <= 0:
        return None

    # Factor 1: Value floor ratio (0-40 points)
    value_ratio = total_value / entry_price_cents
    if value_ratio >= 1.0:
        value_score = 40.0
    elif value_ratio >= 0.5:
        value_score = 30.0
    elif value_ratio >= 0.2:
        value_score = 20.0
    else:
        value_score = 10.0

    # Factor 2: Exclusivity ratio (0-40 points)
    exclusivity_ratio = exclusive_count / total_count
    if exclusivity_ratio >= 0.8:
        excl_score = 40.0  # Most minifigs are exclusive
    elif exclusivity_ratio >= 0.5:
        excl_score = 30.0
    elif exclusivity_ratio >= 0.2:
        excl_score = 20.0
    else:
        excl_score = 10.0  # Most minifigs appear in other sets

    # Factor 3: Arbitrage position (0-20 points)
    # If THIS set is cheaper than alternatives for the same minifigs = bonus
    # If alternatives are cheaper = penalty
    if cheapest_alt_price is not None and cheapest_alt_price > 0:
        if entry_price_cents < cheapest_alt_price:
            arb_score = 20.0  # This set is the cheapest way to get the figs
        elif entry_price_cents < cheapest_alt_price * 1.2:
            arb_score = 12.0  # Competitive price
        else:
            arb_score = 5.0  # Can get these figs cheaper elsewhere
    else:
        # No alternatives found (all exclusive) or no price data
        arb_score = 15.0 if exclusive_count == total_count else 10.0

    return min(95.0, value_score + excl_score + arb_score)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_up_to(
    sales: pd.DataFrame,
    year: int,
    month: int,
) -> pd.DataFrame:
    """Filter sales DataFrame to rows on or before (year, month)."""
    mask = (sales["year"] < year) | (
        (sales["year"] == year) & (sales["month"] <= month)
    )
    return sales[mask].sort_values(["year", "month"])


def _extract_avg_price(row: pd.Series) -> float | None:
    """Extract avg_price cents from a monthly sales row."""
    val = row.get("avg_price")
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (int, float, np.integer, np.floating)):
        return float(val)
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return float(parsed.get("amount", 0))
            return float(parsed)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    if isinstance(val, dict):
        return float(val.get("amount", 0))
    return None


def _extract_price(row: pd.Series, field: str) -> float | None:
    """Extract a price field's amount from a monthly sales row."""
    val = row.get(field)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (int, float, np.integer, np.floating)):
        return float(val)
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return float(parsed.get("amount", 0))
            return float(parsed)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    if isinstance(val, dict):
        return float(val.get("amount", 0))
    return None


def _extract_snapshot_qty(row: pd.Series) -> int | None:
    """Extract total_qty from a price history snapshot's current_new box."""
    return _extract_snapshot_field(row, "current_new", "total_qty")


def _extract_snapshot_lots(row: pd.Series) -> int | None:
    """Extract total_lots from a price history snapshot's current_new box."""
    return _extract_snapshot_field(row, "current_new", "total_lots")


def _extract_snapshot_field(
    row: pd.Series,
    box_name: str,
    field: str,
) -> int | None:
    """Extract a field from a pricing box in a snapshot row."""
    val = row.get(box_name)
    if val is None:
        return None
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(val, dict):
        result = val.get(field)
        if result is not None:
            return int(result)
    return None
