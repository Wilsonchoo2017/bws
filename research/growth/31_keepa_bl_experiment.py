"""Experiment 31: Keepa + BrickLink Pure Signal Experiment.

Strips back to Keepa + BrickLink for pricing/market signals.
BE used ONLY for factual metadata (theme, pieces, minifigs, RRP, etc).
BE pricing/growth data is FORBIDDEN.

Features: Amazon OOS patterns, 3P price dynamics, restock behavior,
metadata interactions. Targets: BL post-retirement prices.

Run: python -m research.growth.31_keepa_bl_experiment
"""
from __future__ import annotations

import json
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 70)
print("EXPERIMENT 31: KEEPA + BRICKLINK PURE SIGNAL")
print("No BE pricing/growth -- only factual metadata + market signals")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from sqlalchemy import text

engine = get_engine()

# ============================================================================
# PHASE 1: DATA LOADING
# ============================================================================
print("\n--- Phase 1: Data Loading ---")

with engine.connect() as conn:
    # 1a. Base metadata (BE factual only -- NO pricing/growth columns)
    # Use retired_date from BE OR approximate from lego_items.year_retired
    base_df = pd.read_sql(text("""
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            be.subtheme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            be.rrp_usd_cents,
            be.rating_value,
            be.review_count,
            be.exclusive_minifigs,
            be.minifig_value_cents,
            be.designer,
            COALESCE(li.year_released, be.year_released) AS year_released,
            CAST(COALESCE(
                li.retired_date,
                be.retired_date,
                CASE WHEN li.year_retired IS NOT NULL
                     THEN (li.year_retired::TEXT || '-07-01')::DATE
                END
            ) AS TEXT) AS retired_date,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE (be.retired_date IS NOT NULL OR li.year_retired IS NOT NULL)
          AND be.rrp_usd_cents > 0
    """), conn)

    # 1b. Keepa timelines
    keepa_df = pd.read_sql(text("""
        SELECT set_number, amazon_price_json, new_3p_fba_json,
               new_3p_fbm_json, buy_box_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) sub
    """), conn)

    # 1c. BrickLink price history (current snapshot)
    bl_price_df = pd.read_sql(text("""
        SELECT
            SPLIT_PART(item_id, '-', 1) AS set_number,
            six_month_new, current_new
        FROM (
            SELECT DISTINCT ON (item_id) *
            FROM bricklink_price_history
            ORDER BY item_id, scraped_at DESC
        ) sub
    """), conn)

    # 1d. BrickLink monthly sales (for targets)
    bl_monthly_df = pd.read_sql(text("""
        SELECT set_number, year, month, condition,
               times_sold, total_quantity, avg_price, min_price, max_price, currency
        FROM bricklink_monthly_sales
        WHERE condition = 'new' AND avg_price > 0
        ORDER BY set_number, year, month
    """), conn)

print(f"Base metadata: {len(base_df)} sets with retired_date")
print(f"Keepa timelines: {len(keepa_df)} sets")
print(f"BL price history: {len(bl_price_df)} sets")
print(f"BL monthly sales: {len(bl_monthly_df)} rows")

# Merge keepa into base
merged = base_df.merge(keepa_df, on="set_number", how="inner")
print(f"Base + Keepa overlap: {len(merged)} sets")


# ============================================================================
# PHASE 2: FEATURE EXTRACTION
# ============================================================================
print("\n--- Phase 2: Feature Extraction ---")


def parse_timeline(raw: object) -> list[list]:
    """Parse a JSON timeline into list of [date_str, value] points."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


def parse_date(s: str | None) -> datetime | None:
    """Parse a date string to datetime."""
    if not s or s == "None":
        return None
    try:
        return pd.to_datetime(s)
    except (ValueError, TypeError):
        return None


def date_str_to_dt(s: str) -> datetime | None:
    """Convert timeline date string to datetime."""
    try:
        return pd.to_datetime(s)
    except (ValueError, TypeError):
        return None


def days_between_dates(d1: str, d2: str) -> float | None:
    """Days between two date strings."""
    dt1 = date_str_to_dt(d1)
    dt2 = date_str_to_dt(d2)
    if dt1 and dt2:
        return (dt2 - dt1).days
    return None


def extract_features_for_set(row: pd.Series) -> dict:
    """Extract all features for a single set. Core feature extraction function.

    All Keepa features are cut at retired_date to prevent lookahead bias.
    """
    sn = row["set_number"]
    rrp = float(row["rrp_usd_cents"]) if pd.notna(row.get("rrp_usd_cents")) else 0
    retired_date = parse_date(row.get("retired_date"))

    rec: dict[str, object] = {"set_number": sn}

    if rrp <= 0 or retired_date is None:
        return rec

    retired_str = retired_date.strftime("%Y-%m-%d")
    retire_minus_6mo = retired_date - timedelta(days=182)
    retire_minus_12mo = retired_date - timedelta(days=365)

    # Parse all timelines
    amz_raw = parse_timeline(row.get("amazon_price_json"))
    fba_raw = parse_timeline(row.get("new_3p_fba_json"))
    fbm_raw = parse_timeline(row.get("new_3p_fbm_json"))
    bb_raw = parse_timeline(row.get("buy_box_json"))

    # Cut at retired_date (CRITICAL: prevents lookahead)
    def cut_timeline(tl: list[list]) -> list[list]:
        return [
            p for p in tl
            if len(p) >= 2 and isinstance(p[0], str) and p[0] <= retired_str
        ]

    amz = cut_timeline(amz_raw)
    fba = cut_timeline(fba_raw)
    fbm = cut_timeline(fbm_raw)
    bb = cut_timeline(bb_raw)

    if len(amz) < 3:
        return rec

    # Build date-indexed lookups for alignment
    amz_dates = [p[0] for p in amz]
    amz_values = [p[1] for p in amz]
    amz_prices = [float(p[1]) for p in amz if p[1] is not None and p[1] > 0]

    if not amz_prices:
        return rec

    # ----------------------------------------------------------------
    # A. Amazon Stock-Out Features
    # ----------------------------------------------------------------
    oos_episodes: list[dict] = []
    in_stock_episodes: list[dict] = []
    current_episode: dict | None = None

    for point in amz:
        date_str = point[0]
        val = point[1]
        is_oos = val is None or val <= 0

        if current_episode is None:
            current_episode = {"start": date_str, "end": date_str, "oos": is_oos}
        elif is_oos == current_episode["oos"]:
            current_episode["end"] = date_str
        else:
            if current_episode["oos"]:
                oos_episodes.append(current_episode)
            else:
                in_stock_episodes.append(current_episode)
            current_episode = {"start": date_str, "end": date_str, "oos": is_oos}

    if current_episode is not None:
        if current_episode["oos"]:
            oos_episodes.append(current_episode)
        else:
            in_stock_episodes.append(current_episode)

    total_points = len(amz)
    oos_points = sum(1 for p in amz if p[1] is None or (p[1] is not None and p[1] <= 0))

    rec["amz_oos_event_count"] = float(len(oos_episodes))
    rec["amz_oos_pct"] = oos_points / total_points * 100 if total_points > 0 else 0

    # Episode durations in days
    oos_durations: list[float] = []
    for ep in oos_episodes:
        d = days_between_dates(ep["start"], ep["end"])
        if d is not None and d >= 0:
            oos_durations.append(max(d, 1.0))  # at least 1 day

    if oos_durations:
        rec["amz_longest_oos_days"] = max(oos_durations)
        rec["amz_avg_oos_duration_days"] = float(np.mean(oos_durations))
    else:
        rec["amz_longest_oos_days"] = 0.0
        rec["amz_avg_oos_duration_days"] = 0.0

    # OOS in last 6/12 months before retirement
    last_6mo_points = [
        p for p in amz
        if isinstance(p[0], str) and p[0] >= retire_minus_6mo.strftime("%Y-%m-%d")
    ]
    last_12mo_points = [
        p for p in amz
        if isinstance(p[0], str) and p[0] >= retire_minus_12mo.strftime("%Y-%m-%d")
    ]

    if last_6mo_points:
        oos_6mo = sum(1 for p in last_6mo_points if p[1] is None or (p[1] is not None and p[1] <= 0))
        rec["amz_oos_in_last_6mo"] = 1.0 if oos_6mo > 0 else 0.0
        rec["amz_oos_pct_last_6mo"] = oos_6mo / len(last_6mo_points) * 100
    if last_12mo_points:
        oos_12mo = sum(1 for p in last_12mo_points if p[1] is None or (p[1] is not None and p[1] <= 0))
        rec["amz_oos_pct_last_12mo"] = oos_12mo / len(last_12mo_points) * 100

    # First OOS timing relative to retirement
    if oos_episodes:
        first_oos_dt = date_str_to_dt(oos_episodes[0]["start"])
        if first_oos_dt and retired_date:
            rec["amz_first_oos_months_before_retire"] = (retired_date - first_oos_dt).days / 30.44

        last_oos = oos_episodes[-1]
        last_oos_end_dt = date_str_to_dt(last_oos["end"])
        if last_oos_end_dt and retired_date:
            rec["amz_final_oos_to_retire_days"] = (retired_date - last_oos_end_dt).days

    # ----------------------------------------------------------------
    # B. Restock Behavior
    # ----------------------------------------------------------------
    restock_delays: list[float] = []
    restocked_after_final = False

    for i, ep in enumerate(oos_episodes):
        # Find the next in-stock episode after this OOS
        oos_end_dt = date_str_to_dt(ep["end"])
        if oos_end_dt is None:
            continue
        # Check if there's any in-stock point after this OOS end
        for ist_ep in in_stock_episodes:
            ist_start_dt = date_str_to_dt(ist_ep["start"])
            if ist_start_dt and ist_start_dt > oos_end_dt:
                delay = (ist_start_dt - date_str_to_dt(ep["start"])).days
                if delay > 0:
                    restock_delays.append(float(delay))
                if i == len(oos_episodes) - 1:
                    restocked_after_final = True
                break

    rec["amz_restock_count"] = float(len(restock_delays))

    if restock_delays:
        rec["amz_avg_restock_delay_days"] = float(np.mean(restock_delays))
        rec["amz_max_restock_delay_days"] = float(max(restock_delays))
        if len(restock_delays) >= 2:
            mid = len(restock_delays) // 2
            early = float(np.mean(restock_delays[:mid]))
            late = float(np.mean(restock_delays[mid:]))
            rec["amz_restock_delay_trend"] = (late - early) / early if early > 0 else 0
    else:
        rec["amz_avg_restock_delay_days"] = 0.0
        rec["amz_max_restock_delay_days"] = 0.0

    rec["amz_restocked_after_final_oos"] = 1.0 if restocked_after_final else 0.0

    # ----------------------------------------------------------------
    # C. 3P Price Response to OOS
    # ----------------------------------------------------------------
    # Build date->price lookups for FBA
    fba_lookup: dict[str, float] = {}
    for p in fba:
        if p[1] is not None and p[1] > 0:
            fba_lookup[p[0]] = float(p[1])

    bb_lookup: dict[str, float] = {}
    for p in bb:
        if p[1] is not None and p[1] > 0:
            bb_lookup[p[0]] = float(p[1])

    fbm_lookup: dict[str, float] = {}
    for p in fbm:
        if p[1] is not None and p[1] > 0:
            fbm_lookup[p[0]] = float(p[1])

    # Compute 3P prices during OOS vs in-stock periods
    fba_during_oos: list[float] = []
    fba_during_instock: list[float] = []
    bb_during_oos: list[float] = []

    for point in amz:
        date_str = point[0]
        is_oos = point[1] is None or (point[1] is not None and point[1] <= 0)

        fba_price = fba_lookup.get(date_str)
        bb_price = bb_lookup.get(date_str)

        if fba_price:
            if is_oos:
                fba_during_oos.append(fba_price)
            else:
                fba_during_instock.append(fba_price)
        if bb_price and is_oos:
            bb_during_oos.append(bb_price)

    if fba_during_oos and fba_during_instock:
        avg_oos = float(np.mean(fba_during_oos))
        avg_ist = float(np.mean(fba_during_instock))
        if avg_ist > 0:
            rec["3p_price_spike_at_oos_pct"] = (avg_oos - avg_ist) / avg_ist * 100
        rec["3p_max_spike_at_oos_pct"] = (max(fba_during_oos) - avg_ist) / avg_ist * 100 if avg_ist > 0 else None

    if fba_during_oos and rrp > 0:
        rec["3p_price_during_oos_vs_rrp"] = float(np.mean(fba_during_oos)) / rrp

    # 3P recovery after restock
    recovery_drops: list[float] = []
    for ep in oos_episodes:
        oos_end_dt = date_str_to_dt(ep["end"])
        if not oos_end_dt:
            continue
        oos_end_str = ep["end"]
        # Avg FBA price during this OOS episode
        oos_fba = [
            fba_lookup[d] for d in fba_lookup
            if ep["start"] <= d <= ep["end"]
        ]
        # Avg FBA price in 30 days after OOS ends
        post_oos_fba = [
            fba_lookup[d] for d in fba_lookup
            if d > oos_end_str and days_between_dates(oos_end_str, d) is not None
            and 0 < (days_between_dates(oos_end_str, d) or 999) <= 30
        ]
        if oos_fba and post_oos_fba:
            drop_pct = (float(np.mean(post_oos_fba)) - float(np.mean(oos_fba))) / float(np.mean(oos_fba)) * 100
            recovery_drops.append(drop_pct)

    if recovery_drops:
        rec["3p_price_recovery_after_restock"] = float(np.mean(recovery_drops))

    if bb_during_oos and rrp > 0:
        rec["bb_premium_during_oos_pct"] = (float(np.mean(bb_during_oos)) - rrp) / rrp * 100

    if bb_during_oos and fba_during_oos:
        rec["bb_vs_3p_spread_oos"] = (float(np.mean(bb_during_oos)) - float(np.mean(fba_during_oos))) / rrp * 100 if rrp > 0 else None

    # FBM vs FBA during OOS
    fbm_during_oos: list[float] = []
    for point in amz:
        if point[1] is None or (point[1] is not None and point[1] <= 0):
            fbm_price = fbm_lookup.get(point[0])
            if fbm_price:
                fbm_during_oos.append(fbm_price)

    if fbm_during_oos and fba_during_oos:
        rec["3p_fbm_vs_fba_spread_oos"] = (float(np.mean(fbm_during_oos)) - float(np.mean(fba_during_oos))) / rrp * 100 if rrp > 0 else None

    # ----------------------------------------------------------------
    # D. 3P Price Trend
    # ----------------------------------------------------------------
    fba_prices = [float(p[1]) for p in fba if p[1] is not None and p[1] > 0]

    if fba_prices and rrp > 0:
        above_rrp = [p for p in fba_prices if p > rrp]
        rec["3p_above_rrp_pct"] = len(above_rrp) / len(fba_prices) * 100

        # Duration in days above RRP
        above_rrp_dates = [p[0] for p in fba if p[1] is not None and p[1] > rrp]
        if len(above_rrp_dates) >= 2:
            d_total = days_between_dates(above_rrp_dates[0], above_rrp_dates[-1])
            rec["3p_above_rrp_duration_days"] = d_total if d_total else 0

        # Longest streak above RRP
        streak = 0
        max_streak = 0
        for p in fba:
            if p[1] is not None and p[1] > rrp:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        # Convert to approximate days (points are ~weekly)
        rec["3p_above_rrp_longest_streak"] = float(max_streak)

        rec["3p_avg_premium_vs_rrp_pct"] = (float(np.mean(fba_prices)) - rrp) / rrp * 100
        rec["3p_max_premium_vs_rrp_pct"] = (max(fba_prices) - rrp) / rrp * 100

        fba_min = min(fba_prices)
        rec["3p_floor_above_rrp"] = 1.0 if fba_min > rrp else 0.0
        rec["3p_floor_vs_rrp_ratio"] = fba_min / rrp
        rec["3p_never_below_rrp"] = 1.0 if fba_min >= rrp * 0.98 else 0.0

        # Price trend
        if len(fba_prices) >= 6:
            q = max(1, len(fba_prices) // 4)
            early = float(np.mean(fba_prices[:q]))
            late = float(np.mean(fba_prices[-q:]))
            if early > 0:
                rec["3p_price_trend_pct"] = (late - early) / early * 100

        # 3-month momentum (last ~13 weekly points)
        if len(fba_prices) >= 13:
            recent = float(np.mean(fba_prices[-13:]))
            prior = float(np.mean(fba_prices[:-13]))
            if prior > 0:
                rec["3p_price_momentum_3mo"] = (recent - prior) / prior * 100

        fba_mean = float(np.mean(fba_prices))
        if fba_mean > 0:
            rec["3p_price_cv"] = float(np.std(fba_prices) / fba_mean)

        # FBA vs Amazon spread (when both in stock)
        amz_ist_prices = [float(p[1]) for p in amz if p[1] is not None and p[1] > 0]
        if amz_ist_prices and fba_prices:
            rec["3p_fba_vs_amz_avg_spread"] = (fba_mean - float(np.mean(amz_ist_prices))) / rrp * 100

        # Price at retirement
        if fba:
            last_fba = None
            for p in reversed(fba):
                if p[1] is not None and p[1] > 0:
                    last_fba = float(p[1])
                    break
            if last_fba:
                rec["3p_price_at_retire_vs_rrp"] = last_fba / rrp

        # Last 6 months above RRP %
        fba_last_6mo = [
            p for p in fba
            if isinstance(p[0], str) and p[0] >= retire_minus_6mo.strftime("%Y-%m-%d")
            and p[1] is not None and p[1] > 0
        ]
        if fba_last_6mo:
            above_6mo = sum(1 for p in fba_last_6mo if p[1] > rrp)
            rec["3p_above_rrp_last_6mo_pct"] = above_6mo / len(fba_last_6mo) * 100

    # ----------------------------------------------------------------
    # E. Amazon 1P Price Dynamics
    # ----------------------------------------------------------------
    if amz_prices and rrp > 0:
        amz_mean = float(np.mean(amz_prices))
        rec["amz_avg_discount_pct"] = (rrp - amz_mean) / rrp * 100
        rec["amz_max_discount_pct"] = (rrp - min(amz_prices)) / rrp * 100
        rec["amz_never_discounted"] = 1.0 if min(amz_prices) >= rrp * 0.98 else 0.0

        if len(amz_prices) >= 6:
            q = max(1, len(amz_prices) // 4)
            early = float(np.mean(amz_prices[:q]))
            late = float(np.mean(amz_prices[-q:]))
            if early > 0:
                rec["amz_discount_trend"] = (late - early) / early * 100

        # Last Amazon price before final OOS
        last_amz = None
        for p in reversed(amz):
            if p[1] is not None and p[1] > 0:
                last_amz = float(p[1])
                break
        if last_amz:
            rec["amz_price_at_retire_vs_rrp"] = last_amz / rrp

        if amz_mean > 0:
            rec["amz_price_cv"] = float(np.std(amz_prices) / amz_mean)

        below_rrp = sum(1 for p in amz_prices if p < rrp)
        rec["amz_price_below_rrp_pct"] = below_rrp / len(amz_prices) * 100

    # ----------------------------------------------------------------
    # F. Demand Proxy
    # ----------------------------------------------------------------
    if pd.notna(row.get("tracking_users")):
        rec["keepa_tracking_users"] = float(row["tracking_users"])
    if pd.notna(row.get("kp_reviews")):
        rec["amz_review_count"] = float(row["kp_reviews"])
    if pd.notna(row.get("kp_rating")):
        rec["amz_rating"] = float(row["kp_rating"])

    # ----------------------------------------------------------------
    # J. Data Quality
    # ----------------------------------------------------------------
    if len(amz) >= 2:
        first_dt = date_str_to_dt(amz[0][0])
        last_dt = date_str_to_dt(amz[-1][0])
        if first_dt and last_dt:
            rec["keepa_data_months"] = max(1.0, (last_dt - first_dt).days / 30.44)
    rec["keepa_n_price_points"] = float(len(amz))
    rec["keepa_3p_data_available"] = 1.0 if len(fba) > 0 else 0.0

    return rec


# Extract features for all sets
print("Extracting Keepa features...")
t_feat = time.time()
feature_rows: list[dict] = []
for _, row in merged.iterrows():
    feature_rows.append(extract_features_for_set(row))

features_df = pd.DataFrame(feature_rows)
print(f"Feature extraction: {time.time() - t_feat:.1f}s, {len(features_df)} sets")

# ----------------------------------------------------------------
# I. Factual Metadata Features
# ----------------------------------------------------------------
print("Adding metadata features...")

from config.ml import LICENSED_THEMES

meta = base_df[["set_number", "theme", "subtheme", "parts_count", "minifig_count",
                "rrp_usd_cents", "rating_value", "review_count",
                "exclusive_minifigs", "minifig_value_cents", "designer",
                "retired_date", "release_date", "year_released"]].copy()

for col in ("parts_count", "minifig_count", "rrp_usd_cents", "rating_value",
            "review_count", "minifig_value_cents"):
    meta[col] = pd.to_numeric(meta[col], errors="coerce")

meta["log_rrp"] = np.log1p(meta["rrp_usd_cents"].fillna(0))
meta["log_parts"] = np.log1p(meta["parts_count"].fillna(0))
meta["price_per_part"] = np.where(
    meta["parts_count"] > 0,
    meta["rrp_usd_cents"] / meta["parts_count"], np.nan
)
meta["minifig_density"] = np.where(
    meta["parts_count"] > 0,
    meta["minifig_count"].fillna(0) / meta["parts_count"] * 100, np.nan
)
meta["has_exclusive_minifigs"] = meta["exclusive_minifigs"].notna().astype(float)
meta["minifig_value_ratio"] = np.where(
    meta["rrp_usd_cents"] > 0,
    meta["minifig_value_cents"].fillna(0) / meta["rrp_usd_cents"], np.nan
)
meta["is_licensed"] = meta["theme"].isin(LICENSED_THEMES).astype(float)

retired_dt = pd.to_datetime(meta["retired_date"], errors="coerce")
release_dt = pd.to_datetime(meta["release_date"], errors="coerce")
shelf_days = (retired_dt - release_dt).dt.days
meta["shelf_life_months"] = np.where(shelf_days > 0, shelf_days / 30.44, np.nan)
meta["retire_quarter"] = retired_dt.dt.quarter.astype(float)

rrp_usd = meta["rrp_usd_cents"].fillna(0) / 100
meta["price_tier"] = pd.cut(
    rrp_usd, bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999], labels=range(1, 9)
).astype(float)

# Year retired (for grouping)
meta["year_retired"] = retired_dt.dt.year

# Merge metadata with features
df = features_df.merge(
    meta[["set_number", "theme", "subtheme", "log_rrp", "log_parts",
          "price_per_part", "minifig_count", "minifig_density",
          "has_exclusive_minifigs", "minifig_value_ratio", "is_licensed",
          "shelf_life_months", "retire_quarter", "price_tier",
          "rrp_usd_cents", "year_released", "year_retired",
          "rating_value", "review_count", "retired_date"]],
    on="set_number", how="left"
)
print(f"Merged dataset: {len(df)} sets with features + metadata")

# ============================================================================
# PHASE 3: TARGET CONSTRUCTION
# ============================================================================
print("\n--- Phase 3: Target Construction ---")

# Target 1: BL current price / RRP
bl_current = bl_price_df.copy()
bl_current_prices: dict[str, float] = {}
for _, r in bl_current.iterrows():
    cn = r.get("current_new")
    if isinstance(cn, dict):
        qty_avg = cn.get("qty_avg_price") or cn.get("avg_price")
        if isinstance(qty_avg, dict) and qty_avg.get("amount"):
            bl_current_prices[r["set_number"]] = float(qty_avg["amount"])

# Target 2-4: BL monthly post-retirement prices at +12/24/36 months
bl_post_retire: dict[str, dict[str, float]] = {}  # sn -> {target_name: value}

for sn, group in bl_monthly_df.groupby("set_number"):
    sn = str(sn)
    retired_row = meta[meta["set_number"] == sn]
    if retired_row.empty:
        continue
    retired_date_str = retired_row.iloc[0]["retired_date"]
    ret_dt = parse_date(retired_date_str)
    if not ret_dt:
        continue

    rrp_val = retired_row.iloc[0]["rrp_usd_cents"]
    if pd.isna(rrp_val) or rrp_val <= 0:
        continue

    targets: dict[str, float] = {}

    for _, sale in group.iterrows():
        sale_dt = datetime(int(sale["year"]), int(sale["month"]), 15)
        months_post = (sale_dt.year - ret_dt.year) * 12 + (sale_dt.month - ret_dt.month)

        # Map to target buckets (allow +/- 2 month window)
        price_val = float(sale["avg_price"])
        currency = sale.get("currency", "MYR")
        # Convert MYR to USD cents (approx MYR/USD = 4.4)
        if currency == "MYR":
            price_usd_cents = price_val / 4.4
        else:
            price_usd_cents = price_val

        if 10 <= months_post <= 14:
            targets.setdefault("bl_price_12mo_prices", []).append(price_usd_cents)
        if 22 <= months_post <= 26:
            targets.setdefault("bl_price_24mo_prices", []).append(price_usd_cents)
        if 34 <= months_post <= 38:
            targets.setdefault("bl_price_36mo_prices", []).append(price_usd_cents)

    result: dict[str, float] = {}
    for key, bucket in [
        ("bl_price_12mo_vs_rrp", "bl_price_12mo_prices"),
        ("bl_price_24mo_vs_rrp", "bl_price_24mo_prices"),
        ("bl_price_36mo_vs_rrp", "bl_price_36mo_prices"),
    ]:
        prices = targets.get(bucket, [])
        if prices:
            result[key] = float(np.mean(prices)) / float(rrp_val)

    if result:
        bl_post_retire[sn] = result

# BL current as target
for sn in bl_current_prices:
    if sn not in bl_post_retire:
        bl_post_retire[sn] = {}
    # Convert MYR to USD cents (BL price history is in MYR)
    bl_post_retire[sn]["bl_current_vs_rrp"] = bl_current_prices[sn] / 4.4 / float(
        meta[meta["set_number"] == sn]["rrp_usd_cents"].iloc[0]
    ) if sn in meta["set_number"].values and meta[meta["set_number"] == sn]["rrp_usd_cents"].iloc[0] > 0 else None

# Annualized return
now = datetime(2026, 4, 9)
for sn, targets in bl_post_retire.items():
    if "bl_current_vs_rrp" in targets and targets["bl_current_vs_rrp"]:
        retired_row = meta[meta["set_number"] == sn]
        if not retired_row.empty:
            ret_dt = parse_date(retired_row.iloc[0]["retired_date"])
            if ret_dt:
                years = max(0.25, (now - ret_dt).days / 365.25)
                ratio = targets["bl_current_vs_rrp"]
                if ratio > 0:
                    targets["annualized_return"] = ratio ** (1.0 / years) - 1.0

# Merge targets
target_rows: list[dict] = []
for sn, t in bl_post_retire.items():
    target_rows.append({"set_number": sn, **t})
targets_df = pd.DataFrame(target_rows)

df = df.merge(targets_df, on="set_number", how="left")

print(f"Target coverage:")
for col in ["bl_price_12mo_vs_rrp", "bl_price_24mo_vs_rrp", "bl_price_36mo_vs_rrp",
            "bl_current_vs_rrp", "annualized_return"]:
    if col in df.columns:
        n = df[col].notna().sum()
        print(f"  {col}: {n} sets ({n/len(df)*100:.1f}%)")

# ============================================================================
# K. Interaction Features (metadata x market signals)
# ============================================================================
print("\n--- Adding interaction features ---")

oos_pct = df["amz_oos_pct"].fillna(0)
premium_3p = df.get("3p_avg_premium_vs_rrp_pct", pd.Series(0, index=df.index)).fillna(0)

df["oos_pct_x_licensed"] = oos_pct * df["is_licensed"].fillna(0)
df["oos_pct_x_price_tier"] = oos_pct * df["price_tier"].fillna(0)
df["3p_premium_x_price_tier"] = premium_3p * df["price_tier"].fillna(0)
df["3p_premium_x_exclusive_mfig"] = premium_3p * df["has_exclusive_minifigs"].fillna(0)
df["tracking_users_x_oos"] = df["keepa_tracking_users"].fillna(0) * oos_pct
df["oos_pct_x_shelf_life"] = oos_pct * df["shelf_life_months"].fillna(0)
df["3p_premium_x_minifig_density"] = premium_3p * df["minifig_density"].fillna(0)
df["oos_pct_x_log_rrp"] = oos_pct * df["log_rrp"].fillna(0)

# ============================================================================
# PHASE 4: EDA
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: EXPLORATORY DATA ANALYSIS")
print("=" * 70)

# Primary target for EDA: bl_current_vs_rrp (best coverage)
primary_target = "bl_current_vs_rrp"
has_target = df[primary_target].notna() if primary_target in df.columns else pd.Series(False, index=df.index)
df_eda = df[has_target].copy()
print(f"\nSets with primary target ({primary_target}): {len(df_eda)}")

# Feature list (all numeric, non-target, non-metadata-only)
exclude_cols = {
    "set_number", "theme", "subtheme", "retired_date",
    "bl_price_12mo_vs_rrp", "bl_price_24mo_vs_rrp", "bl_price_36mo_vs_rrp",
    "bl_current_vs_rrp", "annualized_return", "rrp_usd_cents",
    "year_released", "year_retired", "rating_value", "review_count",
}
feature_cols = [
    c for c in df_eda.columns
    if c not in exclude_cols and df_eda[c].dtype in ("float64", "float32", "int64", "int32")
]

print(f"\nTotal features: {len(feature_cols)}")

# Feature coverage
print("\n--- Feature Coverage ---")
coverage = []
for col in sorted(feature_cols):
    n = df_eda[col].notna().sum()
    pct = n / len(df_eda) * 100
    coverage.append((col, n, pct))
coverage.sort(key=lambda x: -x[2])
for name, n, pct in coverage:
    print(f"  {name:45s}: {n:5d} ({pct:5.1f}%)")

# Correlations with primary target
print(f"\n--- Correlations with {primary_target} ---")
target_values = df_eda[primary_target]
correlations: list[tuple[str, float, float]] = []
for col in feature_cols:
    vals = df_eda[col]
    mask = vals.notna() & target_values.notna()
    if mask.sum() < 20:
        continue
    pearson = vals[mask].corr(target_values[mask])
    spearman = vals[mask].rank().corr(target_values[mask].rank())
    correlations.append((col, pearson, spearman))

correlations.sort(key=lambda x: -abs(x[2]))
print(f"\n{'Feature':45s} {'Pearson':>8s} {'Spearman':>8s}")
print("-" * 65)
for name, p, s in correlations[:40]:
    print(f"  {name:43s} {p:8.3f} {s:8.3f}")

# ============================================================================
# PHASE 5: VALIDATE 75248 and 76173
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 5: VALIDATE 75248 / 76173")
print("=" * 70)

for sn in ["75248", "76173"]:
    row = df[df["set_number"] == sn]
    if row.empty:
        print(f"\n{sn}: NOT IN DATASET")
        continue
    print(f"\n--- {sn} ({row.iloc[0].get('theme', '?')}) ---")
    for col in feature_cols:
        val = row.iloc[0][col]
        if pd.notna(val):
            print(f"  {col:45s}: {val:12.2f}")
    for t in ["bl_current_vs_rrp", "annualized_return", "bl_price_12mo_vs_rrp"]:
        if t in row.columns:
            val = row.iloc[0][t]
            if pd.notna(val):
                print(f"  [TARGET] {t:38s}: {val:12.3f}")

# ============================================================================
# PHASE 6: COHORT ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: COHORT ANALYSIS")
print("=" * 70)

# Top features for cohort slicing (take top 10 by abs spearman)
top_features = [name for name, _, _ in correlations[:10]] if correlations else []

# 6a. By retirement year
print("\n--- Cohort: Retirement Year ---")
if "year_retired" in df_eda.columns:
    for yr, grp in df_eda.groupby("year_retired"):
        if len(grp) < 10:
            continue
        target_vals = grp[primary_target]
        print(f"\n  Year {int(yr)}: n={len(grp)}, target mean={target_vals.mean():.3f}, median={target_vals.median():.3f}")
        for feat in top_features[:5]:
            if feat in grp.columns:
                mask = grp[feat].notna() & target_vals.notna()
                if mask.sum() >= 10:
                    corr = grp[feat][mask].rank().corr(target_vals[mask].rank())
                    print(f"    {feat:40s} spearman={corr:+.3f} (n={mask.sum()})")

# 6b. By theme (top themes)
print("\n--- Cohort: Theme (top 10 by count) ---")
if "theme" in df_eda.columns:
    theme_counts = df_eda["theme"].value_counts()
    for theme in theme_counts.head(10).index:
        grp = df_eda[df_eda["theme"] == theme]
        if len(grp) < 10:
            continue
        target_vals = grp[primary_target]
        print(f"\n  {theme}: n={len(grp)}, target mean={target_vals.mean():.3f}")
        for feat in top_features[:5]:
            if feat in grp.columns:
                mask = grp[feat].notna() & target_vals.notna()
                if mask.sum() >= 5:
                    corr = grp[feat][mask].rank().corr(target_vals[mask].rank())
                    print(f"    {feat:40s} spearman={corr:+.3f} (n={mask.sum()})")

# 6c. By price tier
print("\n--- Cohort: Price Tier ---")
if "price_tier" in df_eda.columns:
    for tier, grp in df_eda.groupby("price_tier"):
        if len(grp) < 10:
            continue
        target_vals = grp[primary_target]
        print(f"\n  Tier {int(tier)}: n={len(grp)}, target mean={target_vals.mean():.3f}")
        for feat in top_features[:5]:
            if feat in grp.columns:
                mask = grp[feat].notna() & target_vals.notna()
                if mask.sum() >= 5:
                    corr = grp[feat][mask].rank().corr(target_vals[mask].rank())
                    print(f"    {feat:40s} spearman={corr:+.3f} (n={mask.sum()})")

# 6d. Licensed vs unlicensed
print("\n--- Cohort: Licensed vs Unlicensed ---")
for label, val in [("Licensed", 1.0), ("Unlicensed", 0.0)]:
    grp = df_eda[df_eda["is_licensed"] == val]
    if len(grp) < 10:
        continue
    target_vals = grp[primary_target]
    print(f"\n  {label}: n={len(grp)}, target mean={target_vals.mean():.3f}")
    for feat in top_features[:5]:
        if feat in grp.columns:
            mask = grp[feat].notna() & target_vals.notna()
            if mask.sum() >= 5:
                corr = grp[feat][mask].rank().corr(target_vals[mask].rank())
                print(f"    {feat:40s} spearman={corr:+.3f} (n={mask.sum()})")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total sets processed: {len(df)}")
print(f"Sets with primary target: {len(df_eda)}")
print(f"Features extracted: {len(feature_cols)}")
print(f"Time elapsed: {time.time() - t0:.1f}s")

if correlations:
    print(f"\nTop 10 features by |Spearman| with {primary_target}:")
    for name, p, s in correlations[:10]:
        print(f"  {name:45s} r={s:+.3f}")

# Save feature_cols and df_eda for later phases
_saved_feature_cols = feature_cols
_saved_df_eda = df_eda
_saved_correlations = correlations

# ============================================================================
# PHASE 7: LIGHTGBM MODEL
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 7: LIGHTGBM MODEL")
print("=" * 70)

import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import PowerTransformer

# Use bl_current_vs_rrp as primary target (best coverage)
# Also test annualized_return as alternative
TARGET_COLS = ["bl_current_vs_rrp", "annualized_return"]

# Select features: drop low-coverage (<50%) and data quality flags
model_feature_cols = [
    c for c in feature_cols
    if df_eda[c].notna().mean() >= 0.50
    and c not in ("keepa_3p_data_available",)
]
print(f"\nModel features (>=50% coverage): {len(model_feature_cols)}")

# Groups for GroupKFold: retirement year
groups_col = df_eda["year_retired"].fillna(2023).astype(int)

for target_col in TARGET_COLS:
    print(f"\n{'=' * 50}")
    print(f"TARGET: {target_col}")
    print(f"{'=' * 50}")

    mask = df_eda[target_col].notna()
    df_model = df_eda[mask].copy()
    y_raw = df_model[target_col].values.astype(float)

    if len(df_model) < 50:
        print(f"  Skipping: only {len(df_model)} samples")
        continue

    # Winsorize target at P2/P98
    lo, hi = np.percentile(y_raw, [2, 98])
    y = np.clip(y_raw, lo, hi)

    # Yeo-Johnson transform target
    yt = PowerTransformer(method="yeo-johnson")
    y_transformed = yt.fit_transform(y.reshape(-1, 1)).ravel()

    X = df_model[model_feature_cols].values.astype(float)
    groups = groups_col[mask].values

    # 5-fold GroupKFold
    n_splits = 5
    gkf = GroupKFold(n_splits=n_splits)

    oof_preds = np.full(len(y), np.nan)
    fold_metrics: list[dict] = []
    importances = np.zeros(len(model_feature_cols))

    for fold_i, (train_idx, val_idx) in enumerate(gkf.split(X, y_transformed, groups)):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y_transformed[train_idx], y_transformed[val_idx]

        dtrain = lgb.Dataset(X_tr, label=y_tr, feature_name=model_feature_cols)
        dval = lgb.Dataset(X_val, label=y_val, feature_name=model_feature_cols, reference=dtrain)

        params = {
            "objective": "huber",
            "metric": "mae",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "max_depth": 6,
            "min_child_samples": 10,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "verbosity": -1,
            "seed": 42 + fold_i,
        }

        model = lgb.train(
            params, dtrain,
            num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

        # Predict in transformed space, then inverse transform
        val_pred_transformed = model.predict(X_val)
        val_pred = yt.inverse_transform(val_pred_transformed.reshape(-1, 1)).ravel()
        oof_preds[val_idx] = val_pred

        y_val_orig = y[val_idx]
        fold_r2 = r2_score(y_val_orig, val_pred)
        fold_mae = mean_absolute_error(y_val_orig, val_pred)

        val_groups = groups[val_idx]
        unique_groups = np.unique(val_groups)
        fold_metrics.append({
            "fold": fold_i + 1,
            "r2": fold_r2,
            "mae": fold_mae,
            "n_val": len(val_idx),
            "val_years": sorted(unique_groups.tolist()),
            "n_trees": model.best_iteration,
        })

        importances += model.feature_importance(importance_type="gain")

        print(f"  Fold {fold_i + 1}: R2={fold_r2:.3f}, MAE={fold_mae:.4f}, "
              f"n={len(val_idx)}, trees={model.best_iteration}, "
              f"years={sorted(unique_groups.tolist())}")

    importances /= n_splits

    # Overall OOF metrics
    valid_mask = ~np.isnan(oof_preds)
    if valid_mask.sum() > 0:
        overall_r2 = r2_score(y[valid_mask], oof_preds[valid_mask])
        overall_mae = mean_absolute_error(y[valid_mask], oof_preds[valid_mask])
        mean_r2 = np.mean([m["r2"] for m in fold_metrics])
        std_r2 = np.std([m["r2"] for m in fold_metrics])

        print(f"\n  OOF R2: {overall_r2:.3f}")
        print(f"  OOF MAE: {overall_mae:.4f}")
        print(f"  Mean fold R2: {mean_r2:.3f} +/- {std_r2:.3f}")

        # Residual analysis
        residuals = oof_preds[valid_mask] - y[valid_mask]
        print(f"  Residual mean: {residuals.mean():.4f}, std: {residuals.std():.4f}")

        # Top/bottom quintile analysis
        y_actual = y[valid_mask]
        y_pred = oof_preds[valid_mask]
        q20 = np.percentile(y_pred, 20)
        q80 = np.percentile(y_pred, 80)

        bottom_mask = y_pred <= q20
        top_mask = y_pred >= q80
        if bottom_mask.sum() > 0 and top_mask.sum() > 0:
            print(f"\n  Bottom 20% predicted: actual mean={y_actual[bottom_mask].mean():.3f}")
            print(f"  Top 20% predicted:    actual mean={y_actual[top_mask].mean():.3f}")
            print(f"  Separation: {y_actual[top_mask].mean() - y_actual[bottom_mask].mean():.3f}")

    # Feature importance
    print(f"\n  Top 20 features by importance (gain):")
    imp_order = np.argsort(-importances)
    for rank, idx in enumerate(imp_order[:20]):
        print(f"    {rank+1:2d}. {model_feature_cols[idx]:40s} gain={importances[idx]:10.1f}")

    # Rank correlation: how well does model rank sets?
    if valid_mask.sum() > 0:
        from scipy.stats import spearmanr
        rank_corr, _ = spearmanr(y[valid_mask], oof_preds[valid_mask])
        print(f"\n  OOF Spearman rank correlation: {rank_corr:.3f}")

# ============================================================================
# PHASE 8: MULTI-TARGET COMPARISON
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 8: MULTI-TARGET HORIZON COMPARISON")
print("=" * 70)

horizon_targets = [
    ("bl_price_12mo_vs_rrp", "12mo post-retire"),
    ("bl_price_24mo_vs_rrp", "24mo post-retire"),
    ("bl_price_36mo_vs_rrp", "36mo post-retire"),
    ("bl_current_vs_rrp", "Current BL price"),
]

for target_col, label in horizon_targets:
    if target_col not in df_eda.columns:
        continue
    mask = df_eda[target_col].notna()
    n = mask.sum()
    if n < 30:
        print(f"\n  {label} ({target_col}): n={n} -- too few, skipping")
        continue

    df_h = df_eda[mask]
    y_h = df_h[target_col].values.astype(float)

    # Quick 3-fold CV (fewer sets for horizon targets)
    n_folds = min(3, len(np.unique(groups_col[mask])))
    if n_folds < 2:
        print(f"\n  {label}: only {n_folds} group(s), skipping")
        continue

    gkf_h = GroupKFold(n_splits=n_folds)
    X_h = df_h[model_feature_cols].values.astype(float)
    g_h = groups_col[mask].values

    lo_h, hi_h = np.percentile(y_h, [2, 98])
    y_h_clip = np.clip(y_h, lo_h, hi_h)

    fold_r2s = []
    for train_idx, val_idx in gkf_h.split(X_h, y_h_clip, g_h):
        dtrain = lgb.Dataset(X_h[train_idx], label=y_h_clip[train_idx], feature_name=model_feature_cols)
        dval = lgb.Dataset(X_h[val_idx], label=y_h_clip[val_idx], feature_name=model_feature_cols, reference=dtrain)

        model_h = lgb.train(
            {
                "objective": "huber", "metric": "mae",
                "learning_rate": 0.05, "num_leaves": 15, "max_depth": 4,
                "min_child_samples": 5, "subsample": 0.8, "colsample_bytree": 0.8,
                "verbosity": -1,
            },
            dtrain, num_boost_round=300,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )
        pred = model_h.predict(X_h[val_idx])
        fold_r2s.append(r2_score(y_h_clip[val_idx], pred))

    mean_r2 = np.mean(fold_r2s)
    std_r2 = np.std(fold_r2s)
    print(f"\n  {label:25s} n={n:4d}  CV R2={mean_r2:.3f} +/- {std_r2:.3f}  folds={fold_r2s}")

# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)
print(f"Dataset: {len(df_eda)} sets, {len(model_feature_cols)} features")
print(f"Time: {time.time() - t0:.1f}s")
print("\nKey results above. Compare with T1 baseline: R2=0.754 on BE growth target (different target!).")

# ============================================================================
# PHASE 9: FEATURE SELECTION
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 9: FEATURE SELECTION")
print("=" * 70)

from sklearn.feature_selection import mutual_info_regression
from scipy.stats import spearmanr

target_col_fs = "bl_current_vs_rrp"
mask_fs = df_eda[target_col_fs].notna()
df_fs = df_eda[mask_fs].copy()
y_fs = df_fs[target_col_fs].values.astype(float)
groups_fs = df_fs["year_retired"].fillna(2023).astype(int).values

# Start with features that have >=50% coverage
fs_candidates = [
    c for c in feature_cols
    if df_fs[c].notna().mean() >= 0.50
    and c not in ("keepa_3p_data_available",)
]
print(f"\nStarting candidates (>=50% coverage): {len(fs_candidates)}")

# Step 1: Mutual Information filtering
print("\n--- Step 1: Mutual Information ---")
X_mi = df_fs[fs_candidates].fillna(0).values.astype(float)
mi_scores = mutual_info_regression(X_mi, y_fs, random_state=42, n_neighbors=10)
mi_df = pd.DataFrame({"feature": fs_candidates, "mi": mi_scores}).sort_values("mi", ascending=False)

MI_THRESHOLD = 0.01
dropped_mi = mi_df[mi_df["mi"] < MI_THRESHOLD]["feature"].tolist()
kept_mi = mi_df[mi_df["mi"] >= MI_THRESHOLD]["feature"].tolist()

print(f"MI threshold: {MI_THRESHOLD}")
print(f"Kept: {len(kept_mi)}, Dropped: {len(dropped_mi)}")
if dropped_mi:
    print(f"Dropped (MI < {MI_THRESHOLD}): {dropped_mi}")

print("\nTop 20 by MI:")
for _, row in mi_df.head(20).iterrows():
    print(f"  {row['feature']:45s} MI={row['mi']:.4f}")

# Step 2: Redundancy removal (Spearman > 0.85)
print("\n--- Step 2: Redundancy Removal ---")
CORR_THRESHOLD = 0.85

X_kept = df_fs[kept_mi].fillna(0)
corr_matrix = X_kept.corr(method="spearman").abs()

# For each pair above threshold, drop the one with lower MI
to_drop_redundant: set[str] = set()
mi_lookup = dict(zip(mi_df["feature"], mi_df["mi"]))

for i in range(len(kept_mi)):
    if kept_mi[i] in to_drop_redundant:
        continue
    for j in range(i + 1, len(kept_mi)):
        if kept_mi[j] in to_drop_redundant:
            continue
        if corr_matrix.iloc[i, j] > CORR_THRESHOLD:
            fi, fj = kept_mi[i], kept_mi[j]
            mi_i = mi_lookup.get(fi, 0)
            mi_j = mi_lookup.get(fj, 0)
            drop = fj if mi_i >= mi_j else fi
            to_drop_redundant.add(drop)
            print(f"  Dropping {drop} (corr={corr_matrix.iloc[i, j]:.3f} with "
                  f"{'kept ' + fi if drop == fj else 'kept ' + fj})")

kept_after_redundancy = [f for f in kept_mi if f not in to_drop_redundant]
print(f"\nAfter redundancy removal: {len(kept_after_redundancy)} features "
      f"(dropped {len(to_drop_redundant)})")

# Step 3: LOFO (Leave-One-Feature-Out)
print("\n--- Step 3: LOFO ---")

def cv_r2(features: list[str], df_in: pd.DataFrame, y: np.ndarray,
           groups: np.ndarray, n_splits: int = 5) -> float:
    """Quick CV R2 for a feature set."""
    X = df_in[features].fillna(0).values.astype(float)

    # Winsorize + Yeo-Johnson
    lo, hi = np.percentile(y, [2, 98])
    y_clip = np.clip(y, lo, hi)
    yt = PowerTransformer(method="yeo-johnson")
    y_t = yt.fit_transform(y_clip.reshape(-1, 1)).ravel()

    gkf = GroupKFold(n_splits=n_splits)
    r2s: list[float] = []

    for train_idx, val_idx in gkf.split(X, y_t, groups):
        dtrain = lgb.Dataset(X[train_idx], label=y_t[train_idx], feature_name=features)
        dval = lgb.Dataset(X[val_idx], label=y_t[val_idx], feature_name=features, reference=dtrain)

        model = lgb.train(
            {
                "objective": "huber", "metric": "mae",
                "learning_rate": 0.05, "num_leaves": 31, "max_depth": 6,
                "min_child_samples": 10, "subsample": 0.8, "colsample_bytree": 0.8,
                "reg_alpha": 0.1, "reg_lambda": 0.1, "verbosity": -1,
            },
            dtrain, num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        pred_t = model.predict(X[val_idx])
        pred = yt.inverse_transform(pred_t.reshape(-1, 1)).ravel()
        r2s.append(r2_score(y_clip[val_idx], pred))

    return float(np.mean(r2s))


# Baseline with all kept features
baseline_r2 = cv_r2(kept_after_redundancy, df_fs, y_fs, groups_fs)
print(f"Baseline R2 ({len(kept_after_redundancy)} features): {baseline_r2:.4f}")

# LOFO: drop each feature and measure delta
lofo_results: list[tuple[str, float, float]] = []
for feat in kept_after_redundancy:
    reduced = [f for f in kept_after_redundancy if f != feat]
    r2_without = cv_r2(reduced, df_fs, y_fs, groups_fs)
    delta = r2_without - baseline_r2
    lofo_results.append((feat, r2_without, delta))
    direction = "HELPS" if delta < -0.005 else ("HURTS" if delta > 0.005 else "neutral")
    print(f"  Drop {feat:42s}: R2={r2_without:.4f} (delta={delta:+.4f}) {direction}")

lofo_results.sort(key=lambda x: x[2])

print(f"\n--- LOFO Summary ---")
print("Features that HELP (dropping them hurts R2):")
for name, r2, delta in lofo_results:
    if delta < -0.003:
        print(f"  {name:45s} delta={delta:+.4f}")

print("\nFeatures that HURT (dropping them improves R2):")
hurting = []
for name, r2, delta in lofo_results:
    if delta > 0.003:
        print(f"  {name:45s} delta={delta:+.4f}")
        hurting.append(name)

# Build final feature set: drop features that hurt
final_features = [f for f in kept_after_redundancy if f not in hurting]
final_r2 = cv_r2(final_features, df_fs, y_fs, groups_fs)
print(f"\nFinal feature set: {len(final_features)} features, R2={final_r2:.4f} "
      f"(vs baseline {baseline_r2:.4f}, delta={final_r2 - baseline_r2:+.4f})")

print("\nFinal features:")
for i, f in enumerate(final_features):
    mi_val = mi_lookup.get(f, 0)
    print(f"  {i+1:2d}. {f:45s} MI={mi_val:.4f}")

# ============================================================================
# PHASE 10: RETRAIN WITH FINAL FEATURES + OOF PREDICTIONS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 10: FINAL MODEL")
print("=" * 70)

X_final = df_fs[final_features].fillna(0).values.astype(float)
lo, hi = np.percentile(y_fs, [2, 98])
y_clip = np.clip(y_fs, lo, hi)
yt_final = PowerTransformer(method="yeo-johnson")
y_t_final = yt_final.fit_transform(y_clip.reshape(-1, 1)).ravel()

gkf_final = GroupKFold(n_splits=5)
oof_final = np.full(len(y_fs), np.nan)
importances_final = np.zeros(len(final_features))

for fold_i, (train_idx, val_idx) in enumerate(gkf_final.split(X_final, y_t_final, groups_fs)):
    dtrain = lgb.Dataset(X_final[train_idx], label=y_t_final[train_idx], feature_name=final_features)
    dval = lgb.Dataset(X_final[val_idx], label=y_t_final[val_idx], feature_name=final_features, reference=dtrain)

    model_f = lgb.train(
        {
            "objective": "huber", "metric": "mae",
            "learning_rate": 0.05, "num_leaves": 31, "max_depth": 6,
            "min_child_samples": 10, "subsample": 0.8, "colsample_bytree": 0.8,
            "reg_alpha": 0.1, "reg_lambda": 0.1, "verbosity": -1,
            "seed": 42 + fold_i,
        },
        dtrain, num_boost_round=500,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    pred_t = model_f.predict(X_final[val_idx])
    oof_final[val_idx] = yt_final.inverse_transform(pred_t.reshape(-1, 1)).ravel()
    importances_final += model_f.feature_importance(importance_type="gain")

    fold_r2 = r2_score(y_clip[val_idx], oof_final[val_idx])
    val_groups = groups_fs[val_idx]
    print(f"  Fold {fold_i+1}: R2={fold_r2:.3f}, years={sorted(np.unique(val_groups).tolist())}")

importances_final /= 5
valid = ~np.isnan(oof_final)

overall_r2 = r2_score(y_clip[valid], oof_final[valid])
overall_mae = mean_absolute_error(y_clip[valid], oof_final[valid])
rank_corr, _ = spearmanr(y_clip[valid], oof_final[valid])

print(f"\nFinal model: R2={overall_r2:.3f}, MAE={overall_mae:.4f}, Spearman={rank_corr:.3f}")
print(f"Features: {len(final_features)}")

print("\nFeature importance (gain):")
imp_order = np.argsort(-importances_final)
for rank, idx in enumerate(imp_order[:20]):
    print(f"  {rank+1:2d}. {final_features[idx]:40s} gain={importances_final[idx]:10.1f}")

# ============================================================================
# PHASE 11: FAILURE MODE ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 11: FAILURE MODE ANALYSIS")
print("=" * 70)

df_fs_copy = df_fs.copy()
df_fs_copy["oof_pred"] = oof_final
df_fs_copy["residual"] = oof_final - y_clip
df_fs_copy["abs_error"] = np.abs(oof_final - y_clip)
df_fs_copy["y_actual"] = y_clip

# 11a. Worst overpredictions (model says high, actual low)
print("\n--- Worst Overpredictions (predicted >> actual) ---")
overpredict = df_fs_copy[valid].nlargest(15, "residual")
print(f"{'Set':>8s} {'Theme':>15s} {'Actual':>8s} {'Pred':>8s} {'Error':>8s}")
for _, r in overpredict.iterrows():
    print(f"  {r['set_number']:>6s} {str(r.get('theme', ''))[:15]:>15s} "
          f"{r['y_actual']:8.3f} {r['oof_pred']:8.3f} {r['residual']:+8.3f}")

# 11b. Worst underpredictions (model says low, actual high)
print("\n--- Worst Underpredictions (predicted << actual) ---")
underpredict = df_fs_copy[valid].nsmallest(15, "residual")
print(f"{'Set':>8s} {'Theme':>15s} {'Actual':>8s} {'Pred':>8s} {'Error':>8s}")
for _, r in underpredict.iterrows():
    print(f"  {r['set_number']:>6s} {str(r.get('theme', ''))[:15]:>15s} "
          f"{r['y_actual']:8.3f} {r['oof_pred']:8.3f} {r['residual']:+8.3f}")

# 11c. Error by retirement year
print("\n--- Error by Retirement Year ---")
for yr, grp in df_fs_copy[valid].groupby("year_retired"):
    if len(grp) < 5:
        continue
    mae = grp["abs_error"].mean()
    bias = grp["residual"].mean()
    r2_yr = r2_score(grp["y_actual"], grp["oof_pred"]) if len(grp) >= 5 else float("nan")
    print(f"  {int(yr)}: n={len(grp):3d}, MAE={mae:.3f}, bias={bias:+.3f}, R2={r2_yr:.3f}")

# 11d. Error by theme
print("\n--- Error by Theme (top 10) ---")
theme_errors = []
for theme, grp in df_fs_copy[valid].groupby("theme"):
    if len(grp) < 10:
        continue
    mae = grp["abs_error"].mean()
    bias = grp["residual"].mean()
    r2_t = r2_score(grp["y_actual"], grp["oof_pred"]) if len(grp) >= 5 else float("nan")
    theme_errors.append((theme, len(grp), mae, bias, r2_t))

theme_errors.sort(key=lambda x: -x[2])
print(f"{'Theme':>15s} {'n':>4s} {'MAE':>6s} {'Bias':>7s} {'R2':>6s}")
for theme, n, mae, bias, r2_t in theme_errors:
    print(f"  {theme[:15]:>13s} {n:4d} {mae:6.3f} {bias:+7.3f} {r2_t:6.3f}")

# 11e. Error by price tier
print("\n--- Error by Price Tier ---")
for tier, grp in df_fs_copy[valid].groupby("price_tier"):
    if len(grp) < 10:
        continue
    mae = grp["abs_error"].mean()
    bias = grp["residual"].mean()
    r2_tier = r2_score(grp["y_actual"], grp["oof_pred"])
    print(f"  Tier {int(tier)}: n={len(grp):3d}, MAE={mae:.3f}, bias={bias:+.3f}, R2={r2_tier:.3f}")

# 11f. Error by target value quintile (where does model fail?)
print("\n--- Error by Actual Value Quintile ---")
df_valid = df_fs_copy[valid].copy()
df_valid["quintile"] = pd.qcut(df_valid["y_actual"], q=5, labels=["Q1(low)", "Q2", "Q3", "Q4", "Q5(high)"])
for q, grp in df_valid.groupby("quintile"):
    mae = grp["abs_error"].mean()
    bias = grp["residual"].mean()
    actual_mean = grp["y_actual"].mean()
    pred_mean = grp["oof_pred"].mean()
    print(f"  {q}: n={len(grp):3d}, actual_mean={actual_mean:.3f}, pred_mean={pred_mean:.3f}, "
          f"bias={bias:+.3f}, MAE={mae:.3f}")

# 11g. Data quality impact
print("\n--- Error by Keepa Data Coverage ---")
if "keepa_data_months" in df_valid.columns:
    df_valid["data_bucket"] = pd.cut(
        df_valid["keepa_data_months"].fillna(0),
        bins=[0, 6, 12, 24, 48, 999],
        labels=["<6mo", "6-12mo", "12-24mo", "24-48mo", "48mo+"]
    )
    for bucket, grp in df_valid.groupby("data_bucket"):
        if len(grp) < 10:
            continue
        mae = grp["abs_error"].mean()
        bias = grp["residual"].mean()
        print(f"  {bucket}: n={len(grp):3d}, MAE={mae:.3f}, bias={bias:+.3f}")

# 11h. Sets where 3P premium is high but appreciation is low (false positives)
print("\n--- False Positives: High 3P Premium but Low Actual ---")
if "3p_avg_premium_vs_rrp_pct" in df_valid.columns:
    high_3p = df_valid["3p_avg_premium_vs_rrp_pct"].fillna(0) > 20
    low_actual = df_valid["y_actual"] < 1.0
    false_pos = df_valid[high_3p & low_actual]
    print(f"  Sets with 3P premium > 20% but BL price < RRP: {len(false_pos)}")
    if len(false_pos) > 0:
        print(f"  {'Set':>8s} {'Theme':>15s} {'3P Prem%':>8s} {'Actual':>8s} {'OOS%':>6s}")
        for _, r in false_pos.head(15).iterrows():
            print(f"    {r['set_number']:>6s} {str(r.get('theme', ''))[:15]:>15s} "
                  f"{r.get('3p_avg_premium_vs_rrp_pct', 0):8.1f} "
                  f"{r['y_actual']:8.3f} "
                  f"{r.get('amz_oos_pct', 0):6.1f}")

# 11i. Sets where 3P premium is low but appreciation is high (false negatives)
print("\n--- False Negatives: Low 3P Premium but High Actual ---")
if "3p_avg_premium_vs_rrp_pct" in df_valid.columns:
    low_3p = df_valid["3p_avg_premium_vs_rrp_pct"].fillna(0) < 5
    high_actual = df_valid["y_actual"] > 1.5
    false_neg = df_valid[low_3p & high_actual]
    print(f"  Sets with 3P premium < 5% but BL price > 1.5x RRP: {len(false_neg)}")
    if len(false_neg) > 0:
        print(f"  {'Set':>8s} {'Theme':>15s} {'3P Prem%':>8s} {'Actual':>8s} {'Title'}")
        for _, r in false_neg.head(15).iterrows():
            print(f"    {r['set_number']:>6s} {str(r.get('theme', ''))[:15]:>15s} "
                  f"{r.get('3p_avg_premium_vs_rrp_pct', 0):8.1f} "
                  f"{r['y_actual']:8.3f} "
                  f"{str(r.get('title', ''))[:40]}")

# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)
print(f"Feature selection: {len(fs_candidates)} -> {len(kept_mi)} (MI) -> "
      f"{len(kept_after_redundancy)} (redundancy) -> {len(final_features)} (LOFO)")
print(f"Baseline R2: {baseline_r2:.4f}")
print(f"Final R2:    {final_r2:.4f} (delta={final_r2 - baseline_r2:+.4f})")
print(f"Final Spearman: {rank_corr:.3f}")
print(f"Time: {time.time() - t0:.1f}s")

# ============================================================================
# PHASE 12: ITERATION -- ALL FOUR IMPROVEMENTS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 12: ITERATED MODEL (4 improvements)")
print("  1. Exclude 2025+ sets (barely retired)")
print("  2. Theme-aware penalty for false-positive themes")
print("  3. Missing Keepa fallback features")
print("  4. Optuna hyperparameter tuning")
print("=" * 70)

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ---- Improvement 1: Exclude 2025+ from training ----
print("\n--- Improvement 1: Exclude 2025+ sets ---")
df_iter = df_fs.copy()
df_iter["oof_pred"] = oof_final
df_iter["y_actual"] = y_clip

yr_mask = df_iter["year_retired"].fillna(2023) <= 2024
df_train_pool = df_iter[yr_mask].copy()
df_2025_holdout = df_iter[~yr_mask].copy()
print(f"Training pool (retired <= 2024): {len(df_train_pool)} sets")
print(f"2025+ holdout: {len(df_2025_holdout)} sets")

y_train_pool = df_train_pool[target_col_fs].values.astype(float)
groups_train_pool = df_train_pool["year_retired"].fillna(2023).astype(int).values

# ---- Improvement 2: Theme penalty features ----
print("\n--- Improvement 2: Theme-aware features ---")

# False-positive themes: high 3P premium but no BL appreciation
FALSE_POS_THEMES = {"Dots", "DUPLO", "Duplo", "Classic", "Seasonal",
                    "Holiday & Event", "Trolls World Tour", "Vidiyo"}

# High-appreciation themes
STRONG_THEMES = {"Star Wars", "Super Heroes", "Harry Potter", "Technic",
                 "Creator", "Icons", "NINJAGO", "Ninjago"}

for d in [df_train_pool, df_2025_holdout, df_iter]:
    d["theme_false_pos"] = d["theme"].isin(FALSE_POS_THEMES).astype(float)
    d["theme_strong"] = d["theme"].isin(STRONG_THEMES).astype(float)
    # Interaction: 3P premium is discounted for false-positive themes
    prem = d.get("3p_above_rrp_pct", pd.Series(0, index=d.index)).fillna(0)
    d["3p_prem_adj"] = prem * (1 - 0.5 * d["theme_false_pos"])
    # Strong theme x premium interaction
    d["strong_theme_x_prem"] = d["theme_strong"] * prem

print(f"False-positive theme sets: {df_train_pool['theme_false_pos'].sum():.0f}")
print(f"Strong theme sets: {df_train_pool['theme_strong'].sum():.0f}")

# ---- Improvement 3: Missing Keepa fallback ----
print("\n--- Improvement 3: Missing Keepa fallback features ---")

# For sets with missing/sparse Keepa 3P data, create metadata-only proxy features
for d in [df_train_pool, df_2025_holdout, df_iter]:
    has_3p = d["3p_above_rrp_pct"].notna()
    d["has_keepa_3p"] = has_3p.astype(float)
    # Metadata-only demand proxy: reviews * minifig_value (available even without Keepa)
    d["meta_demand_proxy"] = (
        np.log1p(d.get("amz_review_count", pd.Series(0, index=d.index)).fillna(0))
        * d["minifig_value_ratio"].fillna(0)
    )
    # Fill 3P features with 0 for missing (model can learn from has_keepa_3p flag)

print(f"Sets with 3P data: {df_train_pool['has_keepa_3p'].sum():.0f} / {len(df_train_pool)}")

# Build iterated feature set
iter_features = final_features + [
    "theme_false_pos", "theme_strong", "3p_prem_adj", "strong_theme_x_prem",
    "has_keepa_3p", "meta_demand_proxy",
]

# Quick sanity: check baseline with new features before tuning
baseline_iter_r2 = cv_r2(iter_features, df_train_pool, y_train_pool, groups_train_pool)
print(f"\nBaseline with new features (no tuning, <=2024): R2={baseline_iter_r2:.4f}")

# Compare to original on same subset
orig_r2_subset = cv_r2(final_features, df_train_pool, y_train_pool, groups_train_pool)
print(f"Original features on same subset: R2={orig_r2_subset:.4f}")
print(f"Delta from new features: {baseline_iter_r2 - orig_r2_subset:+.4f}")

# ---- Improvement 4: Optuna tuning ----
print("\n--- Improvement 4: Optuna Tuning ---")

X_opt = df_train_pool[iter_features].fillna(0).values.astype(float)
lo_opt, hi_opt = np.percentile(y_train_pool, [2, 98])
y_opt_clip = np.clip(y_train_pool, lo_opt, hi_opt)


def objective(trial: optuna.Trial) -> float:
    params = {
        "objective": "huber",
        "metric": "mae",
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 8, 63),
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 30),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        "verbosity": -1,
    }

    yt_opt = PowerTransformer(method="yeo-johnson")
    y_t_opt = yt_opt.fit_transform(y_opt_clip.reshape(-1, 1)).ravel()

    gkf_opt = GroupKFold(n_splits=5)
    r2s: list[float] = []

    for train_idx, val_idx in gkf_opt.split(X_opt, y_t_opt, groups_train_pool):
        dtrain = lgb.Dataset(X_opt[train_idx], label=y_t_opt[train_idx], feature_name=iter_features)
        dval = lgb.Dataset(X_opt[val_idx], label=y_t_opt[val_idx], feature_name=iter_features, reference=dtrain)

        model_opt = lgb.train(
            params, dtrain,
            num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        pred_t = model_opt.predict(X_opt[val_idx])
        pred = yt_opt.inverse_transform(pred_t.reshape(-1, 1)).ravel()
        r2s.append(r2_score(y_opt_clip[val_idx], pred))

    return float(np.mean(r2s))


study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=40, show_progress_bar=False)

best = study.best_params
print(f"\nBest Optuna R2: {study.best_value:.4f}")
print(f"Best params: {best}")

# ---- Final model with all improvements + best params ----
print("\n" + "=" * 70)
print("FINAL ITERATED MODEL")
print("=" * 70)

best_params = {
    "objective": "huber",
    "metric": "mae",
    "verbosity": -1,
    **best,
}

yt_iter = PowerTransformer(method="yeo-johnson")
y_t_iter = yt_iter.fit_transform(y_opt_clip.reshape(-1, 1)).ravel()

gkf_iter = GroupKFold(n_splits=5)
oof_iter = np.full(len(y_train_pool), np.nan)
importances_iter = np.zeros(len(iter_features))

for fold_i, (train_idx, val_idx) in enumerate(gkf_iter.split(X_opt, y_t_iter, groups_train_pool)):
    dtrain = lgb.Dataset(X_opt[train_idx], label=y_t_iter[train_idx], feature_name=iter_features)
    dval = lgb.Dataset(X_opt[val_idx], label=y_t_iter[val_idx], feature_name=iter_features, reference=dtrain)

    model_iter = lgb.train(
        best_params, dtrain,
        num_boost_round=500,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    pred_t = model_iter.predict(X_opt[val_idx])
    oof_iter[val_idx] = yt_iter.inverse_transform(pred_t.reshape(-1, 1)).ravel()
    importances_iter += model_iter.feature_importance(importance_type="gain")

    fold_r2 = r2_score(y_opt_clip[val_idx], oof_iter[val_idx])
    val_groups = groups_train_pool[val_idx]
    print(f"  Fold {fold_i+1}: R2={fold_r2:.3f}, years={sorted(np.unique(val_groups).tolist())}")

importances_iter /= 5
valid_iter = ~np.isnan(oof_iter)

r2_iter = r2_score(y_opt_clip[valid_iter], oof_iter[valid_iter])
mae_iter = mean_absolute_error(y_opt_clip[valid_iter], oof_iter[valid_iter])
spearman_iter, _ = spearmanr(y_opt_clip[valid_iter], oof_iter[valid_iter])

print(f"\nIterated model: R2={r2_iter:.3f}, MAE={mae_iter:.4f}, Spearman={spearman_iter:.3f}")
print(f"Features: {len(iter_features)}")

# Compare to pre-iteration
print(f"\n--- Comparison ---")
print(f"{'Metric':>20s} {'Phase 10':>10s} {'Phase 12':>10s} {'Delta':>10s}")
print(f"{'R2':>20s} {overall_r2:10.3f} {r2_iter:10.3f} {r2_iter - overall_r2:+10.3f}")
print(f"{'MAE':>20s} {overall_mae:10.4f} {mae_iter:10.4f} {mae_iter - overall_mae:+10.4f}")
print(f"{'Spearman':>20s} {rank_corr:10.3f} {spearman_iter:10.3f} {spearman_iter - rank_corr:+10.3f}")
print(f"{'n_sets':>20s} {valid.sum():10d} {valid_iter.sum():10d}")
print(f"{'n_features':>20s} {len(final_features):10d} {len(iter_features):10d}")

# Feature importance
print("\nFeature importance (gain):")
imp_order_iter = np.argsort(-importances_iter)
for rank, idx in enumerate(imp_order_iter):
    if importances_iter[idx] < 1:
        break
    print(f"  {rank+1:2d}. {iter_features[idx]:40s} gain={importances_iter[idx]:10.1f}")

# Quintile analysis on iterated model
print("\n--- Quintile Separation (iterated) ---")
df_tp = df_train_pool.copy()
df_tp["oof_iter"] = oof_iter
df_tp["y_clip"] = y_opt_clip
df_valid_iter = df_tp[valid_iter]

for qlabel, lo_q, hi_q in [("Bottom 20%", 0, 20), ("Q2", 20, 40), ("Q3", 40, 60),
                             ("Q4", 60, 80), ("Top 20%", 80, 100)]:
    lo_th = np.percentile(df_valid_iter["oof_iter"], lo_q)
    hi_th = np.percentile(df_valid_iter["oof_iter"], hi_q)
    mask_q = (df_valid_iter["oof_iter"] >= lo_th) & (df_valid_iter["oof_iter"] < hi_th + 0.001)
    grp = df_valid_iter[mask_q]
    if len(grp) > 0:
        print(f"  {qlabel:12s}: pred_mean={grp['oof_iter'].mean():.3f}, actual_mean={grp['y_clip'].mean():.3f}, n={len(grp)}")

# Failure mode re-check: false positive themes
print("\n--- False Positive Theme Check (iterated) ---")
for theme in sorted(FALSE_POS_THEMES):
    grp = df_valid_iter[df_valid_iter["theme"] == theme]
    if len(grp) < 3:
        continue
    bias = (grp["oof_iter"] - grp["y_clip"]).mean()
    mae_t = (grp["oof_iter"] - grp["y_clip"]).abs().mean()
    print(f"  {theme:20s}: n={len(grp):3d}, bias={bias:+.3f}, MAE={mae_t:.3f}")

# 2025 holdout performance
print("\n--- 2025+ Holdout (out-of-sample) ---")
if len(df_2025_holdout) > 10:
    X_holdout = df_2025_holdout[iter_features].fillna(0).values.astype(float)
    y_holdout = df_2025_holdout[target_col_fs].values.astype(float)
    lo_h, hi_h = np.percentile(y_holdout, [2, 98])
    y_holdout_clip = np.clip(y_holdout, lo_h, hi_h)

    # Train on full training pool, predict holdout
    yt_full = PowerTransformer(method="yeo-johnson")
    y_t_full = yt_full.fit_transform(y_opt_clip.reshape(-1, 1)).ravel()
    dtrain_full = lgb.Dataset(X_opt, label=y_t_full, feature_name=iter_features)
    model_full = lgb.train(
        best_params, dtrain_full, num_boost_round=model_iter.best_iteration or 200,
    )
    pred_holdout_t = model_full.predict(X_holdout)
    pred_holdout = yt_full.inverse_transform(pred_holdout_t.reshape(-1, 1)).ravel()

    r2_holdout = r2_score(y_holdout_clip, pred_holdout)
    mae_holdout = mean_absolute_error(y_holdout_clip, pred_holdout)
    sp_holdout, _ = spearmanr(y_holdout_clip, pred_holdout)
    print(f"  2025+ holdout: n={len(df_2025_holdout)}, R2={r2_holdout:.3f}, "
          f"MAE={mae_holdout:.4f}, Spearman={sp_holdout:.3f}")

print(f"\nTotal time: {time.time() - t0:.1f}s")
