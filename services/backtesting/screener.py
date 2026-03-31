"""Compute current signal snapshots for items (screener mode).

Unlike the walk-forward engine which backtests historically, this module
computes signals at the latest available month — providing a real-time
"financial screener" view.
"""

import logging
from typing import TYPE_CHECKING

import pandas as pd

from config.kelly import APPLY_MODIFIERS, DEFAULT_SIGNAL_WEIGHT, SIGNAL_WEIGHTS
from services.backtesting.data_loader import (
    load_item_metadata,
    load_minifig_data,
    load_monthly_sales,
    load_price_snapshots,
)
from services.backtesting.modifiers import (
    compute_niche_penalty,
    compute_shelf_life,
    compute_subtheme_premium,
)
from services.backtesting.signals import (
    _extract_avg_price,
    compute_collector_premium,
    compute_demand_pressure,
    compute_lifecycle_position,
    compute_listing_ratio,
    compute_minifig_appeal,
    compute_new_used_spread,
    compute_price_trend,
    compute_price_vs_rrp,
    compute_price_wall,
    compute_stock_level,
    compute_supply_velocity,
    compute_theme_growth,
    compute_value_opportunity,
    compute_volume_price_confirm,
)

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def _compute_item_signals(
    item_id: str,
    item_sales: pd.DataFrame,
    item_meta: pd.DataFrame,
    snapshots: pd.DataFrame | None,
    minifig_data: dict | None = None,
) -> dict | None:
    """Compute all signals for a single item at its latest available month.

    Returns a dict with signals, modifiers, and metadata, or None if
    insufficient data.
    """
    item_sales = item_sales.sort_values(["year", "month"]).reset_index(
        drop=True
    )

    if len(item_sales) < 3:
        return None

    latest_row = item_sales.iloc[-1]
    eval_year = int(latest_row["year"])
    eval_month = int(latest_row["month"])

    entry_price = _extract_avg_price(latest_row)
    if entry_price is None or entry_price <= 0:
        return None

    theme = _safe_get(item_meta, "theme")
    title = _safe_get(item_meta, "title")
    set_number = _safe_get(item_meta, "set_number")
    year_released = _safe_get_int(item_meta, "year_released")
    year_retired = _safe_get_int(item_meta, "year_retired")
    rrp_cents = _safe_get_int(item_meta, "rrp_cents")
    rrp_currency = _safe_get(item_meta, "rrp_currency")
    retiring_soon = _safe_get_bool(item_meta, "retiring_soon")

    signals = {
        "demand_pressure": compute_demand_pressure(
            item_sales, eval_year, eval_month
        ),
        "supply_velocity": compute_supply_velocity(
            snapshots, item_id, eval_year, eval_month
        ),
        "price_trend": compute_price_trend(
            item_sales, eval_year, eval_month
        ),
        "price_vs_rrp": compute_price_vs_rrp(
            item_sales, eval_year, eval_month, rrp_cents, rrp_currency
        ),
        "lifecycle_position": compute_lifecycle_position(
            year_released, year_retired, eval_year, retiring_soon
        ),
        "stock_level": compute_stock_level(
            snapshots, item_id, eval_year, eval_month
        ),
        "collector_premium": compute_collector_premium(
            item_sales, eval_year, eval_month
        ),
        "theme_growth": compute_theme_growth(theme),
        "value_opportunity": compute_value_opportunity(
            item_sales, eval_year, eval_month
        ),
        "minifig_appeal": compute_minifig_appeal(
            (minifig_data or {}).get(item_id),
            int(entry_price),
        ),
        "price_wall": compute_price_wall(
            snapshots, item_id, eval_year, eval_month
        ),
        "listing_ratio": compute_listing_ratio(
            snapshots, item_id, item_sales, eval_year, eval_month
        ),
        "volume_price_confirm": compute_volume_price_confirm(
            item_sales, eval_year, eval_month
        ),
        "new_used_spread": compute_new_used_spread(
            snapshots, item_id, eval_year, eval_month
        ),
    }

    modifiers = {
        "mod_shelf_life": compute_shelf_life(year_released, year_retired),
        "mod_subtheme": compute_subtheme_premium(theme),
        "mod_niche": compute_niche_penalty(theme),
    }

    # Weighted composite score
    weighted_sum = 0.0
    weight_sum = 0.0
    for name, value in signals.items():
        if value is not None:
            w = SIGNAL_WEIGHTS.get(name, DEFAULT_SIGNAL_WEIGHT)
            weighted_sum += value * w
            weight_sum += w

    composite = round(weighted_sum / weight_sum, 1) if weight_sum > 0 else None

    # Apply modifiers as multipliers to composite
    if composite is not None and APPLY_MODIFIERS:
        modifier_product = (
            modifiers["mod_shelf_life"]
            * modifiers["mod_subtheme"]
            * modifiers["mod_niche"]
        )
        composite = round(
            min(100.0, max(0.0, composite * modifier_product)), 1
        )

    return {
        "item_id": item_id,
        "set_number": set_number or item_id.removesuffix("-1"),
        "title": title,
        "theme": theme,
        "year_released": year_released,
        "year_retired": year_retired,
        "rrp_cents": rrp_cents,
        "rrp_currency": rrp_currency,
        "entry_price_cents": int(entry_price),
        "eval_year": eval_year,
        "eval_month": eval_month,
        "composite_score": composite,
        **signals,
        **modifiers,
    }


def compute_item_signals(
    conn: "DuckDBPyConnection",
    set_number: str,
    condition: str = "new",
) -> dict | None:
    """Compute current signals for a single item by set_number."""
    all_sales = load_monthly_sales(conn)
    metadata = load_item_metadata(conn)

    try:
        snapshots = load_price_snapshots(conn)
    except Exception:
        logger.warning(
            "Price snapshots unavailable, snapshot-based signals will be skipped",
            exc_info=True,
        )
        snapshots = None

    mfig_data = load_minifig_data(conn)

    condition_sales = all_sales[all_sales["condition"] == condition]
    if condition_sales.empty:
        condition_sales = all_sales

    # Find the item_id matching this set_number
    item_meta = metadata[metadata["set_number"] == set_number]
    if item_meta.empty:
        return None

    # Try item_id from metadata first, then fallback patterns
    item_id_val = _safe_get(item_meta, "item_id")
    candidate_ids = [
        item_id_val,
        f"{set_number}-1",
        set_number,
    ]

    for candidate in candidate_ids:
        if candidate is None:
            continue
        item_sales = condition_sales[condition_sales["item_id"] == candidate]
        if not item_sales.empty:
            return _compute_item_signals(
                candidate, item_sales, item_meta, snapshots, mfig_data
            )

    return None


def compute_all_signals(
    conn: "DuckDBPyConnection",
    condition: str = "new",
) -> list[dict]:
    """Compute current signals for all items with sufficient data."""
    all_sales = load_monthly_sales(conn)
    metadata = load_item_metadata(conn)

    try:
        snapshots = load_price_snapshots(conn)
    except Exception:
        logger.warning(
            "Price snapshots unavailable, snapshot-based signals will be skipped",
            exc_info=True,
        )
        snapshots = None

    mfig_data = load_minifig_data(conn)

    condition_sales = all_sales[all_sales["condition"] == condition]
    if condition_sales.empty:
        condition_sales = all_sales

    grouped = condition_sales.groupby("item_id")
    results: list[dict] = []

    for item_id, item_sales in grouped:
        item_meta = metadata[metadata["item_id"] == item_id]
        if item_meta.empty:
            base_id = str(item_id).removesuffix("-1")
            item_meta = metadata[metadata["set_number"] == base_id]

        result = _compute_item_signals(
            str(item_id), item_sales, item_meta, snapshots, mfig_data
        )
        if result is not None:
            results.append(result)

    results.sort(
        key=lambda r: r.get("composite_score") or 0,
        reverse=True,
    )

    return results


def _safe_get(df: pd.DataFrame, col: str) -> str | None:
    if df.empty or col not in df.columns:
        return None
    val = df.iloc[0][col]
    if pd.isna(val):
        return None
    return str(val)


def _safe_get_bool(df: pd.DataFrame, col: str) -> bool:
    if df.empty or col not in df.columns:
        return False
    val = df.iloc[0][col]
    if pd.isna(val):
        return False
    return bool(val)


def _safe_get_int(df: pd.DataFrame, col: str) -> int | None:
    if df.empty or col not in df.columns:
        return None
    val = df.iloc[0][col]
    if pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
