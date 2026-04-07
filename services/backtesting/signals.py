"""Signal computation functions for backtesting.

Each function computes a signal score (0-100) using only data available
up to the given month T. No look-ahead bias.
"""

import json

import numpy as np
import pandas as pd

from config.value_investing import (
    DEFAULT_THEME_ANNUAL_GROWTH,
    RETIREMENT_MULTIPLIERS,
    get_retirement_multiplier,
    get_subtheme_annual_growth,
    get_theme_annual_growth,
)


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
    cutoff = pd.Timestamp(year=year, month=month, day=28, tz="UTC")
    scraped_at = item_snaps["scraped_at"]
    if hasattr(scraped_at.dt, "tz") and scraped_at.dt.tz is None:
        scraped_at = scraped_at.dt.tz_localize("UTC")
    item_snaps = item_snaps[scraped_at <= cutoff]
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

    cutoff = pd.Timestamp(year=year, month=month, day=28, tz="UTC")
    scraped_at = item_snaps["scraped_at"]
    if hasattr(scraped_at.dt, "tz") and scraped_at.dt.tz is None:
        scraped_at = scraped_at.dt.tz_localize("UTC")
    item_snaps = item_snaps[scraped_at <= cutoff]
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


def _parse_snapshot_box(row: pd.Series, box_name: str) -> dict | None:
    """Parse a pricing box from a snapshot row into a dict."""
    val = row.get(box_name)
    if val is None:
        return None
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(val, dict):
        return val
    return None


def _extract_snapshot_field(
    row: pd.Series,
    box_name: str,
    field: str,
) -> int | None:
    """Extract a field from a pricing box in a snapshot row."""
    box = _parse_snapshot_box(row, box_name)
    if box is None:
        return None
    result = box.get(field)
    if result is not None:
        return int(result)
    return None


def _extract_snapshot_price_amount(
    row: pd.Series,
    box_name: str,
    price_field: str,
) -> int | None:
    """Extract amount (cents) from a nested price field in a snapshot box.

    Price fields like avg_price, qty_avg_price are stored as
    {"currency": "USD", "amount": 1234}. This extracts the amount.
    """
    box = _parse_snapshot_box(row, box_name)
    if box is None:
        return None
    price_obj = box.get(price_field)
    if price_obj is None:
        return None
    if isinstance(price_obj, dict):
        amount = price_obj.get("amount")
        if amount is not None:
            return int(amount)
    if isinstance(price_obj, (int, float)):
        return int(price_obj)
    return None


def _get_latest_snapshot(
    snapshots: pd.DataFrame,
    item_id: str,
    year: int,
    month: int,
) -> pd.Series | None:
    """Get the latest snapshot for an item at or before (year, month)."""
    item_snaps = snapshots[snapshots["item_id"] == item_id]
    if item_snaps.empty:
        return None
    cutoff = pd.Timestamp(year=year, month=month, day=28, tz="UTC")
    scraped_at = item_snaps["scraped_at"]
    if hasattr(scraped_at.dt, "tz") and scraped_at.dt.tz is None:
        scraped_at = scraped_at.dt.tz_localize("UTC")
    item_snaps = item_snaps[scraped_at <= cutoff]
    if item_snaps.empty:
        return None
    return item_snaps.sort_values("scraped_at").iloc[-1]


def compute_price_wall(
    snapshots: pd.DataFrame | None,
    item_id: str,
    year: int,
    month: int,
) -> float | None:
    """Signal 15: Price wall detection from listing inventory distribution.

    Compares qty_avg_price (volume-weighted) to avg_price (simple average)
    in current_new listings. Positive divergence means volume clusters above
    the average price (bullish support); negative means bulk inventory sits
    below average (bearish resistance / dumping).

    High score = strong price support above average.
    """
    if snapshots is None or snapshots.empty:
        return None

    latest = _get_latest_snapshot(snapshots, item_id, year, month)
    if latest is None:
        return None

    avg_price = _extract_snapshot_price_amount(latest, "current_new", "avg_price")
    qty_avg_price = _extract_snapshot_price_amount(latest, "current_new", "qty_avg_price")
    min_price = _extract_snapshot_price_amount(latest, "current_new", "min_price")
    max_price = _extract_snapshot_price_amount(latest, "current_new", "max_price")

    if avg_price is None or qty_avg_price is None or avg_price == 0:
        return None
    if min_price is None or max_price is None:
        return None

    # Divergence: positive = volume above average (bullish)
    divergence = (qty_avg_price - avg_price) / avg_price

    # Position in range: 0 = clusters at min (dumping), 1 = clusters at max
    price_range = max_price - min_price
    if price_range > 0:
        position = (qty_avg_price - min_price) / price_range
    else:
        position = 0.5  # All at same price

    # Combined scoring
    if divergence >= 0.15 and position > 0.65:
        return 90.0
    if divergence >= 0.08:
        return 75.0
    if divergence >= 0.05:
        return 65.0
    if divergence >= -0.05:
        return 55.0
    if divergence >= -0.08:
        return 45.0
    if divergence >= -0.15:
        return 35.0
    if position < 0.35:
        return 20.0
    return 25.0


def compute_listing_ratio(
    snapshots: pd.DataFrame | None,
    item_id: str,
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 16: Listing-to-transaction ratio (months of inventory).

    Compares current listing inventory (from snapshots) against trailing
    3-month transaction velocity (from monthly sales). Low ratio means
    undersupply (bullish); high ratio means oversupply (bearish).

    High score = undersupply (bullish).
    """
    if snapshots is None or snapshots.empty:
        return None

    latest = _get_latest_snapshot(snapshots, item_id, year, month)
    if latest is None:
        return None

    total_qty = _extract_snapshot_field(latest, "current_new", "total_qty")
    total_lots = _extract_snapshot_field(latest, "current_new", "total_lots")

    if total_qty is None:
        return None

    # Trailing 3-month sales velocity
    sales = _filter_up_to(item_sales, year, month)
    recent = sales.tail(3)

    if recent.empty:
        # Listings exist but no sales data at all
        return 10.0 if total_qty > 0 else None

    avg_monthly_qty = float(recent["total_quantity"].mean())
    avg_monthly_times = float(recent["times_sold"].mean())

    # Zero sales but listings exist = extreme oversupply
    if avg_monthly_qty <= 0:
        return 10.0

    # Primary: months of unit inventory
    qty_ratio = total_qty / avg_monthly_qty

    # Secondary: lots-to-transactions ratio for adjustment
    adjustment = 0.0
    if total_lots is not None and avg_monthly_times > 0:
        lots_ratio = total_lots / avg_monthly_times
        # If lots_ratio diverges strongly from qty_ratio, adjust
        if qty_ratio > 0:
            relative_diff = (lots_ratio - qty_ratio) / qty_ratio
            if relative_diff > 0.5:
                adjustment = -5.0  # More sellers per transaction than expected
            elif relative_diff < -0.5:
                adjustment = 5.0  # Fewer sellers = tighter supply

    # Score based on months of inventory (inverted: low = bullish)
    if qty_ratio < 0.5:
        base = 95.0
    elif qty_ratio < 1.0:
        base = 80.0
    elif qty_ratio < 3.0:
        base = 65.0
    elif qty_ratio < 6.0:
        base = 50.0
    elif qty_ratio < 12.0:
        base = 35.0
    elif qty_ratio < 24.0:
        base = 20.0
    else:
        base = 10.0

    return min(100.0, max(0.0, base + adjustment))


def compute_volume_price_confirm(
    item_sales: pd.DataFrame,
    year: int,
    month: int,
) -> float | None:
    """Signal 17: Volume-price confirmation.

    Checks whether volume confirms the price direction. A price move on
    rising volume is trustworthy; on falling volume it is suspect.

    Quadrant scoring:
    - Price up + volume up   = confirmed rally (high score)
    - Price down + volume up = capitulation / potential reversal (moderate)
    - Price up + volume down = weak rally / distribution (low-moderate)
    - Price down + volume down = apathy (low score)

    High score = volume confirms a bullish price move.
    """
    sales = _filter_up_to(item_sales, year, month)
    if len(sales) < 6:
        return None

    recent_3 = sales.tail(3)
    prior_3 = sales.tail(6).head(3)

    if len(prior_3) < 2:
        return None

    # Price direction
    recent_prices = [_extract_avg_price(r) for _, r in recent_3.iterrows()]
    prior_prices = [_extract_avg_price(r) for _, r in prior_3.iterrows()]
    recent_prices = [p for p in recent_prices if p is not None and p > 0]
    prior_prices = [p for p in prior_prices if p is not None and p > 0]

    if not recent_prices or not prior_prices:
        return None

    avg_recent_price = sum(recent_prices) / len(recent_prices)
    avg_prior_price = sum(prior_prices) / len(prior_prices)

    if avg_prior_price == 0:
        return None

    price_change_pct = (avg_recent_price - avg_prior_price) / avg_prior_price

    # Volume direction
    recent_vol = float(recent_3["total_quantity"].mean())
    prior_vol = float(prior_3["total_quantity"].mean())

    if prior_vol == 0:
        vol_change_pct = 1.0 if recent_vol > 0 else 0.0
    else:
        vol_change_pct = (recent_vol - prior_vol) / prior_vol

    price_up = price_change_pct > 0.02  # >2% threshold to avoid noise
    price_down = price_change_pct < -0.02
    vol_up = vol_change_pct > 0.1  # >10% volume increase
    vol_down = vol_change_pct < -0.1

    # Quadrant scoring
    if price_up and vol_up:
        # Confirmed rally -- strength scales with magnitude
        if price_change_pct >= 0.15 and vol_change_pct >= 0.30:
            return 95.0
        if price_change_pct >= 0.08:
            return 85.0
        return 75.0
    if price_up and vol_down:
        # Weak rally / distribution -- smart money may be exiting
        return 40.0
    if price_down and vol_up:
        # Capitulation -- heavy selling, potential reversal
        return 45.0
    if price_down and vol_down:
        # Apathy -- no interest
        return 25.0

    # Neutral zone (price and/or volume within noise thresholds)
    return 55.0


def compute_new_used_spread(
    snapshots: pd.DataFrame | None,
    item_id: str,
    year: int,
    month: int,
) -> float | None:
    """Signal 18: New vs Used price spread dynamics.

    Tracks the spread between new and used condition pricing. A narrowing
    spread signals rising collector demand (used catching up to new).
    Used price exceeding new price indicates extreme sealed-product scarcity.

    Uses two consecutive snapshots to detect spread direction.

    High score = narrowing spread or used exceeding new (bullish collector demand).
    """
    if snapshots is None or snapshots.empty:
        return None

    item_snaps = snapshots[snapshots["item_id"] == item_id].copy()
    if item_snaps.empty:
        return None

    cutoff = pd.Timestamp(year=year, month=month, day=28, tz="UTC")
    scraped_at = item_snaps["scraped_at"]
    if hasattr(scraped_at.dt, "tz") and scraped_at.dt.tz is None:
        scraped_at = scraped_at.dt.tz_localize("UTC")
    item_snaps = item_snaps[scraped_at <= cutoff]
    if item_snaps.empty:
        return None

    item_snaps = item_snaps.sort_values("scraped_at")
    latest = item_snaps.iloc[-1]

    new_price = _extract_snapshot_price_amount(latest, "current_new", "avg_price")
    used_price = _extract_snapshot_price_amount(latest, "current_used", "avg_price")

    if new_price is None or used_price is None:
        return None
    if new_price == 0:
        return None

    # Current spread ratio (used / new)
    current_ratio = used_price / new_price

    # Used exceeding new = extreme scarcity of sealed product
    if current_ratio >= 1.0:
        return 95.0

    # Check spread direction if we have a prior snapshot
    if len(item_snaps) >= 2:
        prior = item_snaps.iloc[-2]
        prior_new = _extract_snapshot_price_amount(prior, "current_new", "avg_price")
        prior_used = _extract_snapshot_price_amount(prior, "current_used", "avg_price")

        if prior_new and prior_used and prior_new > 0:
            prior_ratio = prior_used / prior_new
            ratio_change = current_ratio - prior_ratio

            # Narrowing spread (used catching up) = bullish
            if ratio_change > 0.05:
                if current_ratio >= 0.8:
                    return 85.0  # Already tight + narrowing
                return 75.0
            # Widening spread (used falling behind) = bearish
            if ratio_change < -0.05:
                if current_ratio < 0.5:
                    return 20.0  # Wide + widening
                return 35.0

    # Static spread scoring (no trend data or stable spread)
    if current_ratio >= 0.85:
        return 80.0  # Very tight spread -- strong collector market
    if current_ratio >= 0.70:
        return 65.0
    if current_ratio >= 0.55:
        return 50.0
    if current_ratio >= 0.40:
        return 35.0
    return 20.0  # Very wide spread -- casual market only
