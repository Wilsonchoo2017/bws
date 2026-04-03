"""Keepa full price timeline feature extractor.

Extracts time-series features from Keepa's amazon_price_json, buy_box_json,
and sales_rank_json -- capturing discount dynamics, price momentum,
volatility, stock-out patterns, and demand signals across the full
Amazon pricing history.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from services.ml.helpers import safe_float
from services.ml.types import FeatureMeta

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


class KeepaTimelineExtractor:
    """Extracts time-series features from Keepa price history JSON."""

    @property
    def name(self) -> str:
        return "keepa_timeline"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            # Discount dynamics
            FeatureMeta("kpt_below_rrp_pct", "keepa_snapshots", "% of time Amazon price < 98% RRP"),
            FeatureMeta("kpt_avg_discount", "keepa_snapshots", "Avg Amazon discount from RRP %"),
            FeatureMeta("kpt_max_discount", "keepa_snapshots", "Max Amazon discount from RRP %"),
            FeatureMeta("kpt_median_discount", "keepa_snapshots", "Median Amazon discount from RRP %"),
            # Price dynamics
            FeatureMeta("kpt_price_cv", "keepa_snapshots", "Amazon price coefficient of variation"),
            FeatureMeta("kpt_price_trend", "keepa_snapshots", "Early vs late price trend %"),
            FeatureMeta("kpt_price_momentum", "keepa_snapshots", "Last-quarter vs first-quarter price ratio"),
            FeatureMeta("kpt_price_acceleration", "keepa_snapshots", "Trend change: 2nd half trend minus 1st half"),
            # Stock-out signals
            FeatureMeta("kpt_months_in_stock", "keepa_snapshots", "Months Amazon listing was in stock"),
            FeatureMeta("kpt_stockout_count", "keepa_snapshots", "Number of stock-out events"),
            FeatureMeta("kpt_stockout_pct", "keepa_snapshots", "% of timeline with stock-outs"),
            # Buy box premium
            FeatureMeta("kpt_bb_premium_pct", "keepa_snapshots", "Buy box premium after stock-out %"),
            FeatureMeta("kpt_bb_max_premium", "keepa_snapshots", "Max buy box premium vs RRP %"),
            # 3rd party signals
            FeatureMeta("kpt_3p_premium_pct", "keepa_snapshots", "3P FBA avg premium vs Amazon price %"),
            FeatureMeta("kpt_3p_price_cv", "keepa_snapshots", "3P FBA price coefficient of variation"),
            # Demand proxy
            FeatureMeta("kpt_rank_median", "keepa_snapshots", "Median sales rank (lower = more popular)"),
            FeatureMeta("kpt_rank_trend", "keepa_snapshots", "Sales rank trend (negative = improving)"),
            FeatureMeta("kpt_rank_cv", "keepa_snapshots", "Sales rank coefficient of variation"),
            # Timeline extent
            FeatureMeta("kpt_data_months", "keepa_snapshots", "Months of Keepa price data available"),
            FeatureMeta("kpt_n_price_points", "keepa_snapshots", "Number of price data points"),
        )

    def extract(
        self,
        conn: DuckDBPyConnection,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Load full Keepa timelines and extract time-series features."""
        keepa_df = _load_keepa_full_timelines(conn)
        if keepa_df.empty:
            return pd.DataFrame(columns=["set_number"])

        rrp_map = _load_rrp_map(conn)
        return _compute_timeline_features(keepa_df, rrp_map, base)


def _load_keepa_full_timelines(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load all Keepa JSON timeline columns."""
    return conn.execute("""
        SELECT
            ks.set_number,
            ks.amazon_price_json,
            ks.buy_box_json,
            ks.new_3p_fba_json,
            ks.sales_rank_json,
            ks.tracking_users
        FROM keepa_snapshots ks
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM keepa_snapshots
            GROUP BY set_number
        ) l ON ks.set_number = l.set_number AND ks.scraped_at = l.latest
        WHERE ks.amazon_price_json IS NOT NULL
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


def _parse_json_timeline(raw: object) -> list[list]:
    """Parse a JSON timeline column into a list of [date, value] points."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _extract_prices(timeline: list[list]) -> list[float]:
    """Extract non-null positive prices from a timeline."""
    return [float(p[1]) for p in timeline if len(p) >= 2 and p[1] is not None and p[1] > 0]


def _compute_timeline_features(
    keepa_df: pd.DataFrame,
    rrp_map: dict[str, float],
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Pure computation of timeline features from Keepa JSON data."""
    # Build cutoff lookup for retired sets
    cutoff_lookup: dict[str, str | None] = {}
    for _, row in base.iterrows():
        sn = row["set_number"]
        cy = row.get("cutoff_year")
        cm = row.get("cutoff_month")
        if cy is not None and cm is not None:
            cutoff_lookup[sn] = f"{int(cy):04d}-{int(cm):02d}"
        else:
            cutoff_lookup[sn] = None

    rows: list[dict] = []
    for _, kr in keepa_df.iterrows():
        sn = kr["set_number"]
        rrp = rrp_map.get(sn)
        if not rrp or rrp <= 0:
            continue

        rec: dict[str, object] = {"set_number": sn}
        cutoff = cutoff_lookup.get(sn)

        # --- Amazon price timeline ---
        amz_timeline = _parse_json_timeline(kr.get("amazon_price_json"))
        if cutoff:
            amz_timeline = [p for p in amz_timeline if len(p) >= 2 and (not isinstance(p[0], str) or p[0] <= cutoff)]

        amz_prices = _extract_prices(amz_timeline)

        if len(amz_prices) >= 3:
            mean_p = float(np.mean(amz_prices))
            rec["kpt_price_cv"] = float(np.std(amz_prices) / mean_p) if mean_p > 0 else None
            rec["kpt_below_rrp_pct"] = sum(1 for p in amz_prices if p < rrp * 0.98) / len(amz_prices) * 100
            rec["kpt_avg_discount"] = (rrp - mean_p) / rrp * 100
            rec["kpt_max_discount"] = (rrp - min(amz_prices)) / rrp * 100
            rec["kpt_median_discount"] = (rrp - float(np.median(amz_prices))) / rrp * 100
            rec["kpt_n_price_points"] = float(len(amz_prices))

            # Trend: early vs late
            if len(amz_prices) >= 6:
                q = len(amz_prices) // 4
                early = float(np.mean(amz_prices[:q])) if q > 0 else float(amz_prices[0])
                late = float(np.mean(amz_prices[-q:])) if q > 0 else float(amz_prices[-1])
                rec["kpt_price_trend"] = (late - early) / early * 100 if early > 0 else None

                # Momentum: last quarter vs first quarter
                rec["kpt_price_momentum"] = late / early if early > 0 else None

                # Acceleration: trend change between halves
                mid = len(amz_prices) // 2
                first_half = amz_prices[:mid]
                second_half = amz_prices[mid:]
                if len(first_half) >= 4 and len(second_half) >= 4:
                    fh_q = len(first_half) // 2
                    sh_q = len(second_half) // 2
                    fh_trend = (float(np.mean(first_half[fh_q:])) - float(np.mean(first_half[:fh_q])))
                    sh_trend = (float(np.mean(second_half[sh_q:])) - float(np.mean(second_half[:sh_q])))
                    rec["kpt_price_acceleration"] = (sh_trend - fh_trend) / rrp * 100

            # Stock-out analysis
            stockout_count = 0
            in_stockout = False
            in_stock_points = 0
            total_points = 0
            for point in amz_timeline:
                if len(point) < 2:
                    continue
                total_points += 1
                if point[1] is not None and point[1] > 0:
                    in_stock_points += 1
                    in_stockout = False
                elif not in_stockout:
                    stockout_count += 1
                    in_stockout = True

            rec["kpt_stockout_count"] = float(stockout_count)
            if total_points > 0:
                rec["kpt_stockout_pct"] = (1.0 - in_stock_points / total_points) * 100

            # Data extent in months
            date_strs = [p[0] for p in amz_timeline if len(p) >= 2 and isinstance(p[0], str)]
            if len(date_strs) >= 2:
                try:
                    d_first = pd.to_datetime(date_strs[0])
                    d_last = pd.to_datetime(date_strs[-1])
                    rec["kpt_data_months"] = max(1.0, (d_last - d_first).days / 30.0)
                    rec["kpt_months_in_stock"] = rec["kpt_data_months"] * (in_stock_points / total_points) if total_points > 0 else None
                except (ValueError, TypeError):
                    pass

        # --- Buy box timeline ---
        bb_timeline = _parse_json_timeline(kr.get("buy_box_json"))
        if cutoff:
            bb_timeline = [p for p in bb_timeline if len(p) >= 2 and (not isinstance(p[0], str) or p[0] <= cutoff)]

        bb_prices = _extract_prices(bb_timeline)
        if bb_prices and rrp > 0:
            max_bb = max(bb_prices)
            rec["kpt_bb_max_premium"] = (max_bb - rrp) / rrp * 100

            # Post-stockout buy box premium: find first BB price after last Amazon stockout
            if amz_timeline:
                last_oos_date = None
                for point in reversed(amz_timeline):
                    if len(point) >= 2 and (point[1] is None or point[1] <= 0):
                        last_oos_date = point[0]
                        break
                if last_oos_date and isinstance(last_oos_date, str):
                    post_oos_bb = [
                        float(p[1]) for p in bb_timeline
                        if len(p) >= 2 and isinstance(p[0], str) and p[0] >= last_oos_date
                        and p[1] is not None and p[1] > 0
                    ]
                    if post_oos_bb:
                        rec["kpt_bb_premium_pct"] = (float(np.mean(post_oos_bb)) - rrp) / rrp * 100

        # --- 3P FBA timeline ---
        fba_timeline = _parse_json_timeline(kr.get("new_3p_fba_json"))
        if cutoff:
            fba_timeline = [p for p in fba_timeline if len(p) >= 2 and (not isinstance(p[0], str) or p[0] <= cutoff)]

        fba_prices = _extract_prices(fba_timeline)
        if fba_prices and amz_prices:
            amz_mean = float(np.mean(amz_prices))
            fba_mean = float(np.mean(fba_prices))
            if amz_mean > 0:
                rec["kpt_3p_premium_pct"] = (fba_mean - amz_mean) / amz_mean * 100
            if fba_mean > 0:
                rec["kpt_3p_price_cv"] = float(np.std(fba_prices) / fba_mean)

        # --- Sales rank timeline ---
        rank_timeline = _parse_json_timeline(kr.get("sales_rank_json"))
        if cutoff:
            rank_timeline = [p for p in rank_timeline if len(p) >= 2 and (not isinstance(p[0], str) or p[0] <= cutoff)]

        rank_values = _extract_prices(rank_timeline)  # same extraction logic works
        if len(rank_values) >= 3:
            rec["kpt_rank_median"] = float(np.median(rank_values))
            rank_mean = float(np.mean(rank_values))
            if rank_mean > 0:
                rec["kpt_rank_cv"] = float(np.std(rank_values) / rank_mean)
            if len(rank_values) >= 6:
                q = len(rank_values) // 4
                early_rank = float(np.mean(rank_values[:q])) if q > 0 else float(rank_values[0])
                late_rank = float(np.mean(rank_values[-q:])) if q > 0 else float(rank_values[-1])
                if early_rank > 0:
                    rec["kpt_rank_trend"] = (late_rank - early_rank) / early_rank * 100

        rows.append(rec)

    if not rows:
        return pd.DataFrame(columns=["set_number"])

    return pd.DataFrame(rows)
