"""Experiment 36: Retail-window demand signals.

Test two new feature groups against the 36-feature KEEPA_BL_FEATURES baseline:

  GROUP A: Refined discount-during-retail variants (re-test of the rejected
           BrickTalk hypothesis with depth-weighted, time-windowed,
           in-stock-aware definitions).
  GROUP B: OOS-timing features (productionize the prototype from Exp 31 that
           was never carried forward).

Hypothesis: while a set is still in retail, weak demand should manifest as
either (a) frequent / deep / recent markdowns, or (b) the absence of OOS
episodes (Amazon never runs out because units don't move). Both signals are
available from the Keepa amazon_price timeline cut at retired_date.

All features use rrp_usd_cents from BrickEconomy and the Amazon 1P timeline
trimmed at retired_date — no lookahead.

Run: python -m research.growth.36_retail_demand_signals
"""
from __future__ import annotations

import time
import warnings
from datetime import timedelta

warnings.filterwarnings("ignore")

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

print("=" * 70)
print("EXP 36: RETAIL-WINDOW DEMAND SIGNALS")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.growth.keepa_features import (
    CLASSIFIER_FEATURES,
    GT_FEATURES,
    KEEPA_BL_FEATURES,
    _parse_date,
    _parse_timeline,
    compute_theme_keepa_stats,
    encode_theme_keepa_features,
    engineer_gt_features,
    engineer_keepa_bl_features,
)
from services.ml.growth.model_selection import clip_outliers
from services.ml.pg_queries import (
    load_bl_ground_truth,
    load_google_trends_data,
    load_keepa_bl_training_data,
    _read,
)

engine = get_engine()

# ============================================================================
# PHASE 0: DATA LOADING (mirror Exp 34)
# ============================================================================
print("\n--- Phase 0: Data Loading ---")
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
bl_target = load_bl_ground_truth(engine)
gt_df = load_google_trends_data(engine)

print(f"Base: {len(base_df)}, Keepa: {len(keepa_df)}, Targets: {len(target_series)}")
print(f"BL ground truth: {len(bl_target)} sets")

# Regional RRP (needed for the 35-feature baseline that Exp 34 added)
regional_df = _read(engine, """
    SELECT set_number, rrp_gbp_cents, rrp_eur_cents,
           rrp_cad_cents, rrp_aud_cents
    FROM (
        SELECT DISTINCT ON (set_number) *
        FROM brickeconomy_snapshots
        ORDER BY set_number, scraped_at DESC
    ) be
    WHERE be.rrp_usd_cents > 0
""")
base_df = base_df.merge(regional_df, on="set_number", how="left")

# Engineer baseline features
df_feat = engineer_keepa_bl_features(base_df, keepa_df)

# Add theme encoding
theme_stats = compute_theme_keepa_stats(df_feat)
df_feat = encode_theme_keepa_features(df_feat, theme_stats=theme_stats, training=True)

# Merge GT features
gt_feat = engineer_gt_features(gt_df, base_df)
df_feat = df_feat.merge(gt_feat, on="set_number", how="left")
for col in GT_FEATURES:
    if col not in df_feat.columns:
        df_feat[col] = 0.0
    else:
        df_feat[col] = df_feat[col].fillna(0.0)

# Year retired + per-set lookups
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
rrp_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_usd_cents")))
retired_date_map = dict(zip(base_df["set_number"].astype(str), base_df.get("retired_date")))

for _, row in base_df.iterrows():
    sn = str(row["set_number"])
    if sn not in yr_map or pd.isna(yr_map.get(sn)):
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            yr_map[sn] = rd.year

df_feat["year_retired"] = df_feat["set_number"].map(yr_map).fillna(2023).astype(int)

# Map BL ground truth
df_feat["bl_ann_return"] = df_feat["set_number"].map(bl_target)
df_feat = df_feat[df_feat["bl_ann_return"].notna()].copy()

# Training set: retired <= 2024
train_mask = df_feat["year_retired"] <= 2024
df_train = df_feat[train_mask].copy()
print(f"\nTraining sets with BL ground truth: {len(df_train)} (retired <= 2024)")
print(f"Baseline features: {len(list(CLASSIFIER_FEATURES))}")

# ============================================================================
# PHASE 1: ENGINEER NEW FEATURES
# ============================================================================
print("\n--- Phase 1: Engineer New Features ---")

# Build keepa lookup for re-parsing timelines
keepa_lookup: dict[str, pd.Series] = {}
for _, row in keepa_df.iterrows():
    keepa_lookup[str(row["set_number"])] = row


# Threshold for "discounted": price below 95% of US RRP (5% off — slightly looser
# than the existing amz_never_discounted 98% threshold so we capture genuine
# discounts and not measurement noise).
DISCOUNT_THRESHOLD = 0.95


def compute_new_features(sn: str) -> dict[str, float]:
    """Compute all 8 new features for a single set.

    Returns a dict keyed by feature name. Missing features (insufficient data)
    are simply omitted; the caller fills with 0.
    """
    rec: dict[str, float] = {}

    kp = keepa_lookup.get(sn)
    if kp is None:
        return rec

    rrp_cents = float(rrp_map.get(sn, 0) or 0)
    if rrp_cents <= 0:
        return rec
    rrp = rrp_cents  # Amazon timeline is also in cents

    rd = _parse_date(str(retired_date_map.get(sn, "")))
    if rd is None or rd is pd.NaT:
        return rec
    retired_str = rd.strftime("%Y-%m-%d")
    retire_minus_6mo_str = (rd - timedelta(days=182)).strftime("%Y-%m-%d")
    retire_minus_12mo_str = (rd - timedelta(days=365)).strftime("%Y-%m-%d")

    amz_raw = _parse_timeline(kp.get("amazon_price_json"))
    amz = [
        p for p in amz_raw
        if len(p) >= 2 and isinstance(p[0], str) and p[0] <= retired_str
    ]
    if len(amz) < 3:
        return rec

    # In-stock points (Amazon 1P) — only these count for discount denominators
    in_stock = [p for p in amz if p[1] is not None and float(p[1]) > 0]
    n_in_stock = len(in_stock)

    # ------------------------------------------------------------------
    # GROUP A: Refined discount-during-retail variants
    # ------------------------------------------------------------------
    if n_in_stock >= 3:
        prices = [float(p[1]) for p in in_stock]
        n_below = sum(1 for p in prices if p < rrp * DISCOUNT_THRESHOLD)
        pct_below = n_below / n_in_stock * 100

        # Average discount magnitude across ALL in-stock days (0 when at RRP)
        avg_disc_all = float(np.mean([
            max(0.0, (rrp - p) / rrp * 100) for p in prices
        ]))
        # depth × frequency composite
        rec["amz_discount_depth_x_freq"] = avg_disc_all * pct_below

        # Average discount magnitude WHEN discounted (depth isolated)
        if n_below > 0:
            below_prices = [p for p in prices if p < rrp * DISCOUNT_THRESHOLD]
            rec["amz_avg_discount_when_discounted"] = float(np.mean([
                (rrp - p) / rrp * 100 for p in below_prices
            ]))

        # Distinct discount episodes (price drops below threshold and recovers)
        episode_count = 0
        in_episode = False
        for p in prices:
            below = p < rrp * DISCOUNT_THRESHOLD
            if below and not in_episode:
                episode_count += 1
                in_episode = True
            elif not below:
                in_episode = False
        rec["amz_discount_episodes"] = float(episode_count)

    # Last-6mo and last-12mo discount frequency (in-stock days only)
    in_stock_last_6mo = [
        p for p in in_stock if p[0] >= retire_minus_6mo_str
    ]
    in_stock_last_12mo = [
        p for p in in_stock if p[0] >= retire_minus_12mo_str
    ]

    if len(in_stock_last_6mo) >= 3:
        prices_6mo = [float(p[1]) for p in in_stock_last_6mo]
        n_disc = sum(1 for p in prices_6mo if p < rrp * DISCOUNT_THRESHOLD)
        rec["amz_discount_pct_last_6mo"] = n_disc / len(prices_6mo) * 100

    if len(in_stock_last_12mo) >= 3:
        prices_12mo = [float(p[1]) for p in in_stock_last_12mo]
        n_disc = sum(1 for p in prices_12mo if p < rrp * DISCOUNT_THRESHOLD)
        rec["amz_discount_pct_last_12mo"] = n_disc / len(prices_12mo) * 100

    # ------------------------------------------------------------------
    # GROUP B: OOS-timing features (from Exp 31:280-327)
    # ------------------------------------------------------------------
    # Build OOS / in-stock episodes
    oos_episodes: list[dict] = []
    in_stock_episodes: list[dict] = []
    current_ep: dict | None = None
    for point in amz:
        is_oos = point[1] is None or float(point[1]) <= 0
        if current_ep is None:
            current_ep = {"start": point[0], "end": point[0], "oos": is_oos}
        elif is_oos == current_ep["oos"]:
            current_ep["end"] = point[0]
        else:
            (oos_episodes if current_ep["oos"] else in_stock_episodes).append(current_ep)
            current_ep = {"start": point[0], "end": point[0], "oos": is_oos}
    if current_ep is not None:
        (oos_episodes if current_ep["oos"] else in_stock_episodes).append(current_ep)

    if oos_episodes:
        first_oos_dt = pd.to_datetime(oos_episodes[0]["start"], errors="coerce")
        if first_oos_dt is not pd.NaT:
            rec["amz_first_oos_months_before_retire"] = float(
                (rd - first_oos_dt).days / 30.44
            )

        last_oos = oos_episodes[-1]
        last_oos_end_dt = pd.to_datetime(last_oos["end"], errors="coerce")
        if last_oos_end_dt is not pd.NaT:
            rec["amz_final_oos_to_retire_days"] = float((rd - last_oos_end_dt).days)

        # Did Amazon restock after the final OOS? If not, supply was exhausted.
        last_oos_end_date = last_oos["end"]
        restocked = any(
            ist["start"] > last_oos_end_date for ist in in_stock_episodes
        )
        rec["amz_restocked_after_final_oos"] = 1.0 if restocked else 0.0

    return rec


GROUP_A = [
    "amz_discount_depth_x_freq",
    "amz_avg_discount_when_discounted",
    "amz_discount_episodes",
    "amz_discount_pct_last_6mo",
    "amz_discount_pct_last_12mo",
]
GROUP_B = [
    "amz_first_oos_months_before_retire",
    "amz_final_oos_to_retire_days",
    "amz_restocked_after_final_oos",
]
ALL_NEW = GROUP_A + GROUP_B

# Compute features for every training row
print(f"  Computing {len(ALL_NEW)} new features for {len(df_train)} sets...")
new_records: list[dict] = []
for sn in df_train["set_number"].astype(str):
    rec = compute_new_features(sn)
    rec["set_number"] = sn
    new_records.append(rec)

new_df = pd.DataFrame(new_records)
for col in ALL_NEW:
    if col in new_df.columns:
        df_train[col] = (
            new_df.set_index("set_number")
            .reindex(df_train["set_number"].astype(str).values)[col]
            .values
        )
    else:
        df_train[col] = np.nan
    df_train[col] = df_train[col].fillna(0)

# Coverage report
print(f"\n  GROUP A: refined discount variants")
for f in GROUP_A:
    nonzero = (df_train[f] != 0).sum()
    print(f"    {f:38s}  {nonzero:4d}/{len(df_train)} non-zero ({nonzero / len(df_train) * 100:.1f}%)")

print(f"\n  GROUP B: OOS-timing features")
for f in GROUP_B:
    nonzero = (df_train[f] != 0).sum()
    print(f"    {f:38s}  {nonzero:4d}/{len(df_train)} non-zero ({nonzero / len(df_train) * 100:.1f}%)")

# ============================================================================
# PHASE 2: DIAGNOSTICS (Spearman + MI vs both classifier targets)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 2: FEATURE DIAGNOSTICS")
print("=" * 70)

y_ann = df_train["bl_ann_return"].values.astype(float)
y_avoid = (y_ann < 8.0).astype(int)
y_great = (y_ann >= 20.0).astype(int)

print(f"\nTarget distribution: avoid={y_avoid.sum()}/{len(y_avoid)} "
      f"({y_avoid.mean() * 100:.1f}%), "
      f"great_buy={y_great.sum()}/{len(y_great)} ({y_great.mean() * 100:.1f}%)")

print(f"\n{'Feature':38s} {'Cov%':>5s} {'Sprmn':>8s} {'MI_avd':>7s} {'MI_gb':>7s} "
      f"{'p25':>8s} {'p50':>8s} {'p75':>8s} {'p90':>8s}")
print("-" * 110)

for feat in ALL_NEW:
    vals = df_train[feat].values.astype(float)
    nonzero_mask = (vals != 0) & np.isfinite(vals)
    coverage = nonzero_mask.sum() / len(vals) * 100

    if nonzero_mask.sum() < 30:
        print(f"{feat:38s} {coverage:5.1f}  (too few non-zero)")
        continue

    sp, _ = spearmanr(vals[nonzero_mask], y_ann[nonzero_mask])

    vals_finite = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
    vals_2d = vals_finite.reshape(-1, 1)
    mi_avoid = mutual_info_classif(vals_2d, y_avoid, random_state=42, n_neighbors=5)[0]
    mi_great = mutual_info_classif(vals_2d, y_great, random_state=42, n_neighbors=5)[0]

    p25, p50, p75, p90 = np.nanpercentile(vals[nonzero_mask], [25, 50, 75, 90])
    print(f"{feat:38s} {coverage:5.1f} {sp:+.4f} {mi_avoid:.4f} {mi_great:.4f} "
          f"{p25:8.3f} {p50:8.3f} {p75:8.3f} {p90:8.3f}")

# ============================================================================
# PHASE 3: GROUPKFOLD CV (mirror Exp 34)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 3: GROUPKFOLD CV")
print("=" * 70)

baseline_features = [f for f in CLASSIFIER_FEATURES if f in df_train.columns]
print(f"Baseline features available: {len(baseline_features)} / {len(CLASSIFIER_FEATURES)}")

groups = df_train["year_retired"].values
n_splits = min(5, len(np.unique(groups)))
gkf = GroupKFold(n_splits=n_splits)

CLF_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "max_depth": 4,
    "min_child_samples": 10,
    "is_unbalance": True,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "verbosity": -1,
}


def run_clf_cv(
    feature_names: list[str],
    threshold: float = 8.0,
    invert: bool = False,
) -> float:
    """Run GroupKFold CV for a binary classifier, return AUC."""
    X_raw = df_train[feature_names].fillna(0).copy()
    X_arr = clip_outliers(X_raw).values.astype(float)

    y_binary = (y_ann >= threshold).astype(int) if invert else (y_ann < threshold).astype(int)

    oof = np.full(len(y_binary), np.nan)
    for tr_idx, va_idx in gkf.split(X_arr, y_binary, groups):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_arr[tr_idx])
        X_va = scaler.transform(X_arr[va_idx])
        clf = lgb.LGBMClassifier(n_estimators=200, **CLF_PARAMS, random_state=42, n_jobs=1)
        clf.fit(X_tr, y_binary[tr_idx])
        oof[va_idx] = clf.predict_proba(X_va)[:, 1]

    valid = ~np.isnan(oof)
    return roc_auc_score(y_binary[valid], oof[valid])


configs: dict[str, list[str]] = {
    "BASELINE": baseline_features,
    "+each_A_individually": [],  # placeholder, handled below
}

# Per-feature add (each feature alone on top of baseline)
print(f"\n{'Config':45s} {'#Feat':>6s} {'Avoid AUC':>10s} {'dAvoid':>8s} {'GB AUC':>10s} {'dGB':>8s}")
print("-" * 95)

baseline_avoid = run_clf_cv(baseline_features, threshold=8.0, invert=False)
baseline_gb = run_clf_cv(baseline_features, threshold=20.0, invert=True)
print(f"{'BASELINE':45s} {len(baseline_features):6d} {baseline_avoid:10.4f} "
      f"{0.0:+8.4f} {baseline_gb:10.4f} {0.0:+8.4f}")

results: list[dict] = []
results.append({
    "config": "BASELINE", "n_feat": len(baseline_features),
    "avoid_auc": baseline_avoid, "gb_auc": baseline_gb,
    "d_avoid": 0.0, "d_gb": 0.0,
})

for feat in ALL_NEW:
    feats = baseline_features + [feat]
    avoid_auc = run_clf_cv(feats, threshold=8.0, invert=False)
    gb_auc = run_clf_cv(feats, threshold=20.0, invert=True)
    d_avoid = avoid_auc - baseline_avoid
    d_gb = gb_auc - baseline_gb
    group_tag = "[A]" if feat in GROUP_A else "[B]"
    results.append({
        "config": f"+{feat}", "n_feat": len(feats),
        "avoid_auc": avoid_auc, "gb_auc": gb_auc,
        "d_avoid": d_avoid, "d_gb": d_gb,
    })
    print(f"{group_tag} +{feat:40s} {len(feats):6d} {avoid_auc:10.4f} {d_avoid:+8.4f} "
          f"{gb_auc:10.4f} {d_gb:+8.4f}")

# Cumulative groups
for label, feats_to_add in [
    ("+GROUP_A (all 5 discount)", GROUP_A),
    ("+GROUP_B (all 3 OOS-timing)", GROUP_B),
    ("+ALL_NEW (A+B)", ALL_NEW),
]:
    feats = baseline_features + feats_to_add
    avoid_auc = run_clf_cv(feats, threshold=8.0, invert=False)
    gb_auc = run_clf_cv(feats, threshold=20.0, invert=True)
    d_avoid = avoid_auc - baseline_avoid
    d_gb = gb_auc - baseline_gb
    results.append({
        "config": label, "n_feat": len(feats),
        "avoid_auc": avoid_auc, "gb_auc": gb_auc,
        "d_avoid": d_avoid, "d_gb": d_gb,
    })
    print(f"{label:45s} {len(feats):6d} {avoid_auc:10.4f} {d_avoid:+8.4f} "
          f"{gb_auc:10.4f} {d_gb:+8.4f}")

# ============================================================================
# PHASE 4: REDUNDANCY CHECK (correlation with existing features)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: REDUNDANCY (correlation with closest existing feature)")
print("=" * 70)

# Closest related existing features for each new one
related = {
    "amz_discount_depth_x_freq":          ["amz_max_discount_pct", "amz_never_discounted"],
    "amz_avg_discount_when_discounted":   ["amz_max_discount_pct", "amz_discount_trend"],
    "amz_discount_episodes":              ["amz_max_restock_delay_days"],
    "amz_discount_pct_last_6mo":          ["amz_max_discount_pct", "amz_discount_trend"],
    "amz_discount_pct_last_12mo":         ["amz_max_discount_pct", "amz_discount_trend"],
    "amz_first_oos_months_before_retire": ["amz_max_restock_delay_days"],
    "amz_final_oos_to_retire_days":       ["amz_max_restock_delay_days"],
    "amz_restocked_after_final_oos":      ["amz_max_restock_delay_days"],
}

print(f"\n{'Feature':38s} {'vs existing':38s} {'Pearson r':>10s}")
print("-" * 90)
for feat in ALL_NEW:
    new_vals = df_train[feat].astype(float).fillna(0).values
    for ex in related.get(feat, []):
        if ex not in df_train.columns:
            continue
        ex_vals = df_train[ex].astype(float).fillna(0).values
        if np.std(new_vals) == 0 or np.std(ex_vals) == 0:
            r = float("nan")
        else:
            r = float(np.corrcoef(new_vals, ex_vals)[0, 1])
        flag = "  REDUNDANT" if not np.isnan(r) and abs(r) > 0.85 else ""
        print(f"{feat:38s} {ex:38s} {r:+10.4f}{flag}")

# ============================================================================
# PHASE 5: LOFO ABLATION on +ALL_NEW (do new features carry their weight?)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 5: LOFO ABLATION on +ALL_NEW")
print("=" * 70)

all_new_feats = baseline_features + ALL_NEW
all_avoid = run_clf_cv(all_new_feats, threshold=8.0, invert=False)
all_gb = run_clf_cv(all_new_feats, threshold=20.0, invert=True)
print(f"\n+ALL_NEW reference: Avoid={all_avoid:.4f}, GB={all_gb:.4f}")
print(f"\n{'Removed':38s} {'Avoid':>10s} {'dAvoid':>9s} {'GB':>10s} {'dGB':>9s} {'Verdict':>9s}")
print("-" * 90)

for feat in ALL_NEW:
    reduced = [f for f in all_new_feats if f != feat]
    avoid_auc = run_clf_cv(reduced, threshold=8.0, invert=False)
    gb_auc = run_clf_cv(reduced, threshold=20.0, invert=True)
    d_avoid = avoid_auc - all_avoid
    d_gb = gb_auc - all_gb
    # Removing helps the model => feature was hurting; removing hurts => feature was helping
    verdict = (
        "HELPS" if (d_avoid < -0.002 or d_gb < -0.002)
        else ("HURTS" if (d_avoid > 0.002 or d_gb > 0.002) else "NEUTRAL")
    )
    print(f"{feat:38s} {avoid_auc:10.4f} {d_avoid:+9.4f} {gb_auc:10.4f} {d_gb:+9.4f} {verdict:>9s}")

# ============================================================================
# PHASE 6: FORWARD SELECTION
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: FORWARD SELECTION (greedy)")
print("=" * 70)

selected: list[str] = []
remaining = list(ALL_NEW)
current_avoid = baseline_avoid
current_gb = baseline_gb

print(f"\nStarting from baseline: Avoid={current_avoid:.4f}, GB={current_gb:.4f}")

for step in range(len(ALL_NEW)):
    best_feat = None
    best_score = -1.0
    best_avoid = current_avoid
    best_gb = current_gb

    for feat in remaining:
        trial_feats = baseline_features + selected + [feat]
        avoid_auc = run_clf_cv(trial_feats, threshold=8.0, invert=False)
        gb_auc = run_clf_cv(trial_feats, threshold=20.0, invert=True)
        score = (avoid_auc - current_avoid) + (gb_auc - current_gb)
        if score > best_score:
            best_score = score
            best_feat = feat
            best_avoid = avoid_auc
            best_gb = gb_auc

    if best_score < 0.003:
        print(f"\n  Step {step + 1}: best candidate '{best_feat}' adds "
              f"{best_score:+.4f} (< 0.003 threshold). STOPPING.")
        break

    selected.append(best_feat)
    remaining.remove(best_feat)
    current_avoid = best_avoid
    current_gb = best_gb
    group = "A" if best_feat in GROUP_A else "B"
    print(f"  Step {step + 1}: [{group}] +{best_feat:35s}  "
          f"Avoid={best_avoid:.4f} ({best_avoid - baseline_avoid:+.4f})  "
          f"GB={best_gb:.4f} ({best_gb - baseline_gb:+.4f})  "
          f"combined={best_score:+.4f}")

print(f"\nForward-selected ({len(selected)}):")
for f in selected:
    group = "A" if f in GROUP_A else "B"
    print(f"  [{group}] {f}")

# ============================================================================
# PHASE 7: SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("EXPERIMENT 36: SUMMARY")
print("=" * 70)
print(f"\nBaseline ({len(baseline_features)} features): "
      f"Avoid AUC={baseline_avoid:.4f}, GB AUC={baseline_gb:.4f}")

print(f"\nPer-feature deltas vs baseline:")
for r in results:
    if r["config"] == "BASELINE":
        continue
    sign_a = "+" if r["d_avoid"] > 0.003 else ("-" if r["d_avoid"] < -0.003 else "=")
    sign_g = "+" if r["d_gb"] > 0.003 else ("-" if r["d_gb"] < -0.003 else "=")
    print(f"  {r['config']:45s}  Avoid {sign_a}{r['d_avoid']:+.4f}  GB {sign_g}{r['d_gb']:+.4f}")

print(f"\nForward-selected for productionization: {selected}")
print(f"Total features after integration: {len(baseline_features) + len(selected)}")

# Acceptance bar reminder
print("\nAcceptance bar (per plan):")
print("  - dAUC >= +0.005 on either head AND positive LOFO contribution")
print("  - AND |corr| < 0.85 with any existing feature (Phase 4)")

elapsed = time.time() - t0
print(f"\nTime: {elapsed:.1f}s")
