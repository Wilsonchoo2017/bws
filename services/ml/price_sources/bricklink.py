"""BrickLink monthly sales price source.

Resolves prices from BrickLink monthly avg_price data using a
smoothing window around the target month.
"""

from __future__ import annotations

import pandas as pd

from services.ml.helpers import offset_months


class BrickLinkSource:
    """Price source backed by BrickLink monthly sales data."""

    def __init__(self, prices_df: pd.DataFrame) -> None:
        self._df = prices_df

    @property
    def name(self) -> str:
        return "bricklink"

    def get_price(
        self,
        identifier: str,
        target_year: int,
        target_month: int,
        half_window: int,
    ) -> int | None:
        """Get avg BrickLink price in a window around target month.

        Args:
            identifier: BrickLink item_id (e.g. '75192-1').
        """
        item_df = self._df[self._df["item_id"] == identifier]
        if item_df.empty:
            return None

        prices: list[int] = []
        for offset in range(-half_window, half_window + 1):
            y, m = offset_months(target_year, target_month, offset)
            match = item_df[(item_df["year"] == y) & (item_df["month"] == m)]
            if not match.empty:
                p = match.iloc[0]["avg_price"]
                if p and p > 0:
                    prices.append(int(p))

        if prices:
            return int(sum(prices) / len(prices))
        return None
