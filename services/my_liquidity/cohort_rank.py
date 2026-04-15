"""Cohort-percentile ranking for Malaysian exit-liquidity signals.

Pulls the 5 MY signals for every set that has any Shopee or Carousell
competition data, joins in cohort metadata (year/theme/piece_group/
price_tier), adds a weighted composite score, and hands the list to
`services.backtesting.cohort.enrich_with_cohort_ranks` which owns the
bucketing and per-cohort percentile math.

The 5 signals:
- my_sold_velocity_30d:  Shopee total_sold_count delta over 30d
                         (higher = better, more demand)
- my_premium_median_pct: Shopee median MYR / (BL USD \u00d7 FX) - 1, %
                         (higher = better, room to mark up)
- my_saturation_inverse: 100 - max(Shopee score, Carousell score)
                         (higher = better, less competition)
- my_churn_ratio:        Carousell active\u2192sold flips / listings
                         (higher = better, faster flipping)
- my_liquidity_ratio:    Shopee listings_count / max(1, 30d sold)
                         (LOWER is better; we invert before ranking)

Composite weights: velocity 1.5, premium 1.2, churn 1.1, sat 1.0, liq 0.8.
"""

from __future__ import annotations

import logging
from typing import Any

from services.backtesting.cohort import enrich_with_cohort_ranks
from services.my_liquidity.premium import compute_premium
from services.my_liquidity.velocity import compute_velocity
from services.carousell.competition_repository import (
    get_flipped_to_sold_in_window,
    get_latest_snapshot as get_latest_carousell_snapshot,
)

logger = logging.getLogger(__name__)

SIGNAL_WEIGHTS: dict[str, float] = {
    "my_sold_velocity_30d": 1.5,
    "my_premium_median_pct": 1.2,
    "my_churn_ratio": 1.1,
    "my_saturation_inverse": 1.0,
    "my_liquidity_ratio": 0.8,
}


def build_signal_items(conn: Any) -> list[dict[str, Any]]:
    """Build per-set signal dicts for every set with any MY data.

    Returns a list of dicts with the five signal keys, plus the
    metadata keys `_assign_bucket` expects (set_number, year_released,
    release_date, theme, parts_count, rrp_usd_cents).

    Sets with neither Shopee nor Carousell snapshots are excluded.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT set_number FROM (
            SELECT set_number FROM shopee_competition_snapshots
            UNION
            SELECT set_number FROM carousell_competition_snapshots
        ) mine
        """,
    ).fetchall()
    set_numbers = [r[0] for r in rows]
    if not set_numbers:
        return []

    meta_map = _fetch_meta_map(conn, set_numbers)

    items: list[dict[str, Any]] = []
    for set_number in set_numbers:
        meta = meta_map.get(set_number, {})
        signals = _compute_signals_for_set(conn, set_number)
        if signals is None:
            continue
        items.append(
            {
                "set_number": set_number,
                **meta,
                **signals,
            }
        )

    items = _add_composite_score(items)
    return items


def compute_my_cohort_ranks(conn: Any) -> dict[str, dict[str, Any]]:
    """Build MY cohort ranks for every set with data.

    Returns a dict keyed by set_number -> cohort entry dict (same
    shape as the BL cohort cache). Sets with no MY data are absent.
    """
    items = build_signal_items(conn)
    if not items:
        return {}

    enriched = enrich_with_cohort_ranks(items)
    out: dict[str, dict[str, Any]] = {}
    for item in enriched:
        sn = item["set_number"]
        cohorts = item.get("cohorts") or {}
        if cohorts:
            out[sn] = cohorts
    return out


def _fetch_meta_map(conn: Any, set_numbers: list[str]) -> dict[str, dict[str, Any]]:
    """Return {set_number: {year_released, release_date, theme, parts_count, rrp_usd_cents}}.

    Uses a latest-per-set subquery against brickeconomy_snapshots and
    falls back to bricklink_items for year/theme/parts_count.
    """
    if not set_numbers:
        return {}

    placeholders = ",".join(["?"] * len(set_numbers))
    be_rows = conn.execute(
        f"""
        SELECT set_number, year_released, release_date, theme, pieces, rrp_usd_cents
        FROM (
            SELECT set_number, year_released, release_date, theme, pieces, rrp_usd_cents,
                   ROW_NUMBER() OVER (
                       PARTITION BY set_number ORDER BY scraped_at DESC
                   ) AS rn
            FROM brickeconomy_snapshots
            WHERE set_number IN ({placeholders})
        ) sub WHERE rn = 1
        """,  # noqa: S608 -- placeholders are from parameterized list
        set_numbers,
    ).fetchall()

    meta: dict[str, dict[str, Any]] = {}
    for r in be_rows:
        meta[r[0]] = {
            "year_released": r[1],
            "release_date": r[2].isoformat() if r[2] is not None and hasattr(r[2], "isoformat") else r[2],
            "theme": r[3],
            "parts_count": r[4],
            "rrp_usd_cents": r[5],
        }

    bl_rows = conn.execute(
        f"""
        SELECT set_number, year_released, theme, parts_count
        FROM bricklink_items
        WHERE set_number IN ({placeholders})
        """,  # noqa: S608 -- placeholders parameterized
        set_numbers,
    ).fetchall()
    for r in bl_rows:
        sn = r[0]
        existing = meta.setdefault(
            sn,
            {
                "year_released": None,
                "release_date": None,
                "theme": None,
                "parts_count": None,
                "rrp_usd_cents": None,
            },
        )
        if existing.get("year_released") is None and r[1] is not None:
            existing["year_released"] = r[1]
        if existing.get("theme") is None and r[2] is not None:
            existing["theme"] = r[2]
        if existing.get("parts_count") is None and r[3] is not None:
            existing["parts_count"] = r[3]

    return meta


def _compute_signals_for_set(
    conn: Any,
    set_number: str,
) -> dict[str, float | None] | None:
    """Compute the 5 MY signals for a single set.

    Returns None if the set has neither Shopee nor Carousell data.
    Individual signals may be None when inputs are missing; cohort.py
    will simply skip those metrics for that item.
    """
    shopee_latest = conn.execute(
        """
        SELECT listings_count, saturation_score
        FROM shopee_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()

    carousell_latest = get_latest_carousell_snapshot(conn, set_number)

    if shopee_latest is None and carousell_latest is None:
        return None

    vel_30 = compute_velocity(conn, set_number, window_days=30)
    premium = compute_premium(conn, set_number)
    flip_30_row = get_flipped_to_sold_in_window(conn, set_number, 30)
    flip_30 = flip_30_row.get("flipped") if flip_30_row else None

    shopee_sat = float(shopee_latest[1]) if shopee_latest else None
    carousell_sat = (
        float(carousell_latest["saturation_score"]) if carousell_latest else None
    )
    sat_components = [s for s in (shopee_sat, carousell_sat) if s is not None]
    saturation_inverse = (
        round(100.0 - max(sat_components), 1) if sat_components else None
    )

    shopee_listings = int(shopee_latest[0]) if shopee_latest else 0
    carousell_listings = (
        int(carousell_latest["listings_count"]) if carousell_latest else 0
    )

    churn_ratio: float | None = None
    if carousell_listings > 0 and flip_30 is not None:
        churn_ratio = round(flip_30 / carousell_listings, 4)

    liquidity_ratio: float | None = None
    if shopee_listings > 0 and vel_30.total_sold_delta is not None and vel_30.total_sold_delta > 0:
        liquidity_ratio = round(shopee_listings / max(1, vel_30.total_sold_delta), 4)

    return {
        "my_sold_velocity_30d": (
            float(vel_30.total_sold_delta)
            if vel_30.total_sold_delta is not None
            else None
        ),
        "my_premium_median_pct": premium.premium_median_pct,
        "my_saturation_inverse": saturation_inverse,
        "my_churn_ratio": churn_ratio,
        "my_liquidity_ratio": (
            -liquidity_ratio if liquidity_ratio is not None else None
        ),
    }


def _add_composite_score(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a weighted composite score derived from global percentiles.

    For each signal, compute each item's global percentile (across ALL
    items with the signal present). Weight-average those percentiles
    per-item using SIGNAL_WEIGHTS. Items missing every signal get
    composite_score=None; items partially present are averaged over
    only the weights they have.
    """
    if not items:
        return items

    global_values: dict[str, list[float]] = {}
    for signal in SIGNAL_WEIGHTS:
        vals = [
            float(item[signal])
            for item in items
            if item.get(signal) is not None
        ]
        global_values[signal] = sorted(vals)

    out: list[dict[str, Any]] = []
    for item in items:
        total_weight = 0.0
        weighted_sum = 0.0
        for signal, weight in SIGNAL_WEIGHTS.items():
            v = item.get(signal)
            if v is None:
                continue
            sorted_vals = global_values[signal]
            if not sorted_vals:
                continue
            pct = _percentile(sorted_vals, float(v))
            weighted_sum += pct * weight
            total_weight += weight
        composite = round(weighted_sum / total_weight, 2) if total_weight > 0 else None
        out.append({**item, "composite_score": composite})
    return out


def _percentile(sorted_values: list[float], target: float) -> float:
    """Percentile rank of target within sorted_values (0-100)."""
    n = len(sorted_values)
    if n == 0:
        return 50.0
    if n == 1:
        return 50.0
    count_below = sum(1 for v in sorted_values if v < target)
    count_equal = sum(1 for v in sorted_values if v == target)
    return (count_below + 0.5 * count_equal) / n * 100.0
