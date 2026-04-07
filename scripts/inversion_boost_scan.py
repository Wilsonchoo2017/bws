"""Test whether inversion model can boost the regressor.

Tests:
1. P(avoid) as a feature for the regressor
2. Train regressor on non-losers only (filter <8% growth)
3. Train regressor on non-losers + use P(avoid) as feature
4. Two-stage: classifier gates, regressor predicts winners only

Run: python -m scripts.inversion_boost_scan
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

print("=" * 70)
print("INVERSION BOOST SCAN")
print("Can the classifier help the regressor?")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.feature_selection import select_features
from services.ml.pg_queries import load_growth_training_data

engine = get_engine()
df_raw = load_growth_training_data(engine)
y_all = df_raw["annual_growth_pct"].values.astype(float)
year_retired = np.asarray(
    pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
)

df_feat, _, _ = engineer_intrinsic_features(df_raw, training_target=pd.Series(y_all))
t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
X_raw = df_feat[t1_candidates].copy()
for c in X_raw.columns:
    X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
t1_features = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
if len(t1_features) < 5:
    t1_features = t1_candidates

X = X_raw[t1_features].fillna(X_raw[t1_features].median()).values
feature_names = list(t1_features)

finite = np.isfinite(year_retired)
groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
groups[finite] = year_retired[finite].astype(int)

THRESHOLD = 8.0  # same as production

print(f"\nData: {len(y_all)} sets, {len(t1_features)} features")
print(f"Losers (< {THRESHOLD}%): {(y_all < THRESHOLD).sum()} ({(y_all < THRESHOLD).mean()*100:.0f}%)")
print(f"Winners (>= {THRESHOLD}%): {(y_all >= THRESHOLD).sum()} ({(y_all >= THRESHOLD).mean()*100:.0f}%)")

import lightgbm as lgb
from services.ml.growth.model_selection import MONOTONIC_MAP

mono = [MONOTONIC_MAP.get(f, 0) for f in feature_names]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_regressor(mono_constraints=None):
    m = lgb.LGBMRegressor(
        n_estimators=300, max_depth=8, num_leaves=41,
        learning_rate=0.039, feature_fraction=0.93, subsample=0.79,
        objective="huber", alpha=1.0, verbosity=-1, random_state=42, n_jobs=1,
    )
    if mono_constraints:
        m.set_params(monotone_constraints=mono_constraints)
    return m


def make_classifier():
    return lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, num_leaves=15,
        learning_rate=0.05, is_unbalance=True,
        verbosity=-1, random_state=42, n_jobs=1,
    )


n_unique = len(set(groups))
n_splits = min(5, n_unique)
splitter = GroupKFold(n_splits=n_splits)
folds = list(splitter.split(np.arange(len(y_all)), y_all, groups))


def evaluate(y_true, y_pred, name=""):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    mae = mean_absolute_error(y_true, y_pred)

    # Winner underprediction
    winners = y_true >= 20
    winner_bias = np.mean(y_pred[winners] - y_true[winners]) if winners.sum() >= 5 else np.nan

    return {"name": name, "r2": r2, "mae": mae, "winner_bias": winner_bias}


# ---------------------------------------------------------------------------
# Test 0: Baseline (current production)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 0: BASELINE (current production)")
print("=" * 70)

r2s_base = []
for train_idx, val_idx in folds:
    X_tr, X_va = X[train_idx], X[val_idx]
    y_tr, y_va = y_all[train_idx], y_all[val_idx]

    lo, hi = np.percentile(y_tr, [1, 99])
    y_tr_w = np.clip(y_tr, lo, hi)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    model = make_regressor(mono)
    model.fit(X_tr_s, y_tr_t)
    y_pred = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

    res = evaluate(y_va, y_pred)
    r2s_base.append(res["r2"])

print(f"  R2 = {np.mean(r2s_base):+.3f} +/- {np.std(r2s_base):.3f}")


# ---------------------------------------------------------------------------
# Test 1: P(avoid) as a feature for the regressor
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 1: P(avoid) AS REGRESSOR FEATURE")
print("=" * 70)

r2s_pavoid = []
for train_idx, val_idx in folds:
    X_tr, X_va = X[train_idx], X[val_idx]
    y_tr, y_va = y_all[train_idx], y_all[val_idx]

    # Train classifier on training fold
    y_cls = (y_tr < THRESHOLD).astype(int)
    scaler_cls = StandardScaler()
    X_tr_cls = scaler_cls.fit_transform(X_tr)
    X_va_cls = scaler_cls.transform(X_va)

    clf = make_classifier()
    clf.fit(X_tr_cls, y_cls)

    # Get P(avoid) for train and val
    p_avoid_tr = clf.predict_proba(X_tr_cls)[:, 1].reshape(-1, 1)
    p_avoid_va = clf.predict_proba(X_va_cls)[:, 1].reshape(-1, 1)

    # Append P(avoid) as feature
    X_tr_aug = np.hstack([X_tr, p_avoid_tr])
    X_va_aug = np.hstack([X_va, p_avoid_va])

    lo, hi = np.percentile(y_tr, [1, 99])
    y_tr_w = np.clip(y_tr, lo, hi)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr_aug)
    X_va_s = scaler.transform(X_va_aug)

    # No monotonic on P(avoid) column
    mono_aug = mono + [0]
    model = make_regressor(mono_aug)
    model.fit(X_tr_s, y_tr_t)
    y_pred = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

    res = evaluate(y_va, y_pred)
    r2s_pavoid.append(res["r2"])

delta1 = np.mean(r2s_pavoid) - np.mean(r2s_base)
print(f"  R2 = {np.mean(r2s_pavoid):+.3f} +/- {np.std(r2s_pavoid):.3f}  (delta={delta1:+.3f})")


# ---------------------------------------------------------------------------
# Test 2: Train regressor on non-losers only
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 2: REGRESSOR ON NON-LOSERS ONLY (growth >= 8%)")
print("=" * 70)

r2s_nonloser = []
for train_idx, val_idx in folds:
    X_tr_full, X_va = X[train_idx], X[val_idx]
    y_tr_full, y_va = y_all[train_idx], y_all[val_idx]

    # Filter training to non-losers only
    winner_mask = y_tr_full >= THRESHOLD
    X_tr = X_tr_full[winner_mask]
    y_tr = y_tr_full[winner_mask]

    lo, hi = np.percentile(y_tr, [1, 99])
    y_tr_w = np.clip(y_tr, lo, hi)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    model = make_regressor(mono)
    model.fit(X_tr_s, y_tr_t)
    y_pred = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

    res = evaluate(y_va, y_pred)
    r2s_nonloser.append(res["r2"])

delta2 = np.mean(r2s_nonloser) - np.mean(r2s_base)
print(f"  R2 = {np.mean(r2s_nonloser):+.3f} +/- {np.std(r2s_nonloser):.3f}  (delta={delta2:+.3f})")


# ---------------------------------------------------------------------------
# Test 3: Full hurdle — classifier gates, regressor on non-losers,
#          final = P(good)*regressor + P(bad)*median_loser
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 3: FULL HURDLE (classifier + non-loser regressor)")
print("=" * 70)

r2s_hurdle = []
for train_idx, val_idx in folds:
    X_tr_full, X_va = X[train_idx], X[val_idx]
    y_tr_full, y_va = y_all[train_idx], y_all[val_idx]

    # Train classifier
    y_cls = (y_tr_full < THRESHOLD).astype(int)
    scaler_cls = StandardScaler()
    X_tr_cls = scaler_cls.fit_transform(X_tr_full)
    X_va_cls = scaler_cls.transform(X_va)
    clf = make_classifier()
    clf.fit(X_tr_cls, y_cls)
    p_avoid = clf.predict_proba(X_va_cls)[:, 1]

    # Train regressor on non-losers only
    winner_mask = y_tr_full >= THRESHOLD
    X_tr_win = X_tr_full[winner_mask]
    y_tr_win = y_tr_full[winner_mask]
    median_loser = float(np.median(y_tr_full[~winner_mask]))

    lo, hi = np.percentile(y_tr_win, [1, 99])
    y_tr_w = np.clip(y_tr_win, lo, hi)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr_win)
    X_va_s = scaler.transform(X_va)

    model = make_regressor(mono)
    model.fit(X_tr_s, y_tr_t)
    reg_pred = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

    # Hurdle combine
    y_pred = (1 - p_avoid) * reg_pred + p_avoid * median_loser

    res = evaluate(y_va, y_pred)
    r2s_hurdle.append(res["r2"])

delta3 = np.mean(r2s_hurdle) - np.mean(r2s_base)
print(f"  R2 = {np.mean(r2s_hurdle):+.3f} +/- {np.std(r2s_hurdle):.3f}  (delta={delta3:+.3f})")


# ---------------------------------------------------------------------------
# Test 4: P(avoid) + non-loser regressor (best of Test 1 + Test 2)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 4: P(avoid) FEATURE + NON-LOSER TRAINING")
print("=" * 70)

r2s_combo = []
for train_idx, val_idx in folds:
    X_tr_full, X_va = X[train_idx], X[val_idx]
    y_tr_full, y_va = y_all[train_idx], y_all[val_idx]

    # Train classifier on full training set
    y_cls = (y_tr_full < THRESHOLD).astype(int)
    scaler_cls = StandardScaler()
    X_tr_cls = scaler_cls.fit_transform(X_tr_full)
    X_va_cls = scaler_cls.transform(X_va)
    clf = make_classifier()
    clf.fit(X_tr_cls, y_cls)

    p_avoid_tr = clf.predict_proba(X_tr_cls)[:, 1]
    p_avoid_va = clf.predict_proba(X_va_cls)[:, 1]

    # Filter to non-losers for regressor training
    winner_mask = y_tr_full >= THRESHOLD
    X_tr_win = np.hstack([X_tr_full[winner_mask], p_avoid_tr[winner_mask].reshape(-1, 1)])
    X_va_aug = np.hstack([X_va, p_avoid_va.reshape(-1, 1)])
    y_tr_win = y_tr_full[winner_mask]

    lo, hi = np.percentile(y_tr_win, [1, 99])
    y_tr_w = np.clip(y_tr_win, lo, hi)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr_win)
    X_va_s = scaler.transform(X_va_aug)

    mono_aug = mono + [0]
    model = make_regressor(mono_aug)
    model.fit(X_tr_s, y_tr_t)
    y_pred = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

    res = evaluate(y_va, y_pred)
    r2s_combo.append(res["r2"])

delta4 = np.mean(r2s_combo) - np.mean(r2s_base)
print(f"  R2 = {np.mean(r2s_combo):+.3f} +/- {np.std(r2s_combo):.3f}  (delta={delta4:+.3f})")


# ---------------------------------------------------------------------------
# Test 5: Residual correction — classifier predicts residual bias
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 5: RESIDUAL CORRECTION (classifier corrects regressor bias)")
print("=" * 70)

r2s_resid = []
for train_idx, val_idx in folds:
    X_tr, X_va = X[train_idx], X[val_idx]
    y_tr, y_va = y_all[train_idx], y_all[val_idx]

    lo, hi = np.percentile(y_tr, [1, 99])
    y_tr_w = np.clip(y_tr, lo, hi)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    # Stage 1: regressor
    model = make_regressor(mono)
    model.fit(X_tr_s, y_tr_t)
    reg_pred_tr = pt.inverse_transform(model.predict(X_tr_s).reshape(-1, 1)).ravel()
    reg_pred_va = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

    # Stage 2: train a correction model on residuals
    residuals = y_tr - reg_pred_tr
    # Augment features with regressor prediction
    X_tr_aug = np.hstack([X_tr_s, reg_pred_tr.reshape(-1, 1)])
    X_va_aug = np.hstack([X_va_s, reg_pred_va.reshape(-1, 1)])

    correction = lgb.LGBMRegressor(
        n_estimators=100, max_depth=3, num_leaves=7,
        learning_rate=0.05, objective="huber",
        verbosity=-1, random_state=42, n_jobs=1,
    )
    correction.fit(X_tr_aug, residuals)
    correction_pred = correction.predict(X_va_aug)

    y_pred = reg_pred_va + correction_pred

    res = evaluate(y_va, y_pred)
    r2s_resid.append(res["r2"])

delta5 = np.mean(r2s_resid) - np.mean(r2s_base)
print(f"  R2 = {np.mean(r2s_resid):+.3f} +/- {np.std(r2s_resid):.3f}  (delta={delta5:+.3f})")


# ---------------------------------------------------------------------------
# Test 6: Bucket-specific models (classifier routes to specialist)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 6: BUCKET ROUTING (classifier routes to low/high specialist)")
print("=" * 70)

r2s_bucket = []
for train_idx, val_idx in folds:
    X_tr, X_va = X[train_idx], X[val_idx]
    y_tr, y_va = y_all[train_idx], y_all[val_idx]

    # Train classifier
    y_cls = (y_tr < THRESHOLD).astype(int)
    scaler_cls = StandardScaler()
    X_tr_cls = scaler_cls.fit_transform(X_tr)
    X_va_cls = scaler_cls.transform(X_va)
    clf = make_classifier()
    clf.fit(X_tr_cls, y_cls)
    p_avoid_va = clf.predict_proba(X_va_cls)[:, 1]

    # Train TWO regressors: one for losers, one for winners
    low_mask = y_tr < THRESHOLD
    high_mask = ~low_mask

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    # Low model (losers)
    if low_mask.sum() >= 20:
        pt_lo = PowerTransformer(method="yeo-johnson", standardize=False)
        y_lo_t = pt_lo.fit_transform(y_tr[low_mask].reshape(-1, 1)).ravel()
        model_lo = make_regressor()
        model_lo.fit(X_tr_s[low_mask], y_lo_t)
        pred_lo = pt_lo.inverse_transform(model_lo.predict(X_va_s).reshape(-1, 1)).ravel()
    else:
        pred_lo = np.full(len(y_va), np.median(y_tr[low_mask]) if low_mask.sum() > 0 else 3.0)

    # High model (winners)
    pt_hi = PowerTransformer(method="yeo-johnson", standardize=False)
    y_hi_w = np.clip(y_tr[high_mask], *np.percentile(y_tr[high_mask], [1, 99]))
    y_hi_t = pt_hi.fit_transform(y_hi_w.reshape(-1, 1)).ravel()
    model_hi = make_regressor(mono)
    model_hi.fit(X_tr_s[high_mask], y_hi_t)
    pred_hi = pt_hi.inverse_transform(model_hi.predict(X_va_s).reshape(-1, 1)).ravel()

    # Blend by P(avoid)
    y_pred = (1 - p_avoid_va) * pred_hi + p_avoid_va * pred_lo

    res = evaluate(y_va, y_pred)
    r2s_bucket.append(res["r2"])

delta6 = np.mean(r2s_bucket) - np.mean(r2s_base)
print(f"  R2 = {np.mean(r2s_bucket):+.3f} +/- {np.std(r2s_bucket):.3f}  (delta={delta6:+.3f})")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

results = [
    ("Baseline (all data, no classifier)", np.mean(r2s_base), 0),
    ("+ P(avoid) as feature", np.mean(r2s_pavoid), delta1),
    ("Non-losers only", np.mean(r2s_nonloser), delta2),
    ("Full hurdle (clf + non-loser reg)", np.mean(r2s_hurdle), delta3),
    ("P(avoid) feat + non-loser train", np.mean(r2s_combo), delta4),
    ("Residual correction (2-stage)", np.mean(r2s_resid), delta5),
    ("Bucket routing (lo/hi specialists)", np.mean(r2s_bucket), delta6),
]

results.sort(key=lambda x: x[1], reverse=True)

print(f"\n{'Config':<45} {'R2':>8} {'Delta':>8}")
print("-" * 65)
for name, r2, delta in results:
    marker = " <-- PROD" if delta == 0 else " !!!" if delta > 0.02 else " +" if delta > 0 else ""
    print(f"  {name:<43} {r2:+.3f}  {delta:+.3f}{marker}")

print(f"\nTotal time: {time.time() - t0:.0f}s")
