"""Experiment 32: Google Trends re-test with current production pipeline.

Quick diagnostic: does adding GT features to the Exp 31g Keepa+BL model
improve OOF CV metrics (R2, Spearman, MAE) or P(great_buy) AUC?

Previous tests (Exp 16, 19b) used smaller datasets (78-346 sets) and
different model architecture. Now we have 2400+ sets, BL ground truth,
and the hurdle model. Re-test with the same GroupKFold approach as 31g.

GT features engineered (ALL pre-retirement only, no lookahead):
  - gt_peak_value: max interest value before retirement
  - gt_avg_value: mean interest before retirement
  - gt_months_active: months with interest > 0 before retirement
  - gt_decay_rate: interest decay slope (pre-retirement)
  - gt_pre_retire_avg: avg interest in last 12 months before retirement
  - gt_lifetime_months: total months of timeline before retirement
  - gt_peak_recency: months between peak and retirement (how recent was peak interest)

Run: python -m research.growth.32_gt_retest
"""
from __future__ import annotations

import json
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer

print("=" * 70)
print("EXP 32: GOOGLE TRENDS RE-TEST (QUICK DIAGNOSTIC)")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.pg_queries import load_keepa_bl_training_data
from services.ml.growth.keepa_features import KEEPA_BL_FEATURES, engineer_keepa_bl_features
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights

engine = get_engine()

# ============================================================================
# DATA LOADING
# ============================================================================
print("\n--- Loading data ---")
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
print(f"Base: {len(base_df)}, Keepa: {len(keepa_df)}, Targets: {len(target_series)}")

df_feat = engineer_keepa_bl_features(base_df, keepa_df)
target_map = dict(zip(target_series.index, target_series.values))
df_feat["target"] = df_feat["set_number"].map(target_map)
df_feat = df_feat[df_feat["target"].notna()].copy()

# Add year_retired
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
for _, row in base_df.iterrows():
    sn = str(row["set_number"])
    if sn not in yr_map or pd.isna(yr_map.get(sn)):
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            yr_map[sn] = rd.year
df_feat["year_retired"] = df_feat["set_number"].map(yr_map).fillna(2023).astype(int)

# ============================================================================
# LOAD GOOGLE TRENDS DATA
# ============================================================================
print("\n--- Loading Google Trends ---")
with engine.connect() as conn:
    gt_df = pd.read_sql("""
        SELECT set_number, interest_json, peak_value, average_value, scraped_at
        FROM google_trends_snapshots
        WHERE search_property = 'youtube'
    """, conn)
print(f"GT snapshots: {len(gt_df)} sets")


def _engineer_gt_features(gt_df: pd.DataFrame, base_df: pd.DataFrame) -> pd.DataFrame:
    """Engineer GT features per set, cutting at retired_date to prevent lookahead."""
    retire_map: dict[str, pd.Timestamp] = {}
    for _, row in base_df.iterrows():
        sn = str(row["set_number"])
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            retire_map[sn] = rd

    records: list[dict] = []
    for _, row in gt_df.iterrows():
        sn = str(row["set_number"])
        retire_dt = retire_map.get(sn)

        # Parse timeline
        raw = row["interest_json"]
        if isinstance(raw, str):
            try:
                tl = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                tl = []
        elif isinstance(raw, list):
            tl = raw
        else:
            tl = []

        if not tl:
            continue

        dates = []
        values = []
        for entry in tl:
            if len(entry) >= 2:
                try:
                    d = pd.to_datetime(str(entry[0]))
                    v = float(entry[1])
                    dates.append(d)
                    values.append(v)
                except (ValueError, TypeError):
                    continue

        if not dates:
            continue

        vals = np.array(values, dtype=float)

        # STRICT: only use data BEFORE retired_date (no lookahead)
        if retire_dt is not None and pd.notna(retire_dt):
            pre_mask = np.array([d <= retire_dt for d in dates])
            pre_dates = [d for d, m in zip(dates, pre_mask) if m]
            pre_vals = vals[pre_mask] if pre_mask.any() else np.array([0.0])

            # Last 12 months before retirement
            pre_12m_mask = np.array([
                d > retire_dt - pd.DateOffset(months=12) and d <= retire_dt
                for d in dates
            ])
            pre_12m = vals[pre_12m_mask] if pre_12m_mask.any() else np.array([0.0])
        else:
            # No retire date -- skip (can't determine cutoff)
            continue

        if len(pre_vals) == 0 or pre_vals.max() == 0:
            continue

        # All features are PRE-RETIREMENT only
        gt_peak = float(pre_vals.max())
        gt_avg = float(pre_vals.mean())
        gt_months_active = int((pre_vals > 0).sum())
        gt_lifetime_months = len(pre_vals)

        # Decay rate: linear slope of interest over time (pre-retire)
        gt_decay = 0.0
        if len(pre_vals) >= 6 and pre_vals.std() > 0:
            x = np.arange(len(pre_vals), dtype=float)
            gt_decay = float(np.polyfit(x, pre_vals, 1)[0])

        # Pre-retire 12m average (the signal closest to purchase time)
        pre_avg = float(pre_12m.mean()) if len(pre_12m) > 0 else 0.0

        # Peak recency: how many months before retirement was the peak?
        if pre_dates:
            peak_idx = int(pre_vals.argmax())
            peak_date = pre_dates[peak_idx]
            gt_peak_recency = max(0, (retire_dt - peak_date).days / 30.0)
        else:
            gt_peak_recency = 0.0

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

    return pd.DataFrame(records)


gt_features = _engineer_gt_features(gt_df, base_df)
print(f"GT features engineered for {len(gt_features)} sets")

GT_FEATURE_NAMES = [
    "gt_peak_value", "gt_avg_value", "gt_months_active",
    "gt_decay_rate", "gt_pre_retire_avg",
    "gt_lifetime_months", "gt_peak_recency",
]

# Merge GT features
df_feat = df_feat.merge(gt_features, on="set_number", how="left")
for col in GT_FEATURE_NAMES:
    df_feat[col] = df_feat[col].fillna(0)

has_gt = df_feat["gt_peak_value"] > 0
print(f"Sets with GT data: {has_gt.sum()} / {len(df_feat)} ({has_gt.mean()*100:.1f}%)")

# ============================================================================
# QUICK CORRELATION CHECK
# ============================================================================
print("\n--- GT Feature Correlations with Target ---")
for col in GT_FEATURE_NAMES:
    mask = df_feat[col] != 0
    if mask.sum() > 30:
        r = df_feat.loc[mask, col].corr(df_feat.loc[mask, "target"])
        sp, _ = spearmanr(df_feat.loc[mask, col], df_feat.loc[mask, "target"])
        print(f"  {col:25s}  r={r:+.3f}  spearman={sp:+.3f}  n={mask.sum()}")
    else:
        print(f"  {col:25s}  n={mask.sum()} (too few)")

# ============================================================================
# TRAINING SETUP (same as 31g)
# ============================================================================
train_mask = df_feat["year_retired"] <= 2024
df_train = df_feat[train_mask].copy()

y_raw = df_train["target"].values.astype(float)
groups = df_train["year_retired"].values

lo, hi = np.percentile(y_raw, [2, 98])
y_clip = np.clip(y_raw, lo, hi)
y_growth_pct = (y_clip - 1.0) * 100

sample_weight = compute_recency_weights(groups.astype(float))

# Baseline features (no GT)
baseline_features = [f for f in KEEPA_BL_FEATURES if f in df_train.columns]
# With GT features
gt_enhanced_features = baseline_features + GT_FEATURE_NAMES

print(f"\nTraining: {len(df_train)} sets")
print(f"Baseline features: {len(baseline_features)}")
print(f"GT-enhanced features: {len(gt_enhanced_features)}")

import lightgbm as lgb

LGB_PARAMS = {
    "objective": "huber", "metric": "mae",
    "learning_rate": 0.068, "num_leaves": 20, "max_depth": 8,
    "min_child_samples": 19, "subsample": 0.60,
    "colsample_bytree": 0.88, "reg_alpha": 0.35,
    "reg_lambda": 0.009, "verbosity": -1,
}

CLF_PARAMS = {
    "objective": "binary", "metric": "auc",
    "learning_rate": 0.05, "num_leaves": 15, "max_depth": 4,
    "min_child_samples": 10, "is_unbalance": True,
    "reg_alpha": 0.1, "reg_lambda": 1.0, "verbosity": -1,
}

n_splits = min(5, len(np.unique(groups)))
gkf = GroupKFold(n_splits=n_splits)


# ============================================================================
# HEAD-TO-HEAD: BASELINE vs GT-ENHANCED
# ============================================================================
def run_regressor_oof(feature_names: list[str], label: str) -> np.ndarray:
    """OOF predictions for regressor."""
    X_raw = df_train[feature_names].fillna(0).copy()
    X_arr = clip_outliers(X_raw).values.astype(float)

    tt = PowerTransformer(method="yeo-johnson")
    y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()

    oof = np.full(len(y_clip), np.nan)
    for tr_idx, va_idx in gkf.split(X_arr, y_t, groups):
        w = sample_weight[tr_idx]
        dtrain = lgb.Dataset(X_arr[tr_idx], label=y_t[tr_idx], weight=w)
        dval = lgb.Dataset(X_arr[va_idx], label=y_t[va_idx], reference=dtrain)
        model = lgb.train(
            LGB_PARAMS, dtrain, num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        pred_t = model.predict(X_arr[va_idx])
        oof[va_idx] = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()

    oof_growth = (oof - 1.0) * 100
    actual_growth = y_growth_pct

    r2 = r2_score(actual_growth, oof_growth)
    sp, _ = spearmanr(actual_growth, oof_growth)
    mae = np.mean(np.abs(actual_growth - oof_growth))
    print(f"  [{label}] Regressor: R2={r2:.4f}  Spearman={sp:.4f}  MAE={mae:.2f}%")
    return oof


def run_classifier_oof(feature_names: list[str], threshold_pct: float, label_tag: str) -> np.ndarray:
    """OOF probabilities for binary classifier."""
    X_raw = df_train[feature_names].fillna(0).copy()
    X_arr = clip_outliers(X_raw).values.astype(float)
    y_binary = (y_growth_pct >= threshold_pct).astype(int)

    oof_probs = np.full(len(y_binary), np.nan)
    for tr_idx, va_idx in gkf.split(X_arr, y_binary, groups):
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_arr[tr_idx])
        X_va = scaler.transform(X_arr[va_idx])
        clf = lgb.LGBMClassifier(n_estimators=200, **CLF_PARAMS, random_state=42, n_jobs=1)
        clf.fit(X_tr, y_binary[tr_idx])
        oof_probs[va_idx] = clf.predict_proba(X_va)[:, 1]

    auc = roc_auc_score(y_binary, oof_probs)
    print(f"  [{label_tag}] P(>={threshold_pct}%) AUC={auc:.4f}")
    return oof_probs


print("\n" + "=" * 70)
print("REGRESSOR: BASELINE vs GT-ENHANCED")
print("=" * 70)
oof_base = run_regressor_oof(baseline_features, "BASELINE")
oof_gt = run_regressor_oof(gt_enhanced_features, "GT-ENHANCED")

print("\n" + "=" * 70)
print("CLASSIFIER P(great_buy >= 20%): BASELINE vs GT-ENHANCED")
print("=" * 70)
prob_base = run_classifier_oof(baseline_features, 20.0, "BASELINE")
prob_gt = run_classifier_oof(gt_enhanced_features, 20.0, "GT-ENHANCED")

print("\n" + "=" * 70)
print("CLASSIFIER P(avoid < 0%): BASELINE vs GT-ENHANCED")
print("=" * 70)
avoid_base = run_classifier_oof(baseline_features, 0.0, "BASELINE")
avoid_gt = run_classifier_oof(gt_enhanced_features, 0.0, "GT-ENHANCED")

# ============================================================================
# FEATURE IMPORTANCE: WHERE DO GT FEATURES RANK?
# ============================================================================
print("\n" + "=" * 70)
print("GT FEATURE IMPORTANCE (full model)")
print("=" * 70)

X_full = df_train[gt_enhanced_features].fillna(0).copy()
X_full = clip_outliers(X_full).values.astype(float)
tt = PowerTransformer(method="yeo-johnson")
y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()
dtrain = lgb.Dataset(X_full, label=y_t, weight=sample_weight)
model = lgb.train(LGB_PARAMS, dtrain, num_boost_round=300)
imp = dict(zip(gt_enhanced_features, model.feature_importance(importance_type="gain")))
sorted_imp = sorted(imp.items(), key=lambda x: x[1], reverse=True)

print(f"{'Feature':35s}  {'Gain':>10s}  {'Rank':>5s}")
print("-" * 55)
for rank, (feat, gain) in enumerate(sorted_imp, 1):
    marker = " <-- GT" if feat.startswith("gt_") else ""
    print(f"{feat:35s}  {gain:10.1f}  {rank:5d}{marker}")

# ============================================================================
# VERDICT
# ============================================================================
print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)

oof_base_growth = (oof_base - 1.0) * 100
oof_gt_growth = (oof_gt - 1.0) * 100
r2_base = r2_score(y_growth_pct, oof_base_growth)
r2_gt = r2_score(y_growth_pct, oof_gt_growth)
sp_base, _ = spearmanr(y_growth_pct, oof_base_growth)
sp_gt, _ = spearmanr(y_growth_pct, oof_gt_growth)

print(f"Regressor R2:       BASELINE={r2_base:.4f}  GT={r2_gt:.4f}  delta={r2_gt - r2_base:+.4f}")
print(f"Regressor Spearman: BASELINE={sp_base:.4f}  GT={sp_gt:.4f}  delta={sp_gt - sp_base:+.4f}")

auc_base = roc_auc_score((y_growth_pct >= 20).astype(int), prob_base)
auc_gt = roc_auc_score((y_growth_pct >= 20).astype(int), prob_gt)
print(f"P(great_buy) AUC:   BASELINE={auc_base:.4f}  GT={auc_gt:.4f}  delta={auc_gt - auc_base:+.4f}")

avoid_auc_base = roc_auc_score((y_growth_pct >= 0).astype(int), avoid_base)
avoid_auc_gt = roc_auc_score((y_growth_pct >= 0).astype(int), avoid_gt)
print(f"P(avoid) AUC:       BASELINE={avoid_auc_base:.4f}  GT={avoid_auc_gt:.4f}  delta={avoid_auc_gt - avoid_auc_base:+.4f}")

gt_coverage = (df_train["gt_peak_value"] > 0).mean() * 100
print(f"\nGT coverage: {gt_coverage:.1f}% of training sets")
print(f"Time: {time.time() - t0:.1f}s")

if r2_gt > r2_base + 0.005 or auc_gt > auc_base + 0.005:
    print("\n>> POSITIVE SIGNAL: GT features show marginal improvement. Worth deeper investigation.")
elif r2_gt < r2_base - 0.005 or auc_gt < auc_base - 0.005:
    print("\n>> NEGATIVE SIGNAL: GT features HURT the model. Confirmed dead.")
else:
    print("\n>> NEUTRAL: GT features have no meaningful effect (< 0.005 delta). Not worth pursuing.")
