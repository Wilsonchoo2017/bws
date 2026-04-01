"""Multi-strategy cohort ranking for LEGO sets.

Groups sets into cohorts by different dimensions (time, theme, size, price)
and computes percentile ranks within each cohort for composite score
and selected individual signals.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_COHORT_SIZE = 3

RANKED_METRICS: tuple[str, ...] = (
    "composite_score",
    "demand_pressure",
    "price_vs_rrp",
)

PIECE_GROUPS: tuple[tuple[str, int, int], ...] = (
    ("small", 0, 500),
    ("medium", 500, 1000),
    ("large", 1000, 2000),
    ("xlarge", 2000, 3000),
    ("massive", 3000, 999_999),
)

# USD cents thresholds
PRICE_TIERS: tuple[tuple[str, int, int], ...] = (
    ("budget", 0, 5_000),        # < $50
    ("mid", 5_000, 15_000),      # $50-$149
    ("premium", 15_000, 35_000), # $150-$349
    ("ultra", 35_000, 999_999),  # $350+
)

STRATEGY_NAMES: tuple[str, ...] = (
    "half_year",
    "year",
    "theme",
    "year_theme",
    "price_tier",
    "piece_group",
)


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CohortAssignment:
    strategy: str
    key: str


def _half_year_from_release_date(release_date: str | None) -> str | None:
    """Convert ISO month '2022-06' to '2022-H1' or '2022-H2'."""
    if not release_date or len(release_date) < 7:
        return None
    try:
        year = release_date[:4]
        month = int(release_date[5:7])
    except (ValueError, IndexError):
        return None
    half = "H1" if month <= 6 else "H2"
    return f"{year}-{half}"


def _find_tier(value: int | float, tiers: tuple[tuple[str, int, int], ...]) -> str | None:
    """Find which tier a value falls into."""
    for label, low, high in tiers:
        if low <= value < high:
            return label
    return None


def _assign_bucket(item: dict, strategy: str) -> str | None:
    """Assign a single item to a bucket for the given strategy.

    Returns bucket key string or None if insufficient data.
    """
    if strategy == "half_year":
        release_date = item.get("release_date")
        if release_date:
            return _half_year_from_release_date(release_date)
        # Fallback: use year_released as "YYYY-H1" (assume H1 if no month)
        yr = item.get("year_released")
        return f"{yr}-H1" if yr else None

    if strategy == "year":
        yr = item.get("year_released")
        return str(yr) if yr else None

    if strategy == "theme":
        theme = item.get("theme")
        return theme if theme else None

    if strategy == "year_theme":
        yr = item.get("year_released")
        theme = item.get("theme")
        return f"{yr}|{theme}" if yr and theme else None

    if strategy == "price_tier":
        rrp = item.get("rrp_usd_cents")
        if rrp is None or rrp <= 0:
            return None
        return _find_tier(rrp, PRICE_TIERS)

    if strategy == "piece_group":
        parts = item.get("parts_count")
        if parts is None or parts <= 0:
            return None
        return _find_tier(parts, PIECE_GROUPS)

    return None


# ---------------------------------------------------------------------------
# Percentile computation
# ---------------------------------------------------------------------------


def _compute_percentile(values: list[float], target: float) -> float:
    """Percentile rank of target within values (0-100).

    Uses the 'percentage of scores less than or equal to' method.
    For a cohort of 1, returns 50 (neutral).
    """
    n = len(values)
    if n <= 1:
        return 50.0
    count_below = sum(1 for v in values if v < target)
    count_equal = sum(1 for v in values if v == target)
    percentile = (count_below + 0.5 * count_equal) / n * 100.0
    return round(percentile, 1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def enrich_with_cohort_ranks(
    items: list[dict],
    min_cohort_size: int = MIN_COHORT_SIZE,
) -> list[dict]:
    """Add cohort percentile ranks to each item across multiple strategies.

    Returns a new list of dicts (no mutation of originals). Each dict gets
    a 'cohorts' key containing a dict keyed by strategy name.

    Example output per item:
        {
            ...existing signals...,
            "cohorts": {
                "year": {
                    "key": "2022",
                    "size": 42,
                    "composite_pct": 85.4,
                    "demand_pct": 71.2,
                    "price_perf_pct": 90.1,
                    "rank": 5,
                },
                "theme": { ... },
                ...
            }
        }
    """
    if not items:
        return []

    # Phase 1: assign buckets for each strategy
    # strategy -> bucket_key -> [item_index, ...]
    buckets: dict[str, dict[str, list[int]]] = {
        s: defaultdict(list) for s in STRATEGY_NAMES
    }

    for idx, item in enumerate(items):
        for strategy in STRATEGY_NAMES:
            key = _assign_bucket(item, strategy)
            if key is not None:
                buckets[strategy][key].append(idx)

    # Phase 2: compute ranks within each qualifying cohort
    # Pre-initialize cohort data for each item
    cohort_data: list[dict[str, dict]] = [{} for _ in items]

    for strategy in STRATEGY_NAMES:
        for bucket_key, member_indices in buckets[strategy].items():
            if len(member_indices) < min_cohort_size:
                continue

            cohort_size = len(member_indices)

            # Extract metric values for this cohort
            metric_values: dict[str, list[tuple[int, float]]] = {}
            for metric in RANKED_METRICS:
                vals = []
                for idx in member_indices:
                    v = items[idx].get(metric)
                    if v is not None:
                        vals.append((idx, float(v)))
                metric_values[metric] = vals

            # Compute composite ranks (for ordinal ranking)
            composite_vals = metric_values.get("composite_score", [])
            composite_sorted = sorted(
                composite_vals, key=lambda x: x[1], reverse=True
            )
            ordinal_rank: dict[int, int] = {}
            for rank_pos, (idx, _) in enumerate(composite_sorted, start=1):
                ordinal_rank[idx] = rank_pos

            # Build cohort entry for each member
            for idx in member_indices:
                entry: dict[str, str | int | float | None] = {
                    "key": bucket_key,
                    "size": cohort_size,
                }

                # Percentile for each ranked metric
                pct_keys = {
                    "composite_score": "composite_pct",
                    "demand_pressure": "demand_pct",
                    "price_vs_rrp": "price_perf_pct",
                }
                for metric, pct_key in pct_keys.items():
                    vals_list = metric_values.get(metric, [])
                    item_val = items[idx].get(metric)
                    if item_val is not None and len(vals_list) >= min_cohort_size:
                        all_vals = [v for _, v in vals_list]
                        entry[pct_key] = _compute_percentile(
                            all_vals, float(item_val)
                        )
                    else:
                        entry[pct_key] = None

                entry["rank"] = ordinal_rank.get(idx)

                cohort_data[idx][strategy] = entry

    # Phase 3: build new items with cohort data
    return [
        {**item, "cohorts": cohort_data[idx] if cohort_data[idx] else None}
        for idx, item in enumerate(items)
    ]
