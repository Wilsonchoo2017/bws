"""Keepa / Amazon feature extractor.

Extracts Amazon discount, price range, rating, review count,
and tracking user features from Keepa snapshots.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from services.ml.helpers import safe_float
from services.ml.queries import load_latest_keepa_snapshots, load_rrp_map
from services.ml.types import FeatureMeta

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


class KeepaExtractor:
    """Extracts features from Keepa snapshots."""

    @property
    def name(self) -> str:
        return "keepa"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("amazon_discount_pct", "derived", "Amazon price vs RRP discount %"),
            FeatureMeta("keepa_price_range_pct", "derived", "Keepa (highest-lowest)/RRP %"),
            FeatureMeta("keepa_rating", "keepa_snapshots", "Amazon rating"),
            FeatureMeta("keepa_review_count", "keepa_snapshots", "Amazon review count", "int"),
            FeatureMeta("keepa_tracking_users", "keepa_snapshots", "Keepa tracking user count", "int"),
        )

    def extract(
        self,
        conn: DuckDBPyConnection,
        base: pd.DataFrame,  # noqa: ARG002
    ) -> pd.DataFrame:
        """Load Keepa snapshots and RRP map, then extract features."""
        keepa_df = load_latest_keepa_snapshots(conn)
        rrp_map = load_rrp_map(conn)
        return _compute_keepa_features(keepa_df, rrp_map)


def _compute_keepa_features(
    keepa_df: pd.DataFrame,
    rrp_map: dict[str, float],
) -> pd.DataFrame:
    """Pure computation of Keepa features from pre-loaded data."""
    if keepa_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in keepa_df.iterrows():
        sn = row["set_number"]
        rrp_usd = rrp_map.get(sn)
        amazon_price = safe_float(row.get("current_amazon_cents"))
        lowest = safe_float(row.get("lowest_ever_cents"))
        highest = safe_float(row.get("highest_ever_cents"))

        discount_pct = None
        if rrp_usd and rrp_usd > 0 and amazon_price:
            discount_pct = (float(rrp_usd) - amazon_price) / float(rrp_usd) * 100

        price_range_pct = None
        if rrp_usd and rrp_usd > 0 and lowest and highest:
            price_range_pct = (highest - lowest) / float(rrp_usd) * 100

        rows.append({
            "set_number": sn,
            "amazon_discount_pct": discount_pct,
            "keepa_price_range_pct": price_range_pct,
            "keepa_rating": safe_float(row.get("rating")),
            "keepa_review_count": safe_float(row.get("review_count")),
            "keepa_tracking_users": safe_float(row.get("tracking_users")),
        })

    return pd.DataFrame(rows)
