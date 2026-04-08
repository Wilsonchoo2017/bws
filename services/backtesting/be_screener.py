"""BrickEconomy-based signal computation for cohort ranking.

Computes demand_pressure and composite_score from BrickEconomy data
(sales_trend_json, annual_growth_pct, theme_rank) instead of BrickLink
monthly sales. Reuses the same cohort ranking machinery.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_BE_QUERY = """
    SELECT
        t.set_number,
        t.title,
        t.theme,
        t.subtheme,
        t.year_released,
        t.year_retired,
        t.pieces,
        t.rrp_usd_cents,
        t.sales_trend_json,
        t.annual_growth_pct,
        t.total_growth_pct,
        t.growth_90d_pct,
        t.theme_rank,
        t.value_new_cents,
        t.review_count,
        t.release_date
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY set_number ORDER BY scraped_at DESC
               ) AS rn
        FROM brickeconomy_snapshots
    ) t
    WHERE t.rn = 1
"""


def _load_be_data(conn: Any) -> pd.DataFrame:
    """Load latest BrickEconomy snapshot per set."""
    return conn.execute(_BE_QUERY).df()


def _parse_sales_trend(raw: Any) -> list | None:
    """Parse sales_trend_json into a list, handling all DB representations."""
    if raw is None:
        return None
    if isinstance(raw, float):
        return None
    if isinstance(raw, list):
        return raw if raw else None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) and parsed else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _safe_float(val: Any) -> float | None:
    """Convert a value to float, returning None for NaN/None."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    return float(val)


def _safe_int(val: Any) -> int | None:
    """Convert a value to int, returning None for NaN/None."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    return int(val)


def _safe_str(val: Any) -> str | None:
    """Convert a value to str, returning None for NaN/None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val)


def _compute_be_demand_pressure(sales_trend: list) -> float | None:
    """Compute demand pressure from BE sales_trend_json.

    Uses trailing 3-month average sales volume, same bucketing logic
    as the BrickLink version for comparable scoring.
    """
    recent = sales_trend[-3:]
    if not recent:
        return None

    vals = [v for _, v in recent if v is not None and v > 0]
    if not vals:
        return None

    avg_monthly = sum(vals) / len(vals)

    if avg_monthly >= 50:
        return 95.0
    if avg_monthly >= 20:
        return 80.0
    if avg_monthly >= 10:
        return 65.0
    if avg_monthly >= 5:
        return 50.0
    if avg_monthly >= 1:
        return 30.0
    return 15.0


def _compute_be_theme_growth(
    annual_growth_pct: float | None,
) -> float | None:
    """Convert BE annual_growth_pct to 0-100 score.

    Same thresholds as the BrickLink theme_growth signal.
    """
    if annual_growth_pct is None:
        return None

    if annual_growth_pct >= 15.0:
        return 95.0
    if annual_growth_pct >= 10.0:
        return 80.0
    if annual_growth_pct >= 7.0:
        return 65.0
    if annual_growth_pct >= 5.0:
        return 50.0
    if annual_growth_pct >= 3.0:
        return 35.0
    return 20.0


def _compute_be_composite(
    demand: float | None,
    theme_growth: float | None,
    growth_90d: float | None,
) -> float | None:
    """Simple weighted composite from BE-available signals."""
    signals: list[tuple[float, float]] = []

    if demand is not None:
        signals.append((demand, 1.5))
    if theme_growth is not None:
        signals.append((theme_growth, 1.2))

    # 90-day momentum (down-weighted like price_trend)
    if growth_90d is not None:
        momentum_score = min(100.0, max(0.0, 50.0 + growth_90d))
        signals.append((momentum_score, 0.3))

    if not signals:
        return None

    weighted_sum = sum(v * w for v, w in signals)
    weight_sum = sum(w for _, w in signals)
    return round(weighted_sum / weight_sum, 1)


def compute_be_signals(conn: Any) -> list[dict]:
    """Compute BrickEconomy-based signals for all sets."""
    df = _load_be_data(conn)

    results: list[dict] = []
    for _, row in df.iterrows():
        sales_trend = _parse_sales_trend(row.get("sales_trend_json"))
        if not sales_trend:
            continue

        demand = _compute_be_demand_pressure(sales_trend)
        theme_growth = _compute_be_theme_growth(_safe_float(row.get("annual_growth_pct")))
        growth_90d = _safe_float(row.get("growth_90d_pct"))
        composite = _compute_be_composite(demand, theme_growth, growth_90d)

        if composite is None:
            continue

        results.append({
            "item_id": str(row["set_number"]),
            "set_number": str(row["set_number"]),
            "title": _safe_str(row.get("title")),
            "theme": _safe_str(row.get("theme")),
            "year_released": _safe_int(row.get("year_released")),
            "year_retired": _safe_int(row.get("year_retired")),
            "release_date": _safe_str(row.get("release_date")),
            "parts_count": _safe_int(row.get("pieces")),
            "rrp_usd_cents": _safe_int(row.get("rrp_usd_cents")),
            "composite_score": composite,
            "demand_pressure": demand,
            "theme_growth": theme_growth,
        })

    results.sort(key=lambda r: r.get("composite_score") or 0, reverse=True)
    return results


def compute_be_signals_with_cohort(conn: Any) -> list[dict]:
    """Compute BE signals for all sets, enriched with cohort ranks."""
    from services.backtesting.cohort import enrich_with_cohort_ranks

    items = compute_be_signals(conn)
    return enrich_with_cohort_ranks(items)
