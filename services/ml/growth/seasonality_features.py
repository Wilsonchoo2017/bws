"""Calendar-aware Q4 seasonality features for the growth model.

Builds Q4-specific pricing, YoY comparison, and retail-clearance signals from
Keepa `amazon_price_json`, `new_3p_fba_json`, and `new_3p_fbm_json` timelines.

All features respect `cutoff_dates` so that training on retired sets cannot
leak post-retirement observations — the same pattern used by
`engineer_keepa_features` in features.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


Q4_FEATURE_NAMES: tuple[str, ...] = (
    # Group A — Q4 pricing (Amazon + 3P)
    "kp_q4_avg_discount",
    "kp_q4_max_discount",
    "kp_q4_vs_nonq4_disc_delta",
    "kp_q4_fba_floor_vs_rrp",
    "kp_q4_oct_dec_trajectory",
    "kp_q4_fbm_premium_pct",
    # Group B — Q4 YoY comparisons (require ≥2 observed Q4 years)
    "kp_yoy_q4_disc_delta",
    "kp_yoy_q4_price_delta_pct",
    "kp_q4_price_cagr",
    "kp_q4_disc_slope",
    "kp_yoy_q4_count",
    # Group D — retail clearance detection
    "kp_q4_clearance_signal",
    "kp_q4_clearance_slope",
    "kp_amazon_oos_in_q4",
    "kp_q4_price_above_rrp_pct",
)

# Minimum Q4 price points across all observed years before emitting Group A
# features. Protects against sets with sparse Keepa coverage in Oct-Dec.
MIN_Q4_POINTS = 10


def _parse_json(value: Any) -> list[Any]:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return list(value) if isinstance(value, list) else []


def _iter_points(timeline: Iterable[Any], cutoff_ym: str | None) -> Iterable[tuple[int, int, float]]:
    for point in timeline:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        ts, price = point[0], point[1]
        if price is None or price <= 0:
            continue
        if not isinstance(ts, str) or len(ts) < 7:
            continue
        if cutoff_ym and ts[:7] > cutoff_ym:
            break
        try:
            year = int(ts[:4])
            month = int(ts[5:7])
        except ValueError:
            continue
        yield year, month, float(price)


def _bucket_by_quarter(
    timeline: Iterable[Any],
    cutoff_ym: str | None,
) -> tuple[dict[int, list[float]], list[float], list[tuple[str, int, int]]]:
    """Return (q4_by_year, non_q4_prices, raw_points).

    - q4_by_year: {year -> list of prices observed in Oct-Dec that year}
    - non_q4_prices: all prices in months 1-9 across the in-cutoff window
    - raw_points: [(ts[:7], month, index)] — used for OOS detection in Group D
    """
    q4_by_year: dict[int, list[float]] = {}
    non_q4_prices: list[float] = []
    raw_points: list[tuple[str, int, int]] = []

    idx = 0
    for point in timeline:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        ts = point[0]
        price = point[1]
        if not isinstance(ts, str) or len(ts) < 7:
            continue
        if cutoff_ym and ts[:7] > cutoff_ym:
            break
        raw_points.append((ts[:7], int(ts[5:7]) if ts[5:7].isdigit() else 0, idx))
        idx += 1

        if price is None or price <= 0:
            continue
        try:
            year = int(ts[:4])
            month = int(ts[5:7])
        except ValueError:
            continue

        if month >= 10:
            q4_by_year.setdefault(year, []).append(float(price))
        else:
            non_q4_prices.append(float(price))

    return q4_by_year, non_q4_prices, raw_points


def _flatten_q4(q4_by_year: dict[int, list[float]]) -> list[float]:
    return [p for prices in q4_by_year.values() for p in prices]


def _compute_amazon_features(
    amz_timeline: list[Any],
    rrp: float,
    cutoff_ym: str | None,
) -> dict[str, float]:
    """Features derived from amazon_price_json (Groups A, B, D)."""
    feat: dict[str, float] = {}

    # OOS detection runs independently of Q4 coverage — it only needs one
    # null-price gap anywhere in the in-cutoff timeline.
    first_oos_month: int | None = None
    last_price: float | None = None
    for point in amz_timeline:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        ts, price = point[0], point[1]
        if not isinstance(ts, str) or len(ts) < 7:
            continue
        if cutoff_ym and ts[:7] > cutoff_ym:
            break
        if price is not None and price > 0:
            last_price = float(price)
            continue
        if last_price is not None and first_oos_month is None:
            try:
                first_oos_month = int(ts[5:7])
            except ValueError:
                continue
    if first_oos_month is not None:
        feat["kp_amazon_oos_in_q4"] = 1.0 if first_oos_month >= 10 else 0.0

    q4_by_year, non_q4, _ = _bucket_by_quarter(amz_timeline, cutoff_ym)
    q4_all = _flatten_q4(q4_by_year)

    if len(q4_all) < MIN_Q4_POINTS:
        return feat

    q4_mean = float(np.mean(q4_all))
    q4_min = float(min(q4_all))

    feat["kp_q4_avg_discount"] = (rrp - q4_mean) / rrp * 100.0
    feat["kp_q4_max_discount"] = (rrp - q4_min) / rrp * 100.0
    feat["kp_q4_price_above_rrp_pct"] = (
        100.0 * sum(1 for p in q4_all if p >= rrp * 0.98) / len(q4_all)
    )

    if non_q4:
        non_q4_disc = (rrp - float(np.mean(non_q4))) / rrp * 100.0
        feat["kp_q4_vs_nonq4_disc_delta"] = feat["kp_q4_avg_discount"] - non_q4_disc

    # Per-year summaries used by YoY and clearance features
    years_sorted = sorted(q4_by_year.keys())
    year_mean: dict[int, float] = {y: float(np.mean(q4_by_year[y])) for y in years_sorted}
    year_max_disc: dict[int, float] = {
        y: (rrp - float(min(q4_by_year[y]))) / rrp * 100.0 for y in years_sorted
    }
    year_avg_disc: dict[int, float] = {
        y: (rrp - year_mean[y]) / rrp * 100.0 for y in years_sorted
    }

    feat["kp_yoy_q4_count"] = float(len(years_sorted))

    # Oct-Dec trajectory: (Dec mean − Oct mean) / Oct mean, latest Q4 only
    latest_year = years_sorted[-1]
    latest_points = [
        (month, price)
        for year, month, price in _iter_points(amz_timeline, cutoff_ym)
        if year == latest_year and 10 <= month <= 12
    ]
    oct_prices = [p for m, p in latest_points if m == 10]
    dec_prices = [p for m, p in latest_points if m == 12]
    if oct_prices and dec_prices:
        oct_mean = float(np.mean(oct_prices))
        dec_mean = float(np.mean(dec_prices))
        if oct_mean > 0:
            feat["kp_q4_oct_dec_trajectory"] = (dec_mean - oct_mean) / oct_mean * 100.0

    # --- Group B: YoY / multi-year rate of change ---
    if len(years_sorted) >= 2:
        last_y, prev_y = years_sorted[-1], years_sorted[-2]
        feat["kp_yoy_q4_disc_delta"] = year_avg_disc[last_y] - year_avg_disc[prev_y]
        prev_mean = year_mean[prev_y]
        if prev_mean > 0:
            feat["kp_yoy_q4_price_delta_pct"] = (
                (year_mean[last_y] - prev_mean) / prev_mean * 100.0
            )

        # CAGR of Q4 mean price across first-to-last observed Q4
        span = last_y - years_sorted[0]
        first_mean = year_mean[years_sorted[0]]
        if span > 0 and first_mean > 0 and year_mean[last_y] > 0:
            feat["kp_q4_price_cagr"] = (
                (year_mean[last_y] / first_mean) ** (1.0 / span) - 1.0
            ) * 100.0

            # pp/yr slope of avg Q4 discount (positive = clearance deepening)
            feat["kp_q4_disc_slope"] = (
                year_avg_disc[last_y] - year_avg_disc[years_sorted[0]]
            ) / span

    # --- Group D: retail clearance detection ---
    if len(years_sorted) >= 2:
        prior_max_disc = [year_max_disc[y] for y in years_sorted[:-1]]
        feat["kp_q4_clearance_signal"] = (
            1.0 if year_max_disc[years_sorted[-1]] - max(prior_max_disc) > 10.0 else 0.0
        )

    if len(years_sorted) >= 3:
        years_arr = np.asarray(years_sorted, dtype=float)
        max_disc_arr = np.asarray([year_max_disc[y] for y in years_sorted], dtype=float)
        slope = float(np.polyfit(years_arr, max_disc_arr, 1)[0])
        feat["kp_q4_clearance_slope"] = slope

    return feat


def _compute_fba_features(
    fba_timeline: list[Any],
    rrp: float,
    cutoff_ym: str | None,
) -> dict[str, float]:
    """Group A feature: Q4 3P FBA floor vs RRP."""
    q4_by_year, _, _ = _bucket_by_quarter(fba_timeline, cutoff_ym)
    q4_all = _flatten_q4(q4_by_year)
    if len(q4_all) < 3:
        return {}
    floor = float(min(q4_all))
    return {"kp_q4_fba_floor_vs_rrp": (floor - rrp) / rrp * 100.0}


def _compute_fbm_features(
    fbm_timeline: list[Any],
    rrp: float,
    cutoff_ym: str | None,
) -> dict[str, float]:
    """Group A feature: Q4 FBM mean premium vs RRP."""
    q4_by_year, _, _ = _bucket_by_quarter(fbm_timeline, cutoff_ym)
    q4_all = _flatten_q4(q4_by_year)
    if len(q4_all) < 3:
        return {}
    mean_price = float(np.mean(q4_all))
    return {"kp_q4_fbm_premium_pct": (mean_price - rrp) / rrp * 100.0}


def engineer_q4_seasonal_features(
    df: pd.DataFrame,
    keepa_df: pd.DataFrame,
    *,
    cutoff_dates: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Attach Q4 seasonality features to `df` using Keepa timeline JSONs.

    Args:
        df: DataFrame with at least `set_number` and `rrp_usd_cents` columns.
        keepa_df: DataFrame with `set_number`, `amazon_price_json`,
            `new_3p_fba_json`, `new_3p_fbm_json` columns.
        cutoff_dates: optional `{set_number: "YYYY-MM"}` mapping — points with
            `ts[:7] > cutoff` are excluded. Prevents temporal leakage on
            retired sets.
    """
    result = df.copy()
    cutoffs = cutoff_dates or {}

    rrp_lookup = dict(
        zip(
            result["set_number"],
            pd.to_numeric(result["rrp_usd_cents"], errors="coerce").fillna(0),
        )
    )

    per_set: dict[str, dict[str, float]] = {}

    for _, row in keepa_df.iterrows():
        sn = row["set_number"]
        rrp = rrp_lookup.get(sn, 0.0)
        if rrp <= 0:
            continue
        cutoff = cutoffs.get(sn)

        amz = _parse_json(row.get("amazon_price_json"))
        fba = _parse_json(row.get("new_3p_fba_json"))
        fbm = _parse_json(row.get("new_3p_fbm_json"))

        bucket: dict[str, float] = {}
        if amz:
            bucket.update(_compute_amazon_features(amz, rrp, cutoff))
        if fba:
            bucket.update(_compute_fba_features(fba, rrp, cutoff))
        if fbm:
            bucket.update(_compute_fbm_features(fbm, rrp, cutoff))

        if bucket:
            per_set[sn] = bucket

    for feat in Q4_FEATURE_NAMES:
        result[feat] = result["set_number"].map(
            lambda sn, f=feat: per_set.get(sn, {}).get(f, np.nan)
        )

    coverage = {
        feat: float(pd.to_numeric(result[feat], errors="coerce").notna().mean())
        for feat in Q4_FEATURE_NAMES
    }
    logger.info(
        "Q4 seasonal features coverage: %s",
        ", ".join(f"{k}={v:.1%}" for k, v in coverage.items()),
    )

    return result
