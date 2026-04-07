"""Minifigure composition feature extractor.

Extracts features from set-minifigure mappings and BrickLink minifig
price history: exclusivity, total/hero figure value, sales volume.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from services.ml.helpers import safe_float
from services.ml.types import FeatureMeta
from typing import Any


logger = logging.getLogger(__name__)


class MinifigExtractor:
    """Extracts set-level features from minifigure composition and pricing."""

    @property
    def name(self) -> str:
        return "minifigs"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            FeatureMeta("mf_exclusive_count", "set_minifigures", "Number of exclusive (single-set) minifigs", "int"),
            FeatureMeta("mf_exclusive_pct", "derived", "% of minifigs that are exclusive to this set"),
            FeatureMeta("mf_total_value", "minifig_price_history", "Sum of avg minifig prices (MYR cents)"),
            FeatureMeta("mf_value_vs_rrp", "derived", "Total minifig value / set RRP ratio"),
            FeatureMeta("mf_hero_value", "minifig_price_history", "Most valuable minifig avg price (MYR cents)"),
            FeatureMeta("mf_hero_vs_rrp", "derived", "Hero minifig value / set RRP ratio"),
            FeatureMeta("mf_avg_value", "minifig_price_history", "Mean avg minifig price (MYR cents)"),
            FeatureMeta("mf_value_cv", "derived", "Coefficient of variation of minifig values"),
            FeatureMeta("mf_total_sales", "minifig_price_history", "Sum of 6-month sales across all minifigs", "int"),
            FeatureMeta("mf_avg_sales", "minifig_price_history", "Avg 6-month sales per minifig"),
            FeatureMeta("mf_liquidity_score", "derived", "Total minifig lots / total figs (market depth)"),
        )

    def extract(
        self,
        conn: Any,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Load minifig data and compute set-level features."""
        mappings = conn.execute(
            "SELECT set_item_id, minifig_id, quantity FROM set_minifigures"
        ).df()
        prices_raw = conn.execute(
            "SELECT minifig_id, six_month_new, current_new FROM minifig_price_history"
        ).df()

        if mappings.empty:
            return pd.DataFrame(columns=["set_number"])

        fig_prices = _parse_minifig_prices(prices_raw)
        fig_set_counts = mappings.groupby("minifig_id")["set_item_id"].nunique().to_dict()

        # RRP may come from base (if enriched) or from BE snapshots
        rrp_lookup: dict[str, float] = {}
        if "rrp_usd_cents" in base.columns:
            for _, row in base.iterrows():
                rrp = safe_float(row.get("rrp_usd_cents"))
                if pd.notna(rrp):
                    rrp_lookup[row["set_number"]] = float(rrp)
        if not rrp_lookup:
            rrp_df = conn.execute(
                "SELECT set_number, rrp_usd_cents FROM brickeconomy_snapshots WHERE rrp_usd_cents > 0"
            ).df()
            for _, row in rrp_df.iterrows():
                rrp_lookup[row["set_number"]] = float(row["rrp_usd_cents"])

        return _compute_minifig_features(
            base["set_number"].tolist(),
            mappings,
            fig_prices,
            fig_set_counts,
            rrp_lookup,
        )


def _parse_minifig_prices(
    prices_df: pd.DataFrame,
) -> dict[str, dict[str, float]]:
    """Parse JSON price columns into a simple lookup dict."""
    result: dict[str, dict[str, float]] = {}
    for _, row in prices_df.iterrows():
        mid = row["minifig_id"]
        for col in ("six_month_new", "current_new"):
            raw = row[col]
            if raw is None:
                continue
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                continue
            avg_p = (data.get("avg_price") or {}).get("amount")
            if not avg_p:
                continue
            result[mid] = {
                "avg_price": float(avg_p),
                "max_price": float((data.get("max_price") or {}).get("amount", 0) or 0),
                "times_sold": float(data.get("times_sold") or 0),
                "total_lots": float(data.get("total_lots") or 0),
            }
            break  # prefer six_month_new, fall back to current_new
    return result


def _compute_minifig_features(
    set_numbers: list[str],
    mappings: pd.DataFrame,
    fig_prices: dict[str, dict[str, float]],
    fig_set_counts: dict[str, int],
    rrp_lookup: dict[str, float],
) -> pd.DataFrame:
    """Pure computation of set-level minifig features."""
    rows: list[dict] = []
    for sn in set_numbers:
        set_item_id = f"{sn}-1"
        set_figs = mappings[mappings["set_item_id"] == set_item_id]
        if set_figs.empty:
            rows.append({"set_number": sn})
            continue

        n_figs = len(set_figs)
        exclusive_count = 0
        fig_vals: list[float] = []
        total_sales = 0.0
        total_lots = 0.0

        for _, fm in set_figs.iterrows():
            mid = fm["minifig_id"]
            if fig_set_counts.get(mid, 0) == 1:
                exclusive_count += 1
            fp = fig_prices.get(mid)
            if fp:
                fig_vals.append(fp["avg_price"])
                total_sales += fp["times_sold"]
                total_lots += fp["total_lots"]

        rrp = rrp_lookup.get(sn, 0)
        total_val = sum(fig_vals)
        hero_val = max(fig_vals) if fig_vals else 0
        avg_val = float(np.mean(fig_vals)) if fig_vals else 0

        rec: dict[str, object] = {
            "set_number": sn,
            "mf_exclusive_count": exclusive_count,
            "mf_exclusive_pct": exclusive_count / n_figs * 100 if n_figs > 0 else None,
            "mf_total_value": total_val if fig_vals else None,
            "mf_value_vs_rrp": total_val / rrp if rrp > 0 and fig_vals else None,
            "mf_hero_value": hero_val if fig_vals else None,
            "mf_hero_vs_rrp": hero_val / rrp if rrp > 0 and fig_vals else None,
            "mf_avg_value": avg_val if fig_vals else None,
            "mf_value_cv": float(np.std(fig_vals) / avg_val) if avg_val > 0 and len(fig_vals) > 1 else None,
            "mf_total_sales": total_sales if fig_vals else None,
            "mf_avg_sales": total_sales / len(fig_vals) if fig_vals else None,
            "mf_liquidity_score": total_lots / n_figs if n_figs > 0 and total_lots > 0 else None,
        }
        rows.append(rec)

    return pd.DataFrame(rows)
