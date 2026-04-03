"""BrickEconomy value chart price source.

Resolves prices from BrickEconomy value_chart_json time series data.
Falls back to nearest point within 3 months if exact months not found.
"""

from __future__ import annotations

from services.ml.helpers import offset_months


class BrickEconomyChartSource:
    """Price source backed by BrickEconomy value chart time series."""

    def __init__(self, charts: dict[str, list[tuple[int, int, int]]]) -> None:
        self._charts = charts

    @property
    def name(self) -> str:
        return "brickeconomy_chart"

    def get_price(
        self,
        identifier: str,
        target_year: int,
        target_month: int,
        half_window: int,
    ) -> int | None:
        """Get price from value chart near target month.

        Args:
            identifier: Set number (e.g. '75192').
        """
        points = self._charts.get(identifier)
        if not points:
            return None

        # Collect prices within the smoothing window
        prices: list[int] = []
        for offset in range(-half_window, half_window + 1):
            y, m = offset_months(target_year, target_month, offset)
            for py, pm, price in points:
                if py == y and pm == m:
                    prices.append(price)
                    break

        if prices:
            return int(sum(prices) / len(prices))

        # Fallback: find nearest point within 3 months
        target_abs = target_year * 12 + target_month
        nearest_price = None
        nearest_dist = 999
        for py, pm, price in points:
            dist = abs((py * 12 + pm) - target_abs)
            if dist < nearest_dist and dist <= 3:
                nearest_dist = dist
                nearest_price = price

        return nearest_price
