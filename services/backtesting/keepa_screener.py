"""Keepa-based signal computation for cohort ranking.

Computes signals from Keepa Amazon pricing data (3P FBA premium, reviews,
stock-out patterns) and factual metadata (minifig value, price per part).
Replaces BrickEconomy growth-based signals with real market signals.

Top 5 features from Experiment 31 feature selection:
  1. 3p_premium_x_minifig_density (gain=408)
  2. minifig_value_ratio (gain=341)
  3. amz_review_count (gain=307)
  4. price_per_part (gain=289)
  5. 3p_prem_adj (gain=284) -- theme-discounted 3P premium
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Themes where 3P premium is inflated but doesn't translate to BL appreciation
FALSE_POS_THEMES = frozenset({
    "Dots", "DUPLO", "Duplo", "Classic", "Seasonal",
    "Holiday & Event", "Trolls World Tour", "Vidiyo",
})


_KEEPA_QUERY = """
    SELECT
        ks.set_number,
        ks.new_3p_fba_json,
        ks.review_count AS kp_review_count,
        ks.rating AS kp_rating,
        ks.tracking_users
    FROM (
        SELECT DISTINCT ON (set_number) *
        FROM keepa_snapshots
        WHERE amazon_price_json IS NOT NULL
        ORDER BY set_number, scraped_at DESC
    ) ks
"""

_META_QUERY = """
    SELECT
        li.set_number,
        COALESCE(NULLIF(li.title, ''), be.title) AS title,
        COALESCE(li.theme, be.theme) AS theme,
        be.subtheme,
        COALESCE(li.year_released, be.year_released) AS year_released,
        COALESCE(be.pieces, li.parts_count) AS parts_count,
        be.rrp_usd_cents,
        be.minifig_value_cents,
        COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
        CAST(COALESCE(
            li.retired_date,
            be.retired_date,
            CASE WHEN li.year_retired IS NOT NULL
                 THEN (li.year_retired::TEXT || '-07-01')::DATE
            END
        ) AS TEXT) AS retired_date,
        CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date,
        COALESCE(
            li.year_retired,
            EXTRACT(YEAR FROM be.retired_date)::INTEGER
        ) AS year_retired
    FROM lego_items li
    JOIN (
        SELECT DISTINCT ON (set_number) *
        FROM brickeconomy_snapshots
        ORDER BY set_number, scraped_at DESC
    ) be ON li.set_number = be.set_number
    WHERE be.rrp_usd_cents > 0
"""


def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and (pd.isna(val) or np.isnan(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: object) -> int | None:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_str(val: object) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val)


def _parse_json_timeline(raw: object) -> list:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


def _compute_3p_premium(
    fba_timeline: list,
    rrp_cents: float,
    retired_date_str: str | None,
) -> float | None:
    """Compute avg 3P FBA premium above RRP (%), cut at retired_date."""
    if not fba_timeline or rrp_cents <= 0:
        return None

    prices: list[float] = []
    for point in fba_timeline:
        if len(point) < 2:
            continue
        # Cut at retired_date for retired sets
        if retired_date_str and isinstance(point[0], str) and point[0] > retired_date_str:
            break
        if point[1] is not None and point[1] > 0:
            prices.append(float(point[1]))

    if not prices:
        return None

    avg_price = float(np.mean(prices))
    return (avg_price - rrp_cents) / rrp_cents * 100


def _score_3p_premium(premium_pct: float | None) -> float | None:
    """Convert 3P premium % to 0-100 score."""
    if premium_pct is None:
        return None
    if premium_pct >= 50:
        return 95.0
    if premium_pct >= 30:
        return 85.0
    if premium_pct >= 15:
        return 70.0
    if premium_pct >= 5:
        return 55.0
    if premium_pct >= 0:
        return 40.0
    if premium_pct >= -10:
        return 25.0
    return 10.0


def _score_demand_intensity(review_count: int | None) -> float | None:
    """Convert Amazon review count to 0-100 score."""
    if review_count is None:
        return None
    if review_count >= 10000:
        return 95.0
    if review_count >= 5000:
        return 85.0
    if review_count >= 2000:
        return 75.0
    if review_count >= 1000:
        return 60.0
    if review_count >= 500:
        return 45.0
    if review_count >= 100:
        return 30.0
    return 15.0


def _score_value_density(price_per_part: float | None) -> float | None:
    """Convert price-per-part to 0-100 score. Lower = better value = higher score."""
    if price_per_part is None or price_per_part <= 0:
        return None
    # Invert: lower price per part = higher score
    if price_per_part <= 5:
        return 95.0
    if price_per_part <= 8:
        return 80.0
    if price_per_part <= 12:
        return 65.0
    if price_per_part <= 18:
        return 50.0
    if price_per_part <= 25:
        return 35.0
    return 15.0


def _score_minifig_premium(mfig_value_ratio: float | None) -> float | None:
    """Convert minifig value / RRP ratio to 0-100 score."""
    if mfig_value_ratio is None:
        return None
    if mfig_value_ratio >= 0.8:
        return 95.0
    if mfig_value_ratio >= 0.5:
        return 80.0
    if mfig_value_ratio >= 0.3:
        return 65.0
    if mfig_value_ratio >= 0.15:
        return 50.0
    if mfig_value_ratio >= 0.05:
        return 35.0
    return 15.0


def _compute_keepa_composite(
    adjusted_premium: float | None,
    demand_intensity: float | None,
    minifig_premium: float | None,
    value_density: float | None,
    third_party_premium: float | None,
) -> float | None:
    """Weighted composite from Keepa signals. Weights from model feature importance."""
    signals: list[tuple[float, float]] = []

    if adjusted_premium is not None:
        signals.append((adjusted_premium, 2.0))
    if demand_intensity is not None:
        signals.append((demand_intensity, 1.5))
    if minifig_premium is not None:
        signals.append((minifig_premium, 1.2))
    if value_density is not None:
        signals.append((value_density, 0.8))
    if third_party_premium is not None:
        signals.append((third_party_premium, 0.5))

    if not signals:
        return None

    weighted_sum = sum(v * w for v, w in signals)
    weight_sum = sum(w for _, w in signals)
    return round(weighted_sum / weight_sum, 1)


def compute_keepa_signals(conn: Any) -> list[dict]:
    """Compute Keepa-based signals for all sets."""
    keepa_df = conn.execute(_KEEPA_QUERY).df()
    meta_df = conn.execute(_META_QUERY).df()

    # Build lookups
    keepa_lookup: dict[str, pd.Series] = {}
    for _, row in keepa_df.iterrows():
        keepa_lookup[str(row["set_number"])] = row

    results: list[dict] = []
    for _, meta in meta_df.iterrows():
        sn = str(meta["set_number"])
        rrp = _safe_float(meta.get("rrp_usd_cents"))
        if not rrp or rrp <= 0:
            continue

        kp = keepa_lookup.get(sn)
        theme = _safe_str(meta.get("theme")) or ""
        parts = _safe_float(meta.get("parts_count"))
        mfig_val = _safe_float(meta.get("minifig_value_cents"))
        retired_date = _safe_str(meta.get("retired_date"))

        # Signal 1: 3P Premium
        fba_timeline = _parse_json_timeline(kp["new_3p_fba_json"]) if kp is not None else []
        premium_pct = _compute_3p_premium(fba_timeline, rrp, retired_date)
        third_party_premium = _score_3p_premium(premium_pct)

        # Signal 2: Demand Intensity (Amazon reviews)
        review_count = _safe_int(kp["kp_review_count"]) if kp is not None else None
        demand_intensity = _score_demand_intensity(review_count)

        # Signal 3: Value Density (price per part)
        price_per_part = rrp / parts if parts and parts > 0 else None
        value_density = _score_value_density(price_per_part)

        # Signal 4: Minifig Premium
        mfig_ratio = mfig_val / rrp if mfig_val and mfig_val > 0 else 0.0
        minifig_premium = _score_minifig_premium(mfig_ratio)

        # Signal 5: Adjusted Premium (theme-discounted)
        is_false_pos = theme in FALSE_POS_THEMES
        if third_party_premium is not None:
            adjusted_premium = third_party_premium * (0.5 if is_false_pos else 1.0)
        else:
            adjusted_premium = None

        composite = _compute_keepa_composite(
            adjusted_premium, demand_intensity, minifig_premium,
            value_density, third_party_premium,
        )

        if composite is None:
            continue

        results.append({
            "item_id": sn,
            "set_number": sn,
            "title": _safe_str(meta.get("title")),
            "theme": theme,
            "year_released": _safe_int(meta.get("year_released")),
            "year_retired": _safe_int(meta.get("year_retired")),
            "release_date": _safe_str(meta.get("release_date")),
            "parts_count": _safe_int(meta.get("parts_count")),
            "rrp_usd_cents": _safe_int(meta.get("rrp_usd_cents")),
            "composite_score": composite,
            "third_party_premium": third_party_premium,
            "demand_intensity": demand_intensity,
            "value_density": value_density,
            "minifig_premium": minifig_premium,
            "adjusted_premium": adjusted_premium,
            # Raw values for display
            "premium_pct_raw": round(premium_pct, 1) if premium_pct is not None else None,
            "review_count_raw": review_count,
            "price_per_part_raw": round(price_per_part, 1) if price_per_part is not None else None,
            "minifig_value_ratio_raw": round(mfig_ratio, 3) if mfig_ratio else None,
        })

    results.sort(key=lambda r: r.get("composite_score") or 0, reverse=True)
    return results


def compute_keepa_signals_with_cohort(conn: Any) -> list[dict]:
    """Compute Keepa signals for all sets, enriched with cohort ranks."""
    from services.backtesting.cohort import enrich_with_cohort_ranks

    items = compute_keepa_signals(conn)
    return enrich_with_cohort_ranks(items)
