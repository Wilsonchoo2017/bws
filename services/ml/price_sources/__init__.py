"""Price source chain of responsibility.

Each source resolves prices from a different data provider. Sources
are tried in priority order; the first to return a non-None price wins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.ml.price_sources.be_chart import BrickEconomyChartSource
from services.ml.price_sources.be_snapshot import BrickEconomySnapshotSource
from services.ml.price_sources.bricklink import BrickLinkSource

if TYPE_CHECKING:
    import pandas as pd

    from services.ml.protocols import PriceSource


def get_price_chain(
    bricklink_prices: pd.DataFrame,
    be_value_charts: dict[str, list[tuple[int, int, int]]],
    be_snapshots: pd.DataFrame,
) -> tuple[PriceSource, ...]:
    """Build the price source chain from pre-loaded data.

    Sources are returned in priority order:
    1. BrickLink monthly avg_price (most reliable)
    2. BrickEconomy value chart time series
    3. BrickEconomy snapshot values (fallback)
    """
    return (
        BrickLinkSource(bricklink_prices),
        BrickEconomyChartSource(be_value_charts),
        BrickEconomySnapshotSource(be_snapshots),
    )


def resolve_price(
    sources: tuple[PriceSource, ...],
    identifier: str,
    target_year: int,
    target_month: int,
    half_window: int,
) -> tuple[int | None, str]:
    """Try each source in order, returning the first non-None result.

    Args:
        sources: Ordered tuple of price sources.
        identifier: Set number or item ID.
        target_year: Target year.
        target_month: Target month.
        half_window: Smoothing window half-width in months.

    Returns:
        (price_cents, source_name) or (None, "none").
    """
    for source in sources:
        price = source.get_price(identifier, target_year, target_month, half_window)
        if price is not None:
            return price, source.name
    return None, "none"
