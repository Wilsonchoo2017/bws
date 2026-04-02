"""Signal registry for centralized signal computation.

Eliminates duplication between engine.py and screener.py by providing
a single registry of signal and modifier computations.
"""

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from services.backtesting.modifiers import (
    compute_niche_penalty,
    compute_shelf_life,
    compute_subtheme_premium,
)
from services.backtesting.signals import (
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
    compute_theme_growth,
    compute_value_opportunity,
)


@dataclass(frozen=True)
class SignalContext:
    """All inputs a signal or modifier might need."""

    item_id: str
    eval_year: int
    eval_month: int
    item_sales: pd.DataFrame
    snapshots: pd.DataFrame | None
    theme: str | None = None
    year_released: int | None = None
    year_retired: int | None = None
    rrp_cents: int | None = None
    rrp_currency: str | None = None
    retiring_soon: bool = False


SignalFn = Callable[[SignalContext], float | None]
ModifierFn = Callable[[SignalContext], float]

SIGNAL_REGISTRY: dict[str, SignalFn] = {
    "demand_pressure": lambda ctx: compute_demand_pressure(
        ctx.item_sales, ctx.eval_year, ctx.eval_month,
    ),
    "supply_velocity": lambda ctx: compute_supply_velocity(
        ctx.snapshots, ctx.item_id, ctx.eval_year, ctx.eval_month,
    ),
    "price_trend": lambda ctx: compute_price_trend(
        ctx.item_sales, ctx.eval_year, ctx.eval_month,
    ),
    "price_vs_rrp": lambda ctx: compute_price_vs_rrp(
        ctx.item_sales, ctx.eval_year, ctx.eval_month,
        ctx.rrp_cents, ctx.rrp_currency,
    ),
    "lifecycle_position": lambda ctx: compute_lifecycle_position(
        ctx.year_released, ctx.year_retired, ctx.eval_year, ctx.retiring_soon,
    ),
    "stock_level": lambda ctx: compute_stock_level(
        ctx.snapshots, ctx.item_id, ctx.eval_year, ctx.eval_month,
    ),
    "collector_premium": lambda ctx: compute_collector_premium(
        ctx.item_sales, ctx.eval_year, ctx.eval_month,
    ),
    "theme_growth": lambda ctx: compute_theme_growth(ctx.theme),
    "value_opportunity": lambda ctx: compute_value_opportunity(
        ctx.item_sales, ctx.eval_year, ctx.eval_month,
    ),
    "price_wall": lambda ctx: compute_price_wall(
        ctx.snapshots, ctx.item_id, ctx.eval_year, ctx.eval_month,
    ),
    "listing_ratio": lambda ctx: compute_listing_ratio(
        ctx.snapshots, ctx.item_id, ctx.item_sales,
        ctx.eval_year, ctx.eval_month,
    ),
    "new_used_spread": lambda ctx: compute_new_used_spread(
        ctx.snapshots, ctx.item_id, ctx.eval_year, ctx.eval_month,
    ),
}

MODIFIER_REGISTRY: dict[str, ModifierFn] = {
    "mod_shelf_life": lambda ctx: compute_shelf_life(
        ctx.year_released, ctx.year_retired,
    ),
    "mod_subtheme": lambda ctx: compute_subtheme_premium(ctx.theme),
    "mod_niche": lambda ctx: compute_niche_penalty(ctx.theme),
}


def compute_signals(ctx: SignalContext) -> dict[str, float | None]:
    """Compute all registered signals for the given context."""
    return {name: fn(ctx) for name, fn in SIGNAL_REGISTRY.items()}


def compute_modifiers(ctx: SignalContext) -> dict[str, float]:
    """Compute all registered modifiers for the given context."""
    return {name: fn(ctx) for name, fn in MODIFIER_REGISTRY.items()}
