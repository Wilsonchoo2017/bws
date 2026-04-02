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
    load_monthly_sales,
    load_price_snapshots,
)
from services.backtesting.signal_registry import (
    SignalContext,
    compute_modifiers,
    compute_signals,
)
from services.backtesting.signals import _extract_avg_price
from services.backtesting.utils import safe_get, safe_get_bool, safe_get_int

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def _compute_item_signals(
    item_id: str,
    item_sales: pd.DataFrame,
    item_meta: pd.DataFrame,
    snapshots: pd.DataFrame | None,
    signal_weights: dict[str, float] | None = None,
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

    theme = safe_get(item_meta, "theme")
    title = safe_get(item_meta, "title")
    set_number = safe_get(item_meta, "set_number")
    year_released = safe_get_int(item_meta, "year_released")
    year_retired = safe_get_int(item_meta, "year_retired")
    rrp_cents = safe_get_int(item_meta, "rrp_cents")
    rrp_currency = safe_get(item_meta, "rrp_currency")
    retiring_soon = safe_get_bool(item_meta, "retiring_soon")
    release_date = safe_get(item_meta, "release_date")
    parts_count = safe_get_int(item_meta, "parts_count")
    rrp_usd_cents = safe_get_int(item_meta, "rrp_usd_cents")

    ctx = SignalContext(
        item_id=item_id,
        eval_year=eval_year,
        eval_month=eval_month,
        item_sales=item_sales,
        snapshots=snapshots,
        theme=theme,
        year_released=year_released,
        year_retired=year_retired,
        rrp_cents=rrp_cents,
        rrp_currency=rrp_currency,
        retiring_soon=retiring_soon,
    )

    signals = compute_signals(ctx)
    modifiers = compute_modifiers(ctx)

    # Weighted composite score
    weights = signal_weights if signal_weights is not None else SIGNAL_WEIGHTS
    weighted_sum = 0.0
    weight_sum = 0.0
    for name, value in signals.items():
        if value is not None:
            w = weights.get(name, DEFAULT_SIGNAL_WEIGHT)
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
        # Cohort bucketing inputs
        "release_date": release_date,
        "parts_count": parts_count,
        "rrp_usd_cents": rrp_usd_cents,
        **signals,
        **modifiers,
    }


def compute_item_signals(
    conn: "DuckDBPyConnection",
    set_number: str,
    condition: str = "new",
    signal_weights: dict[str, float] | None = None,
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

    condition_sales = all_sales[all_sales["condition"] == condition]
    if condition_sales.empty:
        condition_sales = all_sales

    # Find the item_id matching this set_number
    item_meta = metadata[metadata["set_number"] == set_number]
    if item_meta.empty:
        return None

    # Try item_id from metadata first, then fallback patterns
    item_id_val = safe_get(item_meta, "item_id")
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
                candidate, item_sales, item_meta, snapshots,
                signal_weights,
            )

    return None


def compute_all_signals(
    conn: "DuckDBPyConnection",
    condition: str = "new",
    signal_weights: dict[str, float] | None = None,
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
            str(item_id), item_sales, item_meta, snapshots,
            signal_weights,
        )
        if result is not None:
            results.append(result)

    results.sort(
        key=lambda r: r.get("composite_score") or 0,
        reverse=True,
    )

    return results


def compute_all_signals_with_cohort(
    conn: "DuckDBPyConnection",
    condition: str = "new",
    signal_weights: dict[str, float] | None = None,
) -> list[dict]:
    """Compute signals for all items, enriched with cohort-relative ranks."""
    from services.backtesting.cohort import enrich_with_cohort_ranks

    items = compute_all_signals(conn, condition, signal_weights)
    return enrich_with_cohort_ranks(items)
