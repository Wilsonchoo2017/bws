"""Shopee saturation feature extractor.

Extracts marketplace saturation metrics: listings count, unique sellers,
price spread, and saturation score.
"""

from __future__ import annotations


import pandas as pd

from services.ml.helpers import safe_float
from services.ml.queries import load_latest_shopee_snapshots
from services.ml.types import FeatureMeta
from typing import Any


class ShopeeExtractor:
    """Extracts features from Shopee saturation data."""

    @property
    def name(self) -> str:
        return "shopee"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("shopee_listings", "shopee_saturation", "Number of Shopee listings", "int"),
            FeatureMeta("shopee_unique_sellers", "shopee_saturation", "Unique Shopee sellers", "int"),
            FeatureMeta("shopee_price_spread_pct", "shopee_saturation", "Shopee price spread %"),
            FeatureMeta("shopee_saturation_score", "shopee_saturation", "Shopee saturation score"),
        )

    def extract(
        self,
        conn: Any,
        base: pd.DataFrame,  # noqa: ARG002
    ) -> pd.DataFrame:
        """Load and extract Shopee saturation features."""
        ss_df = load_latest_shopee_snapshots(conn)
        return _compute_shopee_features(ss_df)


def _compute_shopee_features(ss_df: pd.DataFrame) -> pd.DataFrame:
    """Pure computation of Shopee features from pre-loaded data."""
    if ss_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in ss_df.iterrows():
        rows.append({
            "set_number": row["set_number"],
            "shopee_listings": safe_float(row.get("listings_count")),
            "shopee_unique_sellers": safe_float(row.get("unique_sellers")),
            "shopee_price_spread_pct": safe_float(row.get("price_spread_pct")),
            "shopee_saturation_score": safe_float(row.get("saturation_score")),
        })

    return pd.DataFrame(rows)
