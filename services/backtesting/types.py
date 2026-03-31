"""Data models for the backtesting framework.

All models are frozen dataclasses for immutability.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for a backtest run."""

    flip_horizons: tuple[int, ...] = (1, 2)
    hold_horizons: tuple[int, ...] = (12, 24, 36)
    min_history_months: int = 6
    condition: str = "new"


SIGNAL_NAMES: tuple[str, ...] = (
    "demand_pressure",
    "supply_velocity",
    "price_trend",
    "price_vs_rrp",
    "lifecycle_position",
    "stock_level",
    "collector_premium",
    "theme_growth",
    "value_opportunity",
    "price_wall",
    "listing_ratio",
    "new_used_spread",
)

# Dropped signals (insufficient data coverage or no statistical significance):
# - minifig_appeal: 39% coverage, p=0.32, importance=0.004
# - volume_price_confirm: 29% coverage, p=0.57, importance=0.001

MODIFIER_NAMES: tuple[str, ...] = (
    "mod_shelf_life",
    "mod_subtheme",
    "mod_niche",
)


@dataclass(frozen=True)
class SignalSnapshot:
    """All 14 signals + 3 modifiers computed at a point in time."""

    item_id: str
    year: int
    month: int
    # 12 signals (0-100 each, None if insufficient data)
    demand_pressure: float | None = None
    supply_velocity: float | None = None
    price_trend: float | None = None
    price_vs_rrp: float | None = None
    lifecycle_position: float | None = None
    stock_level: float | None = None
    collector_premium: float | None = None
    theme_growth: float | None = None
    value_opportunity: float | None = None
    price_wall: float | None = None
    listing_ratio: float | None = None
    new_used_spread: float | None = None
    # 3 modifiers (multipliers, default 1.0)
    mod_shelf_life: float = 1.0
    mod_subtheme: float = 1.0
    mod_niche: float = 1.0


@dataclass(frozen=True)
class TradeResult:
    """Result of a simulated trade at a point in time."""

    item_id: str
    entry_year: int
    entry_month: int
    entry_price_cents: int
    signals: SignalSnapshot
    returns: dict[str, float | None] = field(default_factory=dict)
