"""Experiment 35: Phase-aware features, composite signals, and pricing risk.

Evaluate 4 groups of features against the 39-feature baseline (Exp 34):
  A) Phase Transition: early-vs-late comparisons for 3P, buy box, cross-channel spread
  B) Relative Signal: set's signals compared to theme LOO averages ("already priced in")
  C) Composite Signals: explicit multi-condition products of top features
  D) Demand Intensity: review velocity normalized by shelf life / price

Run: python -m research.growth.35_phase_composites
"""
from __future__ import annotations

import time
import warnings

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
print("EXP 35: PHASE-AWARE FEATURES, COMPOSITES, AND PRICING RISK")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.encodings import compute_group_stats, loo_bayesian_encode
from services.ml.growth.keepa_features import (
    CLASSIFIER_FEATURES,
    GT_FEATURES,
    _parse_date,
    _parse_timeline,
    compute_regional_stats,
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
)

engine = get_engine()

# ============================================================================
# PHASE 0: DATA LOADING
# ============================================================================
print("\n--- Phase 0: Data Loading ---")
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
bl_target = load_bl_ground_truth(engine)
gt_df = load_google_trends_data(engine)

print(f"Base: {len(base_df)}, Keepa: {len(keepa_df)}, Targets: {len(target_series)}")
print(f"BL ground truth: {len(bl_target)} sets")

# Engineer baseline 39 features (Exp 34)
df_feat = engineer_keepa_bl_features(base_df, keepa_df)

# Theme encoding (Exp 33)
theme_stats = compute_theme_keepa_stats(df_feat)
df_feat = encode_theme_keepa_features(df_feat, theme_stats=theme_stats, training=True)

# Regional stats (Exp 34)
regional_stats = compute_regional_stats(base_df)
theme_stats["regional_stats"] = regional_stats

# GT features
gt_feat = engineer_gt_features(gt_df, base_df)
df_feat = df_feat.merge(gt_feat, on="set_number", how="left")
for col in GT_FEATURES:
    if col not in df_feat.columns:
        df_feat[col] = 0.0
    else:
        df_feat[col] = df_feat[col].fillna(0.0)

# Metadata lookups
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
rrp_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_usd_cents")))
theme_map = dict(zip(base_df["set_number"].astype(str), base_df.get("theme")))
retired_date_map = dict(zip(base_df["set_number"].astype(str), base_df.get("retired_date")))
release_date_map = dict(zip(base_df["set_number"].astype(str), base_df.get("release_date")))

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

# Build keepa lookup for timeline re-parsing
keepa_lookup: dict[str, pd.Series] = {}
for _, row in keepa_df.iterrows():
    keepa_lookup[str(row["set_number"])] = row


# ---- GROUP A: Phase Transition Features ----
print("\n  Group A: Phase Transition Features")

phase_records: list[dict] = []
for _, row in df_train.iterrows():
    sn = str(row["set_number"])
    kp = keepa_lookup.get(sn)
    rec: dict[str, float] = {"set_number": sn}

    if kp is None:
        phase_records.append(rec)
        continue

    rrp = float(rrp_map.get(sn, 0) or 0)
    if rrp <= 0:
        phase_records.append(rec)
        continue

    retired_str = None
    rd = _parse_date(str(retired_date_map.get(sn, "")))
    if rd and rd is not pd.NaT:
        try:
            retired_str = rd.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass

    def _cut(tl: list[list]) -> list[list]:
        if not retired_str:
            return tl
        return [p for p in tl if len(p) >= 2 and isinstance(p[0], str) and p[0] <= retired_str]

    amz_raw = _parse_timeline(kp.get("amazon_price_json"))
    fba_raw = _parse_timeline(kp.get("new_3p_fba_json"))
    bb_raw = _parse_timeline(kp.get("buy_box_json"))

    amz = _cut(amz_raw)
    fba = _cut(fba_raw)
    bb = _cut(bb_raw)

    amz_prices = [float(p[1]) for p in amz if p[1] is not None and p[1] > 0]
    fba_prices = [float(p[1]) for p in fba if p[1] is not None and p[1] > 0]
    bb_prices = [float(p[1]) for p in bb if p[1] is not None and p[1] > 0]

    # Feature 1: FBA premium late vs early
    if len(fba_prices) >= 6:
        half = len(fba_prices) // 2
        early_fba_mean = float(np.mean(fba_prices[:half]))
        late_fba_mean = float(np.mean(fba_prices[half:]))
        if early_fba_mean > 0:
            rec["fba_prem_late_vs_early"] = late_fba_mean / early_fba_mean

    # Feature 2: Cross-channel spread late vs early
    # (FBA/AMZ ratio in late half) / (FBA/AMZ ratio in early half)
    if len(fba_prices) >= 6 and len(amz_prices) >= 6:
        fba_half = len(fba_prices) // 2
        amz_half = len(amz_prices) // 2
        early_fba = float(np.mean(fba_prices[:fba_half]))
        late_fba = float(np.mean(fba_prices[fba_half:]))
        early_amz = float(np.mean(amz_prices[:amz_half]))
        late_amz = float(np.mean(amz_prices[amz_half:]))
        if early_amz > 0 and early_fba > 0 and late_amz > 0:
            early_spread = early_fba / early_amz
            late_spread = late_fba / late_amz
            if early_spread > 0:
                rec["spread_late_vs_early"] = late_spread / early_spread

    # Feature 3: FBA CV late vs early (stabilizing prices = convergence)
    if len(fba_prices) >= 10:
        half = len(fba_prices) // 2
        early_arr = np.array(fba_prices[:half])
        late_arr = np.array(fba_prices[half:])
        early_mean = float(early_arr.mean())
        late_mean = float(late_arr.mean())
        cv_early = float(early_arr.std() / early_mean) if early_mean > 0 else 0
        cv_late = float(late_arr.std() / late_mean) if late_mean > 0 else 0
        if cv_early > 0:
            rec["fba_cv_late_vs_early"] = cv_late / cv_early

    # Feature 4: Buy box late share (activity near EOL)
    if len(bb_prices) >= 4:
        half = len(bb_prices) // 2
        late_count = len(bb_prices) - half
        rec["buybox_late_share"] = late_count / len(bb_prices)

    # Feature 5: Discount deepening (late max discount / early max discount)
    if len(amz_prices) >= 6 and rrp > 0:
        half = len(amz_prices) // 2
        early_max_disc = (rrp - min(amz_prices[:half])) / rrp * 100
        late_max_disc = (rrp - min(amz_prices[half:])) / rrp * 100
        if early_max_disc > 0.5:  # avoid div-by-zero for never-discounted sets
            rec["discount_deepening"] = late_max_disc / early_max_disc
        elif late_max_disc > 0.5:
            rec["discount_deepening"] = 2.0  # late discount but no early = strong deepening
        # else: both near zero = no discount = leave as NaN

    phase_records.append(rec)

phase_df = pd.DataFrame(phase_records)
GROUP_A = ["fba_prem_late_vs_early", "spread_late_vs_early", "fba_cv_late_vs_early",
           "buybox_late_share", "discount_deepening"]
for col in GROUP_A:
    if col in phase_df.columns:
        df_train[col] = phase_df.set_index("set_number").reindex(df_train["set_number"].values)[col].values
    else:
        df_train[col] = np.nan
    df_train[col] = df_train[col].fillna(0)

a_cov = {f: (df_train[f] != 0).sum() for f in GROUP_A}
print(f"    Features: {GROUP_A}")
print(f"    Coverage (non-zero): {a_cov}")

# Collinearity check with existing amz_discount_trend
if "amz_discount_trend" in df_train.columns:
    for f in GROUP_A:
        vals = df_train[f].values.astype(float)
        adt = df_train["amz_discount_trend"].values.astype(float)
        mask = (vals != 0) & np.isfinite(vals) & np.isfinite(adt)
        if mask.sum() > 30:
            corr = np.corrcoef(vals[mask], adt[mask])[0, 1]
            print(f"    Pearson({f}, amz_discount_trend) = {corr:.3f}")


# ---- GROUP B: Relative Signal ("Already Priced In") ----
print("\n  Group B: Relative Signal ('Already Priced In')")

# Add theme column for grouping
df_train["_theme"] = df_train["set_number"].map(theme_map).fillna("")

# LOO Bayesian encode: 3p_above_rrp_pct relative to theme
prem_col = "3p_above_rrp_pct"
if prem_col in df_train.columns:
    prem_vals = df_train[prem_col].fillna(0).astype(float)
    prem_stats = compute_group_stats(df_train, "_theme", prem_vals)
    theme_avg_prem = loo_bayesian_encode(df_train["_theme"], prem_vals, prem_stats, alpha=20)
    df_train["3p_prem_vs_theme"] = prem_vals - theme_avg_prem
    # Store stats for CV re-encoding
    _prem_stats_global = prem_stats
else:
    df_train["3p_prem_vs_theme"] = 0.0

# LOO Bayesian encode: log1p(amz_review_count) relative to theme
rev_col = "amz_review_count"
if rev_col in df_train.columns:
    log_rev = np.log1p(df_train[rev_col].fillna(0).astype(float))
    rev_stats = compute_group_stats(df_train, "_theme", log_rev)
    theme_avg_rev = loo_bayesian_encode(df_train["_theme"], log_rev, rev_stats, alpha=20)
    df_train["reviews_vs_theme"] = log_rev - theme_avg_rev
    _rev_stats_global = rev_stats
else:
    df_train["reviews_vs_theme"] = 0.0

# LOO Bayesian encode: buybox_premium_avg relative to theme
bb_col = "buybox_premium_avg"
if bb_col in df_train.columns:
    bb_vals = df_train[bb_col].fillna(0).astype(float)
    bb_stats = compute_group_stats(df_train, "_theme", bb_vals)
    theme_avg_bb = loo_bayesian_encode(df_train["_theme"], bb_vals, bb_stats, alpha=20)
    df_train["buybox_vs_theme"] = bb_vals - theme_avg_bb
    _bb_stats_global = bb_stats
else:
    df_train["buybox_vs_theme"] = 0.0

GROUP_B = ["3p_prem_vs_theme", "reviews_vs_theme", "buybox_vs_theme"]
b_cov = {f: (df_train[f] != 0).sum() for f in GROUP_B}
print(f"    Features: {GROUP_B}")
print(f"    Coverage (non-zero): {b_cov}")

# Clean up temp column
df_train = df_train.drop(columns=["_theme"])


# ---- GROUP C: Composite Signals ----
print("\n  Group C: Composite Signals")

# inefficiency_x_demand: rrp_uk_premium * log1p(amz_review_count)
uk_prem = df_train.get("rrp_uk_premium", pd.Series(0, index=df_train.index)).fillna(0)
log_reviews = np.log1p(df_train.get("amz_review_count", pd.Series(0, index=df_train.index)).fillna(0))
df_train["inefficiency_x_demand"] = uk_prem * log_reviews

# scarcity_pressure: buybox_premium_avg * (1 - amz_fba_spread_at_retire)
bb_prem = df_train.get("buybox_premium_avg", pd.Series(0, index=df_train.index)).fillna(0)
spread = df_train.get("amz_fba_spread_at_retire", pd.Series(0, index=df_train.index)).fillna(0)
df_train["scarcity_pressure"] = bb_prem * (1 - spread)

# premium_momentum: 3p_above_rrp_pct * fba_prem_late_vs_early (from Group A)
prem_3p = df_train.get("3p_above_rrp_pct", pd.Series(0, index=df_train.index)).fillna(0)
fba_late_early = df_train.get("fba_prem_late_vs_early", pd.Series(0, index=df_train.index)).fillna(0)
df_train["premium_momentum"] = prem_3p * fba_late_early

# theme_quality_x_premium: theme_avg_retire_price * 3p_prem_vs_theme (from Group B)
theme_retire = df_train.get("theme_avg_retire_price", pd.Series(0, index=df_train.index)).fillna(0)
prem_vs_theme = df_train.get("3p_prem_vs_theme", pd.Series(0, index=df_train.index)).fillna(0)
df_train["theme_quality_x_premium"] = theme_retire * prem_vs_theme

GROUP_C = ["inefficiency_x_demand", "scarcity_pressure", "premium_momentum", "theme_quality_x_premium"]
c_cov = {f: (df_train[f] != 0).sum() for f in GROUP_C}
print(f"    Features: {GROUP_C}")
print(f"    Coverage (non-zero): {c_cov}")


# ---- GROUP D: Demand Intensity ----
print("\n  Group D: Demand Intensity")

# Compute shelf_life_months from release_date to retired_date
shelf_life: dict[str, float] = {}
for sn in df_train["set_number"].values:
    sn_str = str(sn)
    rel = _parse_date(str(release_date_map.get(sn_str, "")))
    ret = _parse_date(str(retired_date_map.get(sn_str, "")))
    if rel and ret and rel is not pd.NaT and ret is not pd.NaT:
        months = max((ret - rel).days / 30.44, 6)  # floor at 6 months
        shelf_life[sn_str] = months
    else:
        shelf_life[sn_str] = 0  # will be filled with median

# Fill missing shelf life with median
sl_vals = [v for v in shelf_life.values() if v > 0]
median_sl = float(np.median(sl_vals)) if sl_vals else 24.0

review_counts = df_train.get("amz_review_count", pd.Series(0, index=df_train.index)).fillna(0)
sl_series = df_train["set_number"].map(shelf_life).fillna(0)
sl_series = sl_series.replace(0, median_sl)
df_train["review_velocity"] = review_counts / sl_series

rrp_dollars = df_train["set_number"].map(rrp_map).astype(float) / 100
rrp_dollars = rrp_dollars.replace(0, np.nan)
df_train["review_per_dollar"] = (review_counts / rrp_dollars).fillna(0)

GROUP_D = ["review_velocity", "review_per_dollar"]
d_cov = {f: (df_train[f] != 0).sum() for f in GROUP_D}
print(f"    Features: {GROUP_D}")
print(f"    Coverage (non-zero): {d_cov}")
print(f"    Median shelf life: {median_sl:.1f} months")

ALL_NEW_FEATURES = GROUP_A + GROUP_B + GROUP_C + GROUP_D
print(f"\nTotal new features: {len(ALL_NEW_FEATURES)}")

# ============================================================================
# PHASE 2: DIAGNOSTICS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 2: FEATURE DIAGNOSTICS")
print("=" * 70)

y_ann = df_train["bl_ann_return"].values.astype(float)
y_avoid = (y_ann < 8.0).astype(int)
y_great = (y_ann >= 20.0).astype(int)

print(f"\n{'Feature':35s} {'Cov%':>5s} {'Sprmn':>7s} {'MI_avd':>7s} {'MI_gb':>7s} {'p25':>7s} {'p50':>7s} {'p75':>7s}")
print("-" * 100)

viable_features: list[str] = []
for feat in ALL_NEW_FEATURES:
    vals = df_train[feat].values.astype(float)
    nonzero = (vals != 0) & np.isfinite(vals)
    coverage = nonzero.sum() / len(vals) * 100

    if nonzero.sum() < 30:
        print(f"{feat:35s} {coverage:5.1f}  (too few non-zero)")
        continue

    sp, _ = spearmanr(vals[nonzero], y_ann[nonzero])

    vals_finite = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
    vals_2d = vals_finite.reshape(-1, 1)
    mi_avoid = mutual_info_classif(vals_2d, y_avoid, random_state=42, n_neighbors=5)[0]
    mi_great = mutual_info_classif(vals_2d, y_great, random_state=42, n_neighbors=5)[0]

    p25, p50, p75 = np.nanpercentile(vals[nonzero], [25, 50, 75])

    print(f"{feat:35s} {coverage:5.1f} {sp:+.4f} {mi_avoid:.4f} {mi_great:.4f} {p25:7.3f} {p50:7.3f} {p75:7.3f}")

    if mi_avoid >= 0.003 or mi_great >= 0.003:
        viable_features.append(feat)

print(f"\nViable features (MI >= 0.003): {len(viable_features)}")
for f in viable_features:
    print(f"  {f}")

# ============================================================================
# PHASE 3: GROUPKFOLD CV
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 3: GROUPKFOLD CV")
print("=" * 70)

baseline_features = [f for f in CLASSIFIER_FEATURES if f in df_train.columns]
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
    label: str,
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
    auc = roc_auc_score(y_binary[valid], oof[valid])
    return auc


# Run all configurations
configs: dict[str, list[str]] = {
    "BASELINE (39)": baseline_features,
    "+GROUP_A (Phase Trans)": baseline_features + GROUP_A,
    "+GROUP_B (Relative Sig)": baseline_features + GROUP_B,
    "+GROUP_C (Composites)": baseline_features + GROUP_C,
    "+GROUP_D (Demand Int)": baseline_features + GROUP_D,
    "+ALL_NEW (A+B+C+D)": baseline_features + ALL_NEW_FEATURES,
}

results: list[dict] = []
print(f"\n{'Config':35s} {'#Feat':>6s} {'Avoid AUC':>10s} {'dAvoid':>8s} {'GB AUC':>10s} {'dGB':>8s}")
print("-" * 85)

baseline_avoid = None
baseline_gb = None

for name, feats in configs.items():
    avoid_auc = run_clf_cv(feats, name, threshold=8.0, invert=False)
    gb_auc = run_clf_cv(feats, name, threshold=20.0, invert=True)

    if baseline_avoid is None:
        baseline_avoid = avoid_auc
        baseline_gb = gb_auc

    d_avoid = avoid_auc - baseline_avoid
    d_gb = gb_auc - baseline_gb

    results.append({
        "config": name, "n_feat": len(feats),
        "avoid_auc": avoid_auc, "gb_auc": gb_auc,
        "d_avoid": d_avoid, "d_gb": d_gb,
    })

    print(f"{name:35s} {len(feats):6d} {avoid_auc:10.4f} {d_avoid:+8.4f} {gb_auc:10.4f} {d_gb:+8.4f}")

# ============================================================================
# PHASE 4: LOFO ABLATION (on ALL_NEW features)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: ABLATION (LOFO on new features in ALL_NEW)")
print("=" * 70)

all_new_feats = baseline_features + ALL_NEW_FEATURES
all_avoid = run_clf_cv(all_new_feats, "ALL_NEW", threshold=8.0, invert=False)
all_gb = run_clf_cv(all_new_feats, "ALL_NEW", threshold=20.0, invert=True)

print(f"\n{'Removed Feature':35s} {'Avoid AUC':>10s} {'dAvoid':>8s} {'GB AUC':>10s} {'dGB':>8s} {'Verdict':>10s}")
print("-" * 90)

for feat in ALL_NEW_FEATURES:
    reduced = [f for f in all_new_feats if f != feat]
    avoid_auc = run_clf_cv(reduced, f"-{feat}", threshold=8.0, invert=False)
    gb_auc = run_clf_cv(reduced, f"-{feat}", threshold=20.0, invert=True)
    d_avoid = avoid_auc - all_avoid
    d_gb = gb_auc - all_gb
    # If removing hurts (negative delta), the feature helps
    verdict = "HELPS" if (d_avoid < -0.002 or d_gb < -0.002) else (
        "HURTS" if (d_avoid > 0.002 or d_gb > 0.002) else "NEUTRAL"
    )
    print(f"{feat:35s} {avoid_auc:10.4f} {d_avoid:+8.4f} {gb_auc:10.4f} {d_gb:+8.4f} {verdict:>10s}")

# ============================================================================
# PHASE 5: FORWARD SELECTION
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 5: FORWARD SELECTION (greedy, from 39-feature baseline)")
print("=" * 70)

selected: list[str] = []
remaining = list(ALL_NEW_FEATURES)
current_feats = list(baseline_features)
current_avoid = baseline_avoid
current_gb = baseline_gb

print(f"\nStarting from baseline: Avoid={current_avoid:.4f}, GB={current_gb:.4f}")

for step in range(len(ALL_NEW_FEATURES)):
    best_feat = None
    best_score = -1.0
    best_avoid = current_avoid
    best_gb = current_gb

    for feat in remaining:
        trial_feats = current_feats + selected + [feat]
        avoid_auc = run_clf_cv(trial_feats, f"+{feat}", threshold=8.0, invert=False)
        gb_auc = run_clf_cv(trial_feats, f"+{feat}", threshold=20.0, invert=True)
        # Combined improvement (equal weight on both classifiers)
        score = (avoid_auc - current_avoid) + (gb_auc - current_gb)
        if score > best_score:
            best_score = score
            best_feat = feat
            best_avoid = avoid_auc
            best_gb = gb_auc

    if best_score < 0.003:
        print(f"\n  Step {step + 1}: best candidate '{best_feat}' adds {best_score:+.4f} (< 0.003 threshold). STOPPING.")
        break

    selected.append(best_feat)
    remaining.remove(best_feat)
    current_avoid = best_avoid
    current_gb = best_gb
    print(f"  Step {step + 1}: +{best_feat:30s}  Avoid={best_avoid:.4f} ({best_avoid - baseline_avoid:+.4f})  "
          f"GB={best_gb:.4f} ({best_gb - baseline_gb:+.4f})  combined={best_score:+.4f}")

print(f"\nSelected features ({len(selected)}):")
for f in selected:
    group = "A" if f in GROUP_A else "B" if f in GROUP_B else "C" if f in GROUP_C else "D"
    print(f"  [{group}] {f}")

# ============================================================================
# PHASE 6: FEATURE IMPORTANCE (ALL_NEW config)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: FEATURE IMPORTANCE (ALL_NEW)")
print("=" * 70)

X_full = df_train[all_new_feats].fillna(0).copy()
X_arr = clip_outliers(X_full).values.astype(float)
y_binary = (y_ann < 8.0).astype(int)

clf = lgb.LGBMClassifier(n_estimators=200, **CLF_PARAMS, random_state=42, n_jobs=1)
clf.fit(X_arr, y_binary)
imp = dict(zip(all_new_feats, clf.feature_importances_))

# Sort by importance
sorted_imp = sorted(imp.items(), key=lambda x: -x[1])
print(f"\nTop 20 features by LightGBM gain:")
for rank, (feat, gain) in enumerate(sorted_imp[:20], 1):
    tag = ""
    if feat in GROUP_A:
        tag = " [A:Phase]"
    elif feat in GROUP_B:
        tag = " [B:Relative]"
    elif feat in GROUP_C:
        tag = " [C:Composite]"
    elif feat in GROUP_D:
        tag = " [D:Demand]"
    print(f"  {rank:2d}. {feat:35s} gain={gain:4d}{tag}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

elapsed = time.time() - t0
print(f"\nElapsed: {elapsed:.0f}s")

print(f"\nBaseline (39 features): Avoid={baseline_avoid:.4f}, GB={baseline_gb:.4f}")
if selected:
    final_feats = baseline_features + selected
    final_avoid = run_clf_cv(final_feats, "FINAL", threshold=8.0, invert=False)
    final_gb = run_clf_cv(final_feats, "FINAL", threshold=20.0, invert=True)
    print(f"Final ({39 + len(selected)} features): Avoid={final_avoid:.4f} ({final_avoid - baseline_avoid:+.4f}), "
          f"GB={final_gb:.4f} ({final_gb - baseline_gb:+.4f})")
    print(f"\nRecommended for production integration ({len(selected)} features):")
    for f in selected:
        group = "A" if f in GROUP_A else "B" if f in GROUP_B else "C" if f in GROUP_C else "D"
        print(f"  [{group}] {f}")
else:
    print("No features passed forward selection threshold.")
    print("Model is mature at 39 features -- no further gains from these feature groups.")
