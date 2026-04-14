"""Keepa+BL feature engineering for the growth model.

Extracts 36 features from Keepa timelines + factual metadata.
All Keepa features are cut at retired_date to prevent lookahead.
No BE pricing/growth data used -- only factual metadata (theme, pieces, RRP, etc).

From Experiment 31 feature selection (MI + redundancy + LOFO),
Exp 33 theme-level Keepa aggregates (LOO Bayesian encoded),
Exp 34 new feature groups (regional RRP, buy box, interactions),
and Exp 35 phase-aware, composite, and relative signal features.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from config.ml import LICENSED_THEMES
from services.ml.encodings import (
    compute_group_stats,
    group_mean_encode,
    loo_bayesian_encode,
)

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

# 7 Google Trends features (Exp 32: +0.017 AUC on P(avoid), +0.006 on P(great_buy))
GT_FEATURES: tuple[str, ...] = (
    "gt_peak_value",
    "gt_avg_value",
    "gt_months_active",
    "gt_decay_rate",
    "gt_pre_retire_avg",
    "gt_lifetime_months",
    "gt_peak_recency",
)

# 37 features: 26 from Exp 31 Phase 12 + 2 theme aggregates from Exp 33
#              + 4 from Exp 34 (regional RRP, buy box, interactions)
#              + 4 from Exp 35 (phase-aware, composite, relative signal)
#              + 1 from Exp 36 (depth × frequency discount composite)
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
    # Exp 33: Theme-level Keepa aggregates (LOO Bayesian encoded)
    "theme_avg_retire_price",
    "theme_growth_x_prem",
    # Exp 34: Regional RRP, buy box, interactions
    "rrp_uk_premium",
    "rrp_regional_cv",
    "buybox_premium_avg",
    "amz_fba_spread_at_retire",
    # Exp 35: Phase-aware, composite, relative signal
    "fba_prem_late_vs_early",
    "scarcity_pressure",
    "theme_quality_x_premium",
    "buybox_vs_theme",
    # Exp 36: depth × frequency composite
    "amz_discount_depth_x_freq",
)

# Classifier-specific features: base 36 + 7 GT = 43 (Exp 32-35)
CLASSIFIER_FEATURES: tuple[str, ...] = KEEPA_BL_FEATURES + GT_FEATURES


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

        # Depth × frequency composite (Exp 36): avg discount magnitude across
        # in-stock days × % of in-stock days discounted >5% off RRP. Captures
        # demand weakness that the binary amz_never_discounted erases.
        if len(amz_prices) >= 3:
            n_below = sum(1 for p in amz_prices if p < rrp * 0.95)
            pct_below = n_below / len(amz_prices) * 100
            avg_disc = float(np.mean([
                max(0.0, (rrp - p) / rrp * 100) for p in amz_prices
            ]))
            rec["amz_discount_depth_x_freq"] = avg_disc * pct_below

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

    # --- Buy box features (Exp 34) ---
    bb_raw = _parse_timeline(keepa_row.get("buy_box_json"))
    bb = _cut(bb_raw)
    bb_prices = [float(p[1]) for p in bb if p[1] is not None and p[1] > 0]
    if bb_prices and rrp > 0:
        rec["buybox_premium_avg"] = float(np.mean(bb_prices)) / rrp

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

    # Exp 34: 1P vs 3P spread at retirement
    amz_ret = rec.get("amz_price_at_retire_vs_rrp", 0) or 0
    fba_ret = rec.get("3p_price_at_retire_vs_rrp", 0) or 0
    rec["amz_fba_spread_at_retire"] = amz_ret / fba_ret if fba_ret > 0 else 0.0

    # Exp 35: Phase-aware -- 3P premium late vs early half
    if len(fba_prices) >= 6:
        half = len(fba_prices) // 2
        early_fba_mean = float(np.mean(fba_prices[:half]))
        late_fba_mean = float(np.mean(fba_prices[half:]))
        if early_fba_mean > 0:
            rec["fba_prem_late_vs_early"] = late_fba_mean / early_fba_mean

    # Exp 35: Composite -- scarcity_pressure = buybox_premium * (1 - spread)
    bb_prem = rec.get("buybox_premium_avg", 0) or 0
    spread_val = rec.get("amz_fba_spread_at_retire", 0) or 0
    rec["scarcity_pressure"] = bb_prem * (1 - spread_val)

    return rec


# Approximate exchange rates for regional RRP normalization (Exp 34).
# These convert foreign-currency cents to USD-equivalent cents.
_FX_TO_USD = {"gbp": 1.27, "eur": 1.08, "cad": 0.74, "aud": 0.66}


def _regional_cv(usd: float, gbp: float, eur: float, cad: float, aud: float) -> float:
    """CV of exchange-rate-normalized regional prices (Exp 34)."""
    vals = [usd]  # USD is already in USD cents
    if gbp > 0:
        vals.append(gbp * _FX_TO_USD["gbp"])
    if eur > 0:
        vals.append(eur * _FX_TO_USD["eur"])
    if cad > 0:
        vals.append(cad * _FX_TO_USD["cad"])
    if aud > 0:
        vals.append(aud * _FX_TO_USD["aud"])
    if len(vals) < 2:
        return 0.0
    arr = np.array(vals, dtype=float)
    mean = arr.mean()
    return float(arr.std() / mean) if mean > 0 else 0.0


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
    *,
    theme_stats: dict | None = None,
) -> pd.DataFrame:
    """Build feature matrix for all sets.

    Args:
        base_df: Metadata with set_number, theme, parts_count, minifig_count,
                 rrp_usd_cents, minifig_value_cents, exclusive_minifigs,
                 retired_date
        keepa_df: Keepa timelines with set_number, amazon_price_json,
                  new_3p_fba_json, kp_reviews, kp_rating
        theme_stats: Pre-computed theme statistics for inference mode.
                     If None, theme aggregate features are left at 0
                     (training pipeline encodes them separately).

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

        # Exp 34: Regional RRP features
        gbp = float(meta.get("rrp_gbp_cents", 0) or 0)
        eur = float(meta.get("rrp_eur_cents", 0) or 0)
        cad = float(meta.get("rrp_cad_cents", 0) or 0)
        aud = float(meta.get("rrp_aud_cents", 0) or 0)

        if gbp > 0:
            rec["_gbp_usd_ratio"] = gbp / rrp  # temp, used for rrp_uk_premium later
        rec["rrp_regional_cv"] = _regional_cv(rrp, gbp, eur, cad, aud)

        rec["set_number"] = sn
        rec["theme"] = theme
        rows.append(rec)

    df = pd.DataFrame(rows)

    # Exp 34: rrp_uk_premium = gbp/usd ratio - median
    # Median comes from theme_stats["regional_stats"] (training) or computed from df
    median_gbp_usd = None
    if theme_stats and "regional_stats" in theme_stats:
        median_gbp_usd = theme_stats["regional_stats"].get("median_gbp_usd_ratio")
    if median_gbp_usd is None and "_gbp_usd_ratio" in df.columns:
        valid = df["_gbp_usd_ratio"].dropna()
        median_gbp_usd = float(valid.median()) if len(valid) > 10 else 0.876
    if "_gbp_usd_ratio" in df.columns:
        df["rrp_uk_premium"] = df["_gbp_usd_ratio"] - (median_gbp_usd or 0.876)
        df = df.drop(columns=["_gbp_usd_ratio"])

    # Ensure all feature columns exist
    for col in KEEPA_BL_FEATURES:
        if col not in df.columns:
            df[col] = 0.0

    # Inference mode: encode theme features from saved stats
    if theme_stats is not None:
        df = encode_theme_keepa_features(df, theme_stats=theme_stats)

    return df


# Source features for theme-level aggregation (Exp 33).
# Keys = new theme feature name, values = per-set source feature.
# Both computed as theme stats; theme_avg_3p_premium used only for the
# interaction feature (theme_growth_x_prem) and not exposed directly.
THEME_SOURCE_FEATURES: dict[str, str] = {
    "theme_avg_retire_price": "3p_price_at_retire_vs_rrp",
    "theme_avg_3p_premium": "3p_above_rrp_pct",
    # Exp 35: theme-level buybox for relative signal features
    "theme_avg_buybox": "buybox_premium_avg",
}


def compute_regional_stats(base_df: pd.DataFrame) -> dict:
    """Compute regional RRP statistics for persistence (Exp 34).

    Returns dict with median GBP/USD ratio for rrp_uk_premium computation.
    """
    usd = base_df["rrp_usd_cents"].astype(float)
    gbp = base_df.get("rrp_gbp_cents", pd.Series(dtype=float)).astype(float)
    valid = (usd > 0) & (gbp > 0)
    if valid.sum() > 10:
        ratios = gbp[valid] / usd[valid]
        return {"median_gbp_usd_ratio": float(ratios.median())}
    return {"median_gbp_usd_ratio": 0.876}


def compute_theme_keepa_stats(df: pd.DataFrame) -> dict:
    """Compute theme-level Keepa feature statistics for persistence.

    Groups the per-set Keepa features (already cut at retired_date) by theme
    and computes group stats for each source feature.

    Args:
        df: Feature DataFrame with theme column and source features.

    Returns:
        Dict with per-source-feature group stats, suitable for serialization.
    """
    result: dict[str, dict] = {}
    for theme_feat, source_feat in THEME_SOURCE_FEATURES.items():
        source_vals = df[source_feat].fillna(0).astype(float)
        stats = compute_group_stats(df, "theme", source_vals)
        result[theme_feat] = stats
    return result


def encode_theme_keepa_features(
    df: pd.DataFrame,
    *,
    theme_stats: dict | None = None,
    training: bool = False,
) -> pd.DataFrame:
    """Encode theme-level Keepa feature aggregates.

    Training mode (training=True):
        Uses LOO Bayesian encoding (excludes each set's own value).
        If theme_stats is None, computes from df first.
    Inference mode (training=False, theme_stats provided):
        Uses saved stats with full mean encoding (no LOO).

    Args:
        df: Feature DataFrame with theme column and source features.
        theme_stats: Pre-computed stats from compute_theme_keepa_stats().
        training: If True, use LOO encoding even when theme_stats provided.

    Returns:
        DataFrame with theme aggregate features added.
    """
    if theme_stats is None:
        theme_stats = compute_theme_keepa_stats(df)
        training = True

    for theme_feat, source_feat in THEME_SOURCE_FEATURES.items():
        stats = theme_stats[theme_feat]
        if training:
            source_vals = df[source_feat].fillna(0).astype(float)
            df[theme_feat] = loo_bayesian_encode(
                df["theme"], source_vals, stats, alpha=20,
            )
        else:
            df[theme_feat] = group_mean_encode(
                df["theme"], stats, alpha=20,
            )

    # Interaction: theme premium tendency * individual set premium
    df["theme_growth_x_prem"] = (
        df["theme_avg_3p_premium"] * df["3p_above_rrp_pct"].fillna(0)
    )

    # Exp 35: buybox_vs_theme = set's buybox - theme average buybox
    df["buybox_vs_theme"] = (
        df["buybox_premium_avg"].fillna(0) - df["theme_avg_buybox"].fillna(0)
    )

    # Exp 35: theme_quality_x_premium = theme retire price * excess 3P premium
    # excess 3P premium = set's 3p_above_rrp_pct - theme average 3p_above_rrp_pct
    excess_prem = df["3p_above_rrp_pct"].fillna(0) - df["theme_avg_3p_premium"].fillna(0)
    df["theme_quality_x_premium"] = df["theme_avg_retire_price"].fillna(0) * excess_prem

    # Drop intermediate columns not in KEEPA_BL_FEATURES
    for _int_col in ("theme_avg_3p_premium", "theme_avg_buybox"):
        if _int_col not in KEEPA_BL_FEATURES:
            df = df.drop(columns=[_int_col], errors="ignore")

    return df


def engineer_gt_features(
    gt_df: pd.DataFrame,
    base_df: pd.DataFrame,
) -> pd.DataFrame:
    """Engineer Google Trends features per set.

    At training time: timelines are cut at retired_date (no lookahead).
    At inference time: sets without retired_date use full timeline
    (these are active sets we're evaluating for purchase).

    Args:
        gt_df: Google Trends data with set_number, interest_json.
        base_df: Metadata with set_number, retired_date.

    Returns:
        DataFrame with set_number + GT_FEATURES columns.
    """
    retire_map: dict[str, pd.Timestamp] = {}
    for _, row in base_df.iterrows():
        sn = str(row["set_number"])
        rd = _parse_date(str(row.get("retired_date", "")))
        if rd is not None:
            retire_map[sn] = rd

    records: list[dict] = []
    for _, row in gt_df.iterrows():
        sn = str(row["set_number"])
        retire_dt = retire_map.get(sn)

        tl = _parse_timeline(row.get("interest_json"))
        if not tl:
            continue

        dates: list[datetime] = []
        values: list[float] = []
        for entry in tl:
            if len(entry) >= 2:
                dt = _date_str_to_dt(str(entry[0]))
                if dt is not None:
                    try:
                        values.append(float(entry[1]))
                        dates.append(dt)
                    except (ValueError, TypeError):
                        continue

        if not dates:
            continue

        vals = np.array(values, dtype=float)

        # Cut at retired_date when available (training); use full timeline otherwise (inference)
        if retire_dt is not None:
            pre_mask = np.array([d <= retire_dt for d in dates])
            pre_dates = [d for d, m in zip(dates, pre_mask) if m]
            pre_vals = vals[pre_mask] if pre_mask.any() else np.array([0.0])

            pre_12m_mask = np.array([
                d > retire_dt - timedelta(days=365) and d <= retire_dt
                for d in dates
            ])
            pre_12m = vals[pre_12m_mask] if pre_12m_mask.any() else np.array([0.0])
        else:
            # Inference: use full timeline as "pre" (set hasn't retired yet)
            pre_vals = vals
            pre_dates = dates
            pre_12m = vals[-12:] if len(vals) >= 12 else vals

        if len(pre_vals) == 0 or pre_vals.max() == 0:
            continue

        gt_peak = float(pre_vals.max())
        gt_avg = float(pre_vals.mean())
        gt_months_active = int((pre_vals > 0).sum())
        gt_lifetime_months = len(pre_vals)

        # Decay rate: linear slope of interest over time
        gt_decay = 0.0
        if len(pre_vals) >= 6 and pre_vals.std() > 0:
            x = np.arange(len(pre_vals), dtype=float)
            gt_decay = float(np.polyfit(x, pre_vals, 1)[0])

        pre_avg = float(pre_12m.mean()) if len(pre_12m) > 0 else 0.0

        # Peak recency: months between peak and cutoff date
        gt_peak_recency = 0.0
        if pre_dates:
            peak_idx = int(pre_vals.argmax())
            peak_date = pre_dates[peak_idx]
            cutoff = retire_dt if retire_dt is not None else dates[-1]
            gt_peak_recency = max(0.0, (cutoff - peak_date).days / 30.0)

        records.append({
            "set_number": sn,
            "gt_peak_value": gt_peak,
            "gt_avg_value": gt_avg,
            "gt_months_active": gt_months_active,
            "gt_decay_rate": gt_decay,
            "gt_pre_retire_avg": pre_avg,
            "gt_lifetime_months": gt_lifetime_months,
            "gt_peak_recency": gt_peak_recency,
        })

    result = pd.DataFrame(records)
    if result.empty:
        result = pd.DataFrame(columns=["set_number"] + list(GT_FEATURES))
    return result
