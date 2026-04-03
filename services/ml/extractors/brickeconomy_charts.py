"""BrickEconomy chart and time-series feature extractor.

Extracts features from value_chart_json (price appreciation curve),
candlestick_json (OHLC volatility), and sales_trend_json (transaction
volume patterns) that the base BrickEconomy extractor does not cover.
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


class BrickEconomyChartsExtractor:
    """Extracts time-series features from BE chart JSON columns."""

    @property
    def name(self) -> str:
        return "brickeconomy_charts"

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        return (
            # Value chart features (price appreciation curve)
            FeatureMeta("be_value_months", "brickeconomy_snapshots", "Months of BE value history"),
            FeatureMeta("be_value_trend_pct", "brickeconomy_snapshots", "Overall value trend %"),
            FeatureMeta("be_value_momentum", "brickeconomy_snapshots", "Recent vs early value ratio"),
            FeatureMeta("be_value_cv", "brickeconomy_snapshots", "Value chart coefficient of variation"),
            FeatureMeta("be_value_max_drawdown", "brickeconomy_snapshots", "Max peak-to-trough drawdown %"),
            FeatureMeta("be_value_recovery", "brickeconomy_snapshots", "Recovery from max drawdown %"),
            # Candlestick features (OHLC volatility)
            FeatureMeta("be_candle_avg_range_pct", "brickeconomy_snapshots", "Avg candle range / close %"),
            FeatureMeta("be_candle_bearish_pct", "brickeconomy_snapshots", "% of bearish candles (close < open)"),
            FeatureMeta("be_candle_trend_strength", "brickeconomy_snapshots", "Avg body / range ratio (trend clarity)"),
            FeatureMeta("be_candle_upper_shadow_pct", "brickeconomy_snapshots", "Avg upper shadow relative to range %"),
            FeatureMeta("be_candle_volatility_trend", "brickeconomy_snapshots", "Late vs early candle range change"),
            # Sales trend features (transaction volume)
            FeatureMeta("be_sales_avg_volume", "brickeconomy_snapshots", "Avg monthly transaction volume"),
            FeatureMeta("be_sales_volume_trend", "brickeconomy_snapshots", "Volume trend: late vs early ratio"),
            FeatureMeta("be_sales_volume_cv", "brickeconomy_snapshots", "Volume coefficient of variation"),
            FeatureMeta("be_sales_months_active", "brickeconomy_snapshots", "Months with sales activity"),
            # Future estimate (BE's own prediction)
            FeatureMeta("be_future_est_return", "brickeconomy_snapshots", "BE future estimate vs current value ratio"),
        )

    def extract(
        self,
        conn: DuckDBPyConnection,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Load BE chart data and extract features."""
        charts_df = _load_be_charts(conn)
        if charts_df.empty:
            return pd.DataFrame(columns=["set_number"])

        # Build cutoff lookup
        cutoff_lookup: dict[str, str | None] = {}
        for _, row in base.iterrows():
            sn = row["set_number"]
            cy = row.get("cutoff_year")
            cm = row.get("cutoff_month")
            if pd.notna(cy) and pd.notna(cm):
                cutoff_lookup[sn] = f"{int(cy):04d}-{int(cm):02d}"
            else:
                cutoff_lookup[sn] = None

        return _compute_chart_features(charts_df, cutoff_lookup)


def _load_be_charts(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load BE chart JSON columns (latest snapshot per set)."""
    return conn.execute("""
        SELECT
            bs.set_number,
            bs.value_chart_json,
            bs.candlestick_json,
            bs.sales_trend_json,
            bs.value_new_cents,
            bs.future_estimate_cents,
            bs.rrp_usd_cents
        FROM brickeconomy_snapshots bs
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM brickeconomy_snapshots
            GROUP BY set_number
        ) l ON bs.set_number = l.set_number AND bs.scraped_at = l.latest
        WHERE bs.value_chart_json IS NOT NULL
           OR bs.candlestick_json IS NOT NULL
           OR bs.sales_trend_json IS NOT NULL
    """).df()


def _parse_json(raw: object) -> list | dict | None:
    """Safely parse a JSON column."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed
    except (json.JSONDecodeError, TypeError):
        return None


def _compute_chart_features(
    charts_df: pd.DataFrame,
    cutoff_lookup: dict[str, str | None],
) -> pd.DataFrame:
    """Pure computation of chart features."""
    rows: list[dict] = []

    for _, row in charts_df.iterrows():
        sn = row["set_number"]
        rec: dict[str, object] = {"set_number": sn}
        cutoff = cutoff_lookup.get(sn)
        rrp = safe_float(row.get("rrp_usd_cents"))

        # --- Value chart features ---
        value_chart = _parse_json(row.get("value_chart_json"))
        if isinstance(value_chart, list) and len(value_chart) >= 3:
            # Parse into (date_str, price) tuples
            points: list[tuple[str, float]] = []
            for entry in value_chart:
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                date_str = str(entry[0])
                price = entry[1]
                if price is None or not isinstance(price, (int, float)) or price <= 0:
                    continue
                if cutoff and date_str > cutoff:
                    continue
                points.append((date_str, float(price)))

            if len(points) >= 3:
                prices = [p[1] for p in points]
                rec["be_value_months"] = float(len(prices))

                mean_v = float(np.mean(prices))
                if mean_v > 0:
                    rec["be_value_cv"] = float(np.std(prices) / mean_v)

                # Overall trend
                if prices[0] > 0:
                    rec["be_value_trend_pct"] = (prices[-1] - prices[0]) / prices[0] * 100

                # Momentum: last quarter vs first quarter
                q = max(1, len(prices) // 4)
                early_avg = float(np.mean(prices[:q]))
                late_avg = float(np.mean(prices[-q:]))
                if early_avg > 0:
                    rec["be_value_momentum"] = late_avg / early_avg

                # Max drawdown
                peak = prices[0]
                max_dd = 0.0
                trough_idx = 0
                for i, p in enumerate(prices):
                    if p > peak:
                        peak = p
                    dd = (peak - p) / peak * 100 if peak > 0 else 0
                    if dd > max_dd:
                        max_dd = dd
                        trough_idx = i
                rec["be_value_max_drawdown"] = max_dd

                # Recovery from drawdown
                if max_dd > 0 and trough_idx < len(prices) - 1:
                    trough_price = prices[trough_idx]
                    post_peak = max(prices[trough_idx:])
                    if trough_price > 0:
                        rec["be_value_recovery"] = (post_peak - trough_price) / trough_price * 100

        # --- Candlestick features ---
        candles = _parse_json(row.get("candlestick_json"))
        if isinstance(candles, list) and len(candles) >= 3:
            ranges: list[float] = []
            bearish_count = 0
            body_range_ratios: list[float] = []
            upper_shadow_pcts: list[float] = []

            for candle in candles:
                if not isinstance(candle, (list, tuple, dict)):
                    continue

                # Support both list [date, open, high, low, close] and dict format
                if isinstance(candle, dict):
                    o = safe_float(candle.get("open") or candle.get("o"))
                    h = safe_float(candle.get("high") or candle.get("h"))
                    lo = safe_float(candle.get("low") or candle.get("l"))
                    c = safe_float(candle.get("close") or candle.get("c"))
                elif isinstance(candle, (list, tuple)) and len(candle) >= 5:
                    o = safe_float(candle[1])
                    h = safe_float(candle[2])
                    lo = safe_float(candle[3])
                    c = safe_float(candle[4])
                else:
                    continue

                if o is None or h is None or lo is None or c is None:
                    continue
                if h <= 0 or lo <= 0:
                    continue

                candle_range = h - lo
                if candle_range <= 0:
                    continue

                close_val = c if c > 0 else 1.0
                ranges.append(candle_range / close_val * 100)

                if c < o:
                    bearish_count += 1

                body = abs(c - o)
                body_range_ratios.append(body / candle_range)

                upper_shadow = h - max(o, c)
                upper_shadow_pcts.append(upper_shadow / candle_range * 100)

            if ranges:
                n = len(ranges)
                rec["be_candle_avg_range_pct"] = float(np.mean(ranges))
                rec["be_candle_bearish_pct"] = bearish_count / n * 100
                rec["be_candle_trend_strength"] = float(np.mean(body_range_ratios))
                rec["be_candle_upper_shadow_pct"] = float(np.mean(upper_shadow_pcts))

                # Volatility trend: compare late vs early candle ranges
                if n >= 4:
                    mid = n // 2
                    early_vol = float(np.mean(ranges[:mid]))
                    late_vol = float(np.mean(ranges[mid:]))
                    if early_vol > 0:
                        rec["be_candle_volatility_trend"] = (late_vol - early_vol) / early_vol * 100

        # --- Sales trend features ---
        sales_trend = _parse_json(row.get("sales_trend_json"))
        if isinstance(sales_trend, list) and len(sales_trend) >= 2:
            volumes: list[float] = []
            for entry in sales_trend:
                vol = None
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    vol = safe_float(entry[1])
                elif isinstance(entry, dict):
                    vol = safe_float(entry.get("volume") or entry.get("count") or entry.get("qty"))

                if vol is not None and vol >= 0:
                    volumes.append(vol)

            if volumes:
                rec["be_sales_avg_volume"] = float(np.mean(volumes))
                rec["be_sales_months_active"] = float(sum(1 for v in volumes if v > 0))

                mean_vol = float(np.mean(volumes))
                if mean_vol > 0:
                    rec["be_sales_volume_cv"] = float(np.std(volumes) / mean_vol)

                if len(volumes) >= 4:
                    q = max(1, len(volumes) // 4)
                    early_vol = float(np.mean(volumes[:q]))
                    late_vol = float(np.mean(volumes[-q:]))
                    if early_vol > 0:
                        rec["be_sales_volume_trend"] = late_vol / early_vol

        # --- Future estimate return ---
        future_est = safe_float(row.get("future_estimate_cents"))
        value_new = safe_float(row.get("value_new_cents"))
        if future_est and future_est > 0 and value_new and value_new > 0:
            rec["be_future_est_return"] = (future_est - value_new) / value_new * 100

        rows.append(rec)

    if not rows:
        return pd.DataFrame(columns=["set_number"])

    return pd.DataFrame(rows)
