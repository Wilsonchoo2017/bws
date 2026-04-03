"""Set intrinsics feature extractor.

Extracts features from core set metadata (parts_count, minifig_count,
shelf_life, licensed theme, piece bucket).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from config.ml import LICENSED_THEMES
from services.backtesting.cohort import PIECE_GROUPS
from services.ml.helpers import ordinal_bucket
from services.ml.types import FeatureMeta

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


class IntrinsicsExtractor:
    """Extracts features derived from core set metadata."""

    @property
    def name(self) -> str:
        return "intrinsics"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("parts_count", "lego_items", "Number of pieces in set", "int"),
            FeatureMeta("minifig_count", "lego_items", "Number of minifigures", "int"),
            FeatureMeta("shelf_life_years", "derived", "Years in production before retirement"),
            FeatureMeta("is_licensed", "derived", "Theme is a licensed IP", "int"),
            FeatureMeta("pieces_bucket_ordinal", "derived", "Piece count bucket (0-4)"),
        )

    def extract(
        self,
        conn: DuckDBPyConnection,  # noqa: ARG002
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Extract intrinsic features from base metadata (pure -- no DB access)."""
        rows: list[dict] = []
        for _, item in base.iterrows():
            parts = item.get("parts_count")
            minifigs = item.get("minifig_count")
            theme = item.get("theme") or ""
            yr_released = item.get("year_released")
            yr_retired = item.get("year_retired")

            shelf_life = None
            if pd.notna(yr_released) and pd.notna(yr_retired):
                shelf_life = float(yr_retired - yr_released)

            is_licensed = 1 if theme in LICENSED_THEMES else 0
            pieces_ord = ordinal_bucket(parts, PIECE_GROUPS) if pd.notna(parts) and parts else None

            rows.append({
                "set_number": item["set_number"],
                "parts_count": float(parts) if pd.notna(parts) else None,
                "minifig_count": float(minifigs) if pd.notna(minifigs) else None,
                "shelf_life_years": shelf_life,
                "is_licensed": float(is_licensed),
                "pieces_bucket_ordinal": float(pieces_ord) if pieces_ord is not None else None,
            })

        return pd.DataFrame(rows)
