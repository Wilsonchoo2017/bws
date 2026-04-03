"""BrickEconomy snapshot price source.

Resolves prices from BrickEconomy value_new_cents snapshot data.
This is the last-resort fallback, finding the nearest snapshot
within 90 days of the target date.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


class BrickEconomySnapshotSource:
    """Price source backed by BrickEconomy snapshot values."""

    def __init__(self, snapshots_df: pd.DataFrame) -> None:
        self._df = snapshots_df

    @property
    def name(self) -> str:
        return "brickeconomy_snapshot"

    def get_price(
        self,
        identifier: str,
        target_year: int,
        target_month: int,
        half_window: int,  # noqa: ARG002
    ) -> int | None:
        """Get value_new_cents from nearest snapshot within 90 days.

        Args:
            identifier: Set number (e.g. '75192').
        """
        item_df = self._df[self._df["set_number"] == identifier]
        if item_df.empty:
            return None

        target_date = datetime(target_year, target_month, 15)
        best_price = None
        best_dist = float("inf")

        for _, row in item_df.iterrows():
            scraped = row["scraped_at"]
            if scraped is None:
                continue
            if isinstance(scraped, str):
                try:
                    scraped = datetime.fromisoformat(scraped)
                except ValueError:
                    continue

            dist_days = abs((scraped - target_date).days)
            if dist_days < best_dist and dist_days <= 90:
                best_dist = dist_days
                best_price = int(row["value_new_cents"])

        return best_price
