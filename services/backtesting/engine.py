"""Walk-forward backtesting engine.

Iterates chronologically through items, computes signals at each month,
simulates trades, and measures actual returns at various horizons.
"""

from typing import TYPE_CHECKING

import pandas as pd

from services.backtesting.signal_registry import (
    SignalContext,
    compute_modifiers,
    compute_signals,
)
from services.backtesting.signals import _extract_avg_price
from services.backtesting.types import BacktestConfig, SignalSnapshot, TradeResult
from services.backtesting.utils import safe_get, safe_get_int

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def run_backtest(
    conn: "DuckDBPyConnection",
    config: BacktestConfig | None = None,
) -> list[TradeResult]:
    """Run walk-forward backtest across all items with sufficient history.

    Args:
        conn: DuckDB connection
        config: Backtest configuration (defaults to BacktestConfig())

    Returns:
        List of TradeResult objects for all simulated trades
    """
    from services.backtesting.data_loader import (
        load_item_metadata,
        load_monthly_sales,
        load_price_snapshots,
    )

    if config is None:
        config = BacktestConfig()

    # Load all data upfront (once)
    all_sales = load_monthly_sales(conn)
    metadata = load_item_metadata(conn)
    try:
        snapshots = load_price_snapshots(conn)
    except Exception:
        snapshots = None

    # Filter to requested condition
    condition_sales = all_sales[all_sales["condition"] == config.condition]
    if condition_sales.empty:
        # Fallback to any condition
        condition_sales = all_sales

    # Group by item
    grouped = condition_sales.groupby("item_id")

    results: list[TradeResult] = []

    for item_id, item_sales in grouped:
        item_sales = item_sales.sort_values(["year", "month"]).reset_index(drop=True)

        if len(item_sales) < config.min_history_months:
            continue

        # Get metadata for this item
        item_meta = metadata[metadata["item_id"] == item_id]
        if item_meta.empty:
            # Try without -1 suffix
            base_id = str(item_id).replace("-1", "")
            item_meta = metadata[
                metadata["set_number"] == base_id
            ]

        theme = safe_get(item_meta, "theme")
        year_released = safe_get_int(item_meta, "year_released")
        year_retired = safe_get_int(item_meta, "year_retired")
        rrp_cents = safe_get_int(item_meta, "rrp_cents")
        rrp_currency = safe_get(item_meta, "rrp_currency")

        # Walk forward from min_history_months onward
        for idx in range(config.min_history_months, len(item_sales)):
            row = item_sales.iloc[idx]
            eval_year = int(row["year"])
            eval_month = int(row["month"])

            entry_price = _extract_avg_price(row)
            if entry_price is None or entry_price <= 0:
                continue

            ctx = SignalContext(
                item_id=str(item_id),
                eval_year=eval_year,
                eval_month=eval_month,
                item_sales=item_sales,
                snapshots=snapshots,
                theme=theme,
                year_released=year_released,
                year_retired=year_retired,
                rrp_cents=rrp_cents,
                rrp_currency=rrp_currency,
            )

            signals = compute_signals(ctx)
            mods = compute_modifiers(ctx)

            snapshot = SignalSnapshot(
                item_id=str(item_id),
                year=eval_year,
                month=eval_month,
                **signals,
                **mods,
            )

            # Calculate returns at each horizon
            returns = _calculate_returns(
                item_sales, idx, entry_price, config
            )

            # Only include trades where at least one return is available
            if any(v is not None for v in returns.values()):
                results.append(
                    TradeResult(
                        item_id=str(item_id),
                        entry_year=eval_year,
                        entry_month=eval_month,
                        entry_price_cents=int(entry_price),
                        signals=snapshot,
                        returns=returns,
                    )
                )

    return results


def _calculate_returns(
    item_sales: pd.DataFrame,
    entry_idx: int,
    entry_price: float,
    config: BacktestConfig,
) -> dict[str, float | None]:
    """Calculate returns at each horizon from the entry point."""
    returns: dict[str, float | None] = {}
    all_horizons = [
        *((h, f"flip_{h}m") for h in config.flip_horizons),
        *((h, f"hold_{h}m") for h in config.hold_horizons),
    ]

    for horizon, label in all_horizons:
        exit_idx = entry_idx + horizon
        if exit_idx < len(item_sales):
            exit_row = item_sales.iloc[exit_idx]
            exit_price = _extract_avg_price(exit_row)
            if exit_price is not None and exit_price > 0:
                returns[label] = (exit_price - entry_price) / entry_price
            else:
                returns[label] = None
        else:
            returns[label] = None

    return returns
