"""Google Trends feature extractor.

Extracts peak and average search interest values.
"""

from __future__ import annotations


import pandas as pd

from services.ml.helpers import safe_float
from services.ml.queries import load_latest_gtrends_snapshots
from services.ml.types import FeatureMeta
from typing import Any


class GoogleTrendsExtractor:
    """Extracts features from Google Trends snapshots."""

    @property
    def name(self) -> str:
        return "gtrends"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("gtrends_peak", "google_trends_snapshots", "Peak search interest value"),
            FeatureMeta("gtrends_avg", "google_trends_snapshots", "Average search interest value"),
        )

    def extract(
        self,
        conn: Any,
        base: pd.DataFrame,  # noqa: ARG002
    ) -> pd.DataFrame:
        """Load and extract Google Trends features."""
        gt_df = load_latest_gtrends_snapshots(conn)
        return _compute_gtrends_features(gt_df)


def _compute_gtrends_features(gt_df: pd.DataFrame) -> pd.DataFrame:
    """Pure computation of Google Trends features from pre-loaded data."""
    if gt_df.empty:
        return pd.DataFrame(columns=["set_number"])

    rows: list[dict] = []
    for _, row in gt_df.iterrows():
        rows.append({
            "set_number": row["set_number"],
            "gtrends_peak": safe_float(row.get("peak_value")),
            "gtrends_avg": safe_float(row.get("average_value")),
        })

    return pd.DataFrame(rows)
