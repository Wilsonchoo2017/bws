"""Google Trends theme-level feature extractor.

Extracts theme-level demand signals from google_trends_theme_snapshots,
capturing brand strength, LEGO market share within themes, and theme
momentum -- signals that individual set-level trends miss.
"""

from __future__ import annotations

import logging

import pandas as pd

from services.ml.helpers import safe_float
from services.ml.types import FeatureMeta
from typing import Any


logger = logging.getLogger(__name__)


class GoogleTrendsThemeExtractor:
    """Extracts theme-level Google Trends features."""

    @property
    def name(self) -> str:
        return "gtrends_theme"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("gt_theme_lego_share", "google_trends_theme_snapshots", "LEGO share of theme search interest"),
            FeatureMeta("gt_theme_avg_lego", "google_trends_theme_snapshots", "Avg LEGO search interest for theme"),
            FeatureMeta("gt_theme_peak_lego", "google_trends_theme_snapshots", "Peak LEGO search interest for theme"),
            FeatureMeta("gt_theme_avg_bare", "google_trends_theme_snapshots", "Avg bare keyword search interest"),
            FeatureMeta("gt_theme_lego_vs_bare", "google_trends_theme_snapshots", "LEGO interest / bare interest ratio"),
        )

    def extract(
        self,
        conn: Any,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Load theme-level trends and join to sets via theme column."""
        theme_df = _load_theme_trends(conn)
        if theme_df.empty:
            return pd.DataFrame(columns=["set_number"])

        return _compute_theme_features(theme_df, base)


def _load_theme_trends(conn: Any) -> pd.DataFrame:
    """Load latest Google Trends theme snapshot per theme."""
    return conn.execute("""
        SELECT
            gt.theme,
            gt.lego_share,
            gt.avg_lego,
            gt.peak_lego,
            gt.avg_bare,
            gt.peak_bare
        FROM google_trends_theme_snapshots gt
        INNER JOIN (
            SELECT theme, MAX(scraped_at) AS latest
            FROM google_trends_theme_snapshots
            GROUP BY theme
        ) l ON gt.theme = l.theme AND gt.scraped_at = l.latest
    """).df()


def _compute_theme_features(
    theme_df: pd.DataFrame,
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Join theme-level trends to sets and compute derived features."""
    # Build theme -> metrics lookup
    theme_metrics: dict[str, dict] = {}
    for _, row in theme_df.iterrows():
        theme = row["theme"]
        if not theme:
            continue
        avg_lego = safe_float(row.get("avg_lego"))
        avg_bare = safe_float(row.get("avg_bare"))

        lego_vs_bare = None
        if avg_lego and avg_bare and avg_bare > 0:
            lego_vs_bare = avg_lego / avg_bare

        theme_metrics[theme] = {
            "gt_theme_lego_share": safe_float(row.get("lego_share")),
            "gt_theme_avg_lego": avg_lego,
            "gt_theme_peak_lego": safe_float(row.get("peak_lego")),
            "gt_theme_avg_bare": avg_bare,
            "gt_theme_lego_vs_bare": lego_vs_bare,
        }

    rows: list[dict] = []
    for _, item in base.iterrows():
        sn = item["set_number"]
        theme = item.get("theme") or ""
        rec: dict[str, object] = {"set_number": sn}

        metrics = theme_metrics.get(theme, {})
        rec.update(metrics)
        rows.append(rec)

    if not rows:
        return pd.DataFrame(columns=["set_number"])

    return pd.DataFrame(rows)
