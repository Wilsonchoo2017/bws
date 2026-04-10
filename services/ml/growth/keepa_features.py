"""Keepa+BL feature engineering for the growth model.

Extracts 26 features from Keepa timelines + factual metadata.
All Keepa features are cut at retired_date to prevent lookahead.
No BE pricing/growth data used -- only factual metadata (theme, pieces, RRP, etc).

From Experiment 31 feature selection (MI + redundancy + LOFO).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from config.ml import LICENSED_THEMES

logger = logging.getLogger(__name__)

# Themes where 3P premium is inflated but doesn't translate to BL appreciation
FALSE_POS_THEMES = frozenset({
    "Dots", "DUPLO", "Duplo", "Classic", "Seasonal",
    "Holiday & Event", "Trolls World Tour", "Vidiyo",
})

STRONG_THEMES = frozenset({
    "Star Wars", "Super Heroes", "Harry Potter", "Technic",
    "Creator", "Icons", "NINJAGO", "Ninjago",
})

# Final 26 features from Exp 31 Phase 12
KEEPA_BL_FEATURES: tuple[str, ...] = (
    # From LOFO-selected 20
    "3p_price_at_retire_vs_rrp",
    "3p_premium_x_minifig_density",
    "3p_above_rrp_pct",
    "amz_review_count",
    "keepa_n_price_points",
    "3p_max_premium_vs_rrp_pct",
    "amz_discount_trend",
    "amz_price_at_retire_vs_rrp",
    "amz_max_discount_pct",
    "price_per_part",
    "amz_price_cv",
    "price_tier",
    "minifig_value_ratio",
    "3p_above_rrp_duration_days",
    "amz_max_restock_delay_days",
    "3p_price_cv",
    "minifig_density",
    "amz_never_discounted",
    "has_exclusive_minifigs",
    "amz_rating",
    # Phase 12 additions
    "theme_false_pos",
    "theme_strong",
    "3p_prem_adj",
    "strong_theme_x_prem",
    "has_keepa_3p",
    "meta_demand_proxy",
)


def _parse_timeline(raw: object) -> list[list]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


def _parse_date(s: str | None) -> datetime | None:
    if not s or s == "None":
        return None
    try:
        return pd.to_datetime(s)
    except (ValueError, TypeError):
        return None


def _date_str_to_dt(s: str) -> datetime | None:
    try:
        return pd.to_datetime(s)
    except (ValueError, TypeError):
        return None


def _days_between(d1: str, d2: str) -> float | None:
    dt1 = _date_str_to_dt(d1)
    dt2 = _date_str_to_dt(d2)
    if dt1 and dt2:
        return (dt2 - dt1).days
    return None


def extract_keepa_features_for_set(
    keepa_row: pd.Series,
    rrp: float,
    retired_date: datetime | None,
    theme: str,
    parts_count: float,
    minifig_count: float,
    minifig_value_cents: float,
) -> dict:
    """Extract all Keepa+metadata features for a single set.

    All Keepa features are cut at retired_date to prevent lookahead.
    Returns a dict of feature_name -> value.
    """
    rec: dict[str, object] = {}

    if rrp <= 0:
        return rec

    retired_str = None
    retire_minus_6mo = None
    if retired_date and retired_date is not pd.NaT:
        try:
            retired_str = retired_date.strftime("%Y-%m-%d")
            retire_minus_6mo = retired_date - timedelta(days=182)
        except (ValueError, AttributeError):
            pass

    # Parse timelines
    amz_raw = _parse_timeline(keepa_row.get("amazon_price_json"))
    fba_raw = _parse_timeline(keepa_row.get("new_3p_fba_json"))

    # Cut at retired_date
    def _cut(tl: list[list]) -> list[list]:
        if not retired_str:
            return tl
        return [
            p for p in tl
            if len(p) >= 2 and isinstance(p[0], str) and p[0] <= retired_str
        ]

    amz = _cut(amz_raw)
    fba = _cut(fba_raw)

    amz_prices = [float(p[1]) for p in amz if p[1] is not None and p[1] > 0]
    fba_prices = [float(p[1]) for p in fba if p[1] is not None and p[1] > 0]

    # --- 3P FBA features ---
    if fba_prices and rrp > 0:
        rec["3p_above_rrp_pct"] = len([p for p in fba_prices if p > rrp]) / len(fba_prices) * 100
        rec["3p_max_premium_vs_rrp_pct"] = (max(fba_prices) - rrp) / rrp * 100

        fba_mean = float(np.mean(fba_prices))
        if fba_mean > 0:
            rec["3p_price_cv"] = float(np.std(fba_prices) / fba_mean)

        # Duration above RRP
        above_dates = [p[0] for p in fba if p[1] is not None and p[1] > rrp]
        if len(above_dates) >= 2:
            d = _days_between(above_dates[0], above_dates[-1])
            rec["3p_above_rrp_duration_days"] = d if d else 0

        # Last FBA price before retirement
        last_fba = None
        for p in reversed(fba):
            if p[1] is not None and p[1] > 0:
                last_fba = float(p[1])
                break
        if last_fba:
            rec["3p_price_at_retire_vs_rrp"] = last_fba / rrp

    # --- Amazon 1P features ---
    if amz_prices and rrp > 0:
        amz_mean = float(np.mean(amz_prices))
        rec["amz_max_discount_pct"] = (rrp - min(amz_prices)) / rrp * 100
        rec["amz_never_discounted"] = 1.0 if min(amz_prices) >= rrp * 0.98 else 0.0

        if len(amz_prices) >= 6:
            q = max(1, len(amz_prices) // 4)
            early = float(np.mean(amz_prices[:q]))
            late = float(np.mean(amz_prices[-q:]))
            if early > 0:
                rec["amz_discount_trend"] = (late - early) / early * 100

        last_amz = None
        for p in reversed(amz):
            if p[1] is not None and p[1] > 0:
                last_amz = float(p[1])
                break
        if last_amz:
            rec["amz_price_at_retire_vs_rrp"] = last_amz / rrp

        if amz_mean > 0:
            rec["amz_price_cv"] = float(np.std(amz_prices) / amz_mean)

    # --- Restock features ---
    oos_episodes: list[dict] = []
    in_stock_episodes: list[dict] = []
    current_ep: dict | None = None

    for point in amz:
        is_oos = point[1] is None or (point[1] is not None and point[1] <= 0)
        if current_ep is None:
            current_ep = {"start": point[0], "end": point[0], "oos": is_oos}
        elif is_oos == current_ep["oos"]:
            current_ep["end"] = point[0]
        else:
            (oos_episodes if current_ep["oos"] else in_stock_episodes).append(current_ep)
            current_ep = {"start": point[0], "end": point[0], "oos": is_oos}
    if current_ep:
        (oos_episodes if current_ep["oos"] else in_stock_episodes).append(current_ep)

    restock_delays: list[float] = []
    for i, ep in enumerate(oos_episodes):
        oos_end_dt = _date_str_to_dt(ep["end"])
        if not oos_end_dt:
            continue
        for ist_ep in in_stock_episodes:
            ist_start = _date_str_to_dt(ist_ep["start"])
            if ist_start and ist_start > oos_end_dt:
                delay = (ist_start - _date_str_to_dt(ep["start"])).days
                if delay > 0:
                    restock_delays.append(float(delay))
                break

    rec["amz_max_restock_delay_days"] = float(max(restock_delays)) if restock_delays else 0.0

    # --- Demand proxy ---
    if pd.notna(keepa_row.get("kp_reviews")):
        rec["amz_review_count"] = float(keepa_row["kp_reviews"])
    if pd.notna(keepa_row.get("kp_rating")):
        rec["amz_rating"] = float(keepa_row["kp_rating"])

    # --- Data quality ---
    rec["keepa_n_price_points"] = float(len(amz))
    rec["has_keepa_3p"] = 1.0 if len(fba) > 0 else 0.0

    # --- Metadata features ---
    rec["price_per_part"] = rrp / parts_count if parts_count > 0 else 0
    rec["minifig_density"] = minifig_count / parts_count * 100 if parts_count > 0 else 0
    rec["minifig_value_ratio"] = minifig_value_cents / rrp if rrp > 0 and minifig_value_cents > 0 else 0
    rec["has_exclusive_minifigs"] = 0.0  # will be filled from metadata
    rec["price_tier"] = _price_tier(rrp)

    # --- Theme features ---
    rec["theme_false_pos"] = 1.0 if theme in FALSE_POS_THEMES else 0.0
    rec["theme_strong"] = 1.0 if theme in STRONG_THEMES else 0.0

    # --- Interactions ---
    prem_3p = rec.get("3p_above_rrp_pct", 0) or 0
    avg_prem = rec.get("3p_max_premium_vs_rrp_pct", 0) or 0
    rec["3p_prem_adj"] = prem_3p * (0.5 if theme in FALSE_POS_THEMES else 1.0)
    rec["strong_theme_x_prem"] = rec["theme_strong"] * prem_3p
    rec["3p_premium_x_minifig_density"] = avg_prem * rec["minifig_density"]
    rec["meta_demand_proxy"] = (
        np.log1p(rec.get("amz_review_count", 0) or 0)
        * rec["minifig_value_ratio"]
    )

    return rec


def _price_tier(rrp_cents: float) -> float:
    """Assign price tier (1-8) from RRP in USD cents."""
    usd = rrp_cents / 100
    if usd <= 15:
        return 1.0
    if usd <= 30:
        return 2.0
    if usd <= 50:
        return 3.0
    if usd <= 80:
        return 4.0
    if usd <= 120:
        return 5.0
    if usd <= 200:
        return 6.0
    if usd <= 500:
        return 7.0
    return 8.0


def engineer_keepa_bl_features(
    base_df: pd.DataFrame,
    keepa_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build feature matrix for all sets.

    Args:
        base_df: Metadata with set_number, theme, parts_count, minifig_count,
                 rrp_usd_cents, minifig_value_cents, exclusive_minifigs,
                 retired_date
        keepa_df: Keepa timelines with set_number, amazon_price_json,
                  new_3p_fba_json, kp_reviews, kp_rating

    Returns:
        DataFrame with set_number + all KEEPA_BL_FEATURES columns.
    """
    keepa_lookup: dict[str, pd.Series] = {}
    for _, row in keepa_df.iterrows():
        keepa_lookup[str(row["set_number"])] = row

    rows: list[dict] = []
    for _, meta in base_df.iterrows():
        sn = str(meta["set_number"])
        rrp = float(meta.get("rrp_usd_cents", 0) or 0)
        if rrp <= 0:
            continue

        retired_date = _parse_date(str(meta.get("retired_date", "")))
        theme = str(meta.get("theme", ""))
        parts = float(meta.get("parts_count", 0) or 0)
        mfigs = float(meta.get("minifig_count", 0) or 0)
        mfig_val = float(meta.get("minifig_value_cents", 0) or 0)
        excl = meta.get("exclusive_minifigs")

        kp = keepa_lookup.get(sn)
        if kp is not None:
            rec = extract_keepa_features_for_set(
                kp, rrp, retired_date, theme, parts, mfigs, mfig_val,
            )
        else:
            # No Keepa data: metadata-only features
            rec = {
                "price_per_part": rrp / parts if parts > 0 else 0,
                "minifig_density": mfigs / parts * 100 if parts > 0 else 0,
                "minifig_value_ratio": mfig_val / rrp if mfig_val > 0 else 0,
                "price_tier": _price_tier(rrp),
                "theme_false_pos": 1.0 if theme in FALSE_POS_THEMES else 0.0,
                "theme_strong": 1.0 if theme in STRONG_THEMES else 0.0,
                "has_keepa_3p": 0.0,
                "keepa_n_price_points": 0.0,
                "amz_max_restock_delay_days": 0.0,
                "amz_never_discounted": 0.0,
                "3p_prem_adj": 0.0,
                "strong_theme_x_prem": 0.0,
                "3p_premium_x_minifig_density": 0.0,
                "meta_demand_proxy": 0.0,
            }

        # Override exclusive_minifigs from metadata
        if pd.notna(excl) and excl:
            rec["has_exclusive_minifigs"] = 1.0
        else:
            rec["has_exclusive_minifigs"] = 0.0

        rec["set_number"] = sn
        rows.append(rec)

    df = pd.DataFrame(rows)

    # Ensure all feature columns exist
    for col in KEEPA_BL_FEATURES:
        if col not in df.columns:
            df[col] = 0.0

    return df
