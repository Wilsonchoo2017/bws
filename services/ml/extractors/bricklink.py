"""BrickLink monthly sales feature extractor.

Extracts pre-retirement price momentum, transaction velocity, and
liquidity features from BrickLink monthly sales data. These capture
how a set was trading before retirement -- a strong signal for
post-retirement appreciation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from services.ml.helpers import offset_months, safe_float, set_number_to_item_id
from services.ml.types import FeatureMeta

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


class BrickLinkExtractor:
    """Extracts features from BrickLink monthly sales history."""

    @property
    def name(self) -> str:
        return "bricklink"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            # Price momentum
            FeatureMeta("bl_price_trend_pct", "bricklink_monthly_sales", "Price trend % over available history"),
            FeatureMeta("bl_price_momentum_3m", "bricklink_monthly_sales", "3-month price momentum %"),
            FeatureMeta("bl_price_momentum_6m", "bricklink_monthly_sales", "6-month price momentum %"),
            FeatureMeta("bl_price_vs_rrp", "bricklink_monthly_sales", "Latest BL price / RRP ratio"),
            # Price volatility
            FeatureMeta("bl_price_cv", "bricklink_monthly_sales", "Price coefficient of variation"),
            FeatureMeta("bl_price_range_pct", "bricklink_monthly_sales", "(Max - Min) / Mean price %"),
            # Transaction volume
            FeatureMeta("bl_avg_monthly_sales", "bricklink_monthly_sales", "Avg monthly units sold"),
            FeatureMeta("bl_sales_trend", "bricklink_monthly_sales", "Sales volume trend: late vs early ratio"),
            FeatureMeta("bl_total_quantity", "bricklink_monthly_sales", "Total units sold across history"),
            # Liquidity
            FeatureMeta("bl_months_with_sales", "bricklink_monthly_sales", "Months with at least 1 sale"),
            FeatureMeta("bl_sales_consistency", "bricklink_monthly_sales", "% of months with sales"),
            # Spread
            FeatureMeta("bl_avg_spread_pct", "bricklink_monthly_sales", "Avg (max-min)/avg price spread %"),
        )

    def extract(
        self,
        conn: DuckDBPyConnection,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Load BrickLink monthly sales and extract features."""
        bl_df = _load_bricklink_data(conn)
        if bl_df.empty:
            return pd.DataFrame(columns=["set_number"])

        rrp_map = _load_rrp_map(conn)
        return _compute_bricklink_features(bl_df, rrp_map, base)


def _load_bricklink_data(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load BrickLink monthly sales (new condition)."""
    return conn.execute("""
        SELECT
            item_id, year, month,
            times_sold, total_quantity,
            min_price, max_price, avg_price
        FROM bricklink_monthly_sales
        WHERE condition = 'N'
          AND avg_price IS NOT NULL AND avg_price > 0
        ORDER BY item_id, year, month
    """).df()


def _load_rrp_map(conn: DuckDBPyConnection) -> dict[str, float]:
    """Load latest RRP USD cents per set."""
    df = conn.execute("""
        SELECT set_number, rrp_usd_cents
        FROM (
            SELECT set_number, rrp_usd_cents,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents IS NOT NULL
        ) WHERE rn = 1
    """).df()
    if df.empty:
        return {}
    return dict(zip(df["set_number"], df["rrp_usd_cents"]))


def _compute_bricklink_features(
    bl_df: pd.DataFrame,
    rrp_map: dict[str, float],
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Pure computation of BrickLink features."""
    # Build item_id -> set_number mapping and cutoff lookup
    sn_to_item: dict[str, str] = {}
    cutoff_lookup: dict[str, tuple[int, int] | None] = {}
    for _, row in base.iterrows():
        sn = row["set_number"]
        sn_to_item[sn] = set_number_to_item_id(sn)
        cy = row.get("cutoff_year")
        cm = row.get("cutoff_month")
        if cy is not None and cm is not None:
            cutoff_lookup[sn] = (int(cy), int(cm))
        else:
            cutoff_lookup[sn] = None

    item_to_sn = {v: k for k, v in sn_to_item.items()}

    rows: list[dict] = []
    for item_id, group in bl_df.groupby("item_id"):
        sn = item_to_sn.get(str(item_id))
        if sn is None:
            continue

        cutoff = cutoff_lookup.get(sn)

        # Sort by date and filter to before cutoff
        sorted_group = group.sort_values(["year", "month"])
        if cutoff:
            cy, cm = cutoff
            sorted_group = sorted_group[
                (sorted_group["year"] < cy) |
                ((sorted_group["year"] == cy) & (sorted_group["month"] <= cm))
            ]

        if sorted_group.empty:
            continue

        prices = sorted_group["avg_price"].values.astype(float)
        quantities = sorted_group["total_quantity"].fillna(0).values.astype(float)
        times_sold = sorted_group["times_sold"].fillna(0).values.astype(float)
        min_prices = sorted_group["min_price"].fillna(0).values.astype(float)
        max_prices = sorted_group["max_price"].fillna(0).values.astype(float)

        rec: dict[str, object] = {"set_number": sn}
        rrp = rrp_map.get(sn)
        n = len(prices)

        if n < 2:
            rows.append(rec)
            continue

        mean_p = float(np.mean(prices))

        # Price trend over full history
        if prices[0] > 0:
            rec["bl_price_trend_pct"] = (prices[-1] - prices[0]) / prices[0] * 100

        # Short-term momentum
        if n >= 3:
            recent_avg = float(np.mean(prices[-3:]))
            earlier_avg = float(np.mean(prices[:-3])) if n > 3 else float(prices[0])
            if earlier_avg > 0:
                rec["bl_price_momentum_3m"] = (recent_avg - earlier_avg) / earlier_avg * 100

        if n >= 6:
            recent_6 = float(np.mean(prices[-6:]))
            earlier_6 = float(np.mean(prices[:-6])) if n > 6 else float(prices[0])
            if earlier_6 > 0:
                rec["bl_price_momentum_6m"] = (recent_6 - earlier_6) / earlier_6 * 100

        # Price vs RRP
        if rrp and rrp > 0:
            rec["bl_price_vs_rrp"] = prices[-1] / rrp

        # Price volatility
        if mean_p > 0:
            rec["bl_price_cv"] = float(np.std(prices) / mean_p)
            p_range = float(np.max(prices) - np.min(prices))
            rec["bl_price_range_pct"] = p_range / mean_p * 100

        # Transaction volume
        rec["bl_avg_monthly_sales"] = float(np.mean(times_sold))
        rec["bl_total_quantity"] = float(np.sum(quantities))

        # Sales trend
        if n >= 4:
            q = max(1, n // 4)
            early_sales = float(np.mean(times_sold[:q]))
            late_sales = float(np.mean(times_sold[-q:]))
            if early_sales > 0:
                rec["bl_sales_trend"] = late_sales / early_sales

        # Liquidity
        months_with_sales = int(np.sum(times_sold > 0))
        rec["bl_months_with_sales"] = float(months_with_sales)
        rec["bl_sales_consistency"] = months_with_sales / n * 100

        # Average spread
        spreads: list[float] = []
        for mp, xp, ap in zip(min_prices, max_prices, prices):
            if ap > 0 and xp > mp:
                spreads.append((xp - mp) / ap * 100)
        if spreads:
            rec["bl_avg_spread_pct"] = float(np.mean(spreads))

        rows.append(rec)

    if not rows:
        return pd.DataFrame(columns=["set_number"])

    return pd.DataFrame(rows)
