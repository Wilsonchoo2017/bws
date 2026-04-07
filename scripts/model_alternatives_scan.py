"""Head-to-head: LightGBM vs CatBoost vs HistGradientBoosting.

Tests whether alternative GBDT implementations beat our LightGBM baseline.
Uses same data, features, and CV setup (5-fold GroupKFold by year_retired).

Run: python -m scripts.model_alternatives_scan
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
print("MODEL ALTERNATIVES SCAN")
print("LightGBM vs CatBoost vs HistGradientBoosting")
print("=" * 70)

# ---------------------------------------------------------------------------
# Load data (same as ml_improvement_scan.py)
# ---------------------------------------------------------------------------

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

df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
    df_raw, training_target=pd.Series(y_all)
)

t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
X_raw = df_feat[t1_candidates].copy()
for c in X_raw.columns:
    X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
t1_features = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
if len(t1_features) < 5:
    t1_features = t1_candidates

X = X_raw[t1_features].fillna(X_raw[t1_features].median())

# Groups for temporal CV
finite = np.isfinite(year_retired)
groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
groups[finite] = year_retired[finite].astype(int)

print(f"\nData: {len(y_all)} sets, {len(t1_features)} features")
print(f"Features: {t1_features}")
print(f"Load time: {time.time() - t0:.1f}s")


# ---------------------------------------------------------------------------
# CV helper
# ---------------------------------------------------------------------------

def cv_score(X_vals, y, groups, model_factory, name="", use_scaler=True,
             target_transform=None, monotonic=None):
    """5-fold GroupKFold CV. Returns R2, MAE, per-fold R2s."""
    n_unique = len(set(groups))
    n_splits = min(5, n_unique)
    splitter = GroupKFold(n_splits=n_splits)

    r2s, maes = [], []

    for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
        X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        # Winsorize P1/P99
        lo, hi = np.percentile(y_tr, [1, 99])
        y_tr = np.clip(y_tr, lo, hi)

        # Target transform
        pt = None
        if target_transform == "yeo-johnson":
            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_fit = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
        else:
            y_tr_fit = y_tr

        # Scale
        if use_scaler:
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)
        else:
            X_tr_s, X_va_s = X_tr, X_va

        model = model_factory()
        if monotonic is not None and hasattr(model, "set_params"):
            try:
                model.set_params(monotone_constraints=monotonic)
            except Exception:
                pass

        model.fit(X_tr_s, y_tr_fit)
        y_pred_raw = model.predict(X_va_s)

        if pt is not None:
            y_pred = pt.inverse_transform(y_pred_raw.reshape(-1, 1)).ravel()
        else:
            y_pred = y_pred_raw

        ss_res = np.sum((y_va - y_pred) ** 2)
        ss_tot = np.sum((y_va - y_va.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        r2s.append(r2)
        maes.append(mean_absolute_error(y_va, y_pred))

    return {
        "name": name,
        "r2_mean": np.mean(r2s),
        "r2_std": np.std(r2s),
        "mae_mean": np.mean(maes),
        "folds": r2s,
    }


# ---------------------------------------------------------------------------
# Monotonic constraints
# ---------------------------------------------------------------------------
from services.ml.growth.model_selection import MONOTONIC_MAP

mono = [MONOTONIC_MAP.get(f, 0) for f in t1_features]

X_vals = X.values
y = y_all.copy()


# ---------------------------------------------------------------------------
# 1. LightGBM baseline (current production)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("1. LightGBM (current production baseline)")
print("=" * 70)

import lightgbm as lgb

def lgbm_factory():
    return lgb.LGBMRegressor(
        n_estimators=300, max_depth=8, num_leaves=41,
        learning_rate=0.039, feature_fraction=0.93, subsample=0.79,
        objective="huber", alpha=1.0, verbosity=-1, random_state=42, n_jobs=1,
    )

t1 = time.time()
res_lgbm = cv_score(X_vals, y, groups, lgbm_factory, name="LightGBM (prod params)",
                     target_transform="yeo-johnson", monotonic=mono)
print(f"  R2 = {res_lgbm['r2_mean']:+.3f} +/- {res_lgbm['r2_std']:.3f}  MAE = {res_lgbm['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")
print(f"  Folds: {[f'{f:+.3f}' for f in res_lgbm['folds']]}")

# Also test with default LightGBM params (no Optuna tuning)
def lgbm_default_factory():
    return lgb.LGBMRegressor(
        n_estimators=300, max_depth=5, num_leaves=31,
        learning_rate=0.05, objective="huber", alpha=1.0,
        verbosity=-1, random_state=42, n_jobs=1,
    )

t1 = time.time()
res_lgbm_def = cv_score(X_vals, y, groups, lgbm_default_factory,
                         name="LightGBM (defaults)",
                         target_transform="yeo-johnson", monotonic=mono)
print(f"\n  LightGBM defaults: R2 = {res_lgbm_def['r2_mean']:+.3f} +/- {res_lgbm_def['r2_std']:.3f}  MAE = {res_lgbm_def['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")


# ---------------------------------------------------------------------------
# 2. CatBoost
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("2. CatBoost")
print("=" * 70)

from catboost import CatBoostRegressor

# CatBoost with similar complexity to our LightGBM
def catboost_factory():
    return CatBoostRegressor(
        iterations=300, depth=8, learning_rate=0.039,
        l2_leaf_reg=3.0, loss_function="Huber:delta=1.0",
        verbose=0, random_seed=42,
    )

t1 = time.time()
res_cb = cv_score(X_vals, y, groups, catboost_factory, name="CatBoost (matched)",
                   target_transform="yeo-johnson", use_scaler=False)
print(f"  R2 = {res_cb['r2_mean']:+.3f} +/- {res_cb['r2_std']:.3f}  MAE = {res_cb['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")
print(f"  Folds: {[f'{f:+.3f}' for f in res_cb['folds']]}")

# CatBoost with default-ish params
def catboost_default_factory():
    return CatBoostRegressor(
        iterations=500, depth=6, learning_rate=0.05,
        l2_leaf_reg=3.0, loss_function="RMSE",
        verbose=0, random_seed=42,
    )

t1 = time.time()
res_cb_def = cv_score(X_vals, y, groups, catboost_default_factory,
                       name="CatBoost (defaults/RMSE)",
                       target_transform="yeo-johnson", use_scaler=False)
print(f"\n  CatBoost defaults: R2 = {res_cb_def['r2_mean']:+.3f} +/- {res_cb_def['r2_std']:.3f}  MAE = {res_cb_def['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")

# CatBoost with MAE loss (less outlier-sensitive)
def catboost_mae_factory():
    return CatBoostRegressor(
        iterations=500, depth=6, learning_rate=0.05,
        l2_leaf_reg=3.0, loss_function="MAE",
        verbose=0, random_seed=42,
    )

t1 = time.time()
res_cb_mae = cv_score(X_vals, y, groups, catboost_mae_factory,
                       name="CatBoost (MAE loss)",
                       target_transform="yeo-johnson", use_scaler=False)
print(f"  CatBoost MAE: R2 = {res_cb_mae['r2_mean']:+.3f} +/- {res_cb_mae['r2_std']:.3f}  MAE = {res_cb_mae['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")


# ---------------------------------------------------------------------------
# 3. HistGradientBoosting (sklearn native)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("3. HistGradientBoosting (sklearn)")
print("=" * 70)

from sklearn.ensemble import HistGradientBoostingRegressor

def hgb_factory():
    return HistGradientBoostingRegressor(
        max_iter=300, max_depth=8, max_leaf_nodes=41,
        learning_rate=0.039, l2_regularization=0.1,
        loss="squared_error", random_state=42,
    )

t1 = time.time()
res_hgb = cv_score(X_vals, y, groups, hgb_factory, name="HistGB (matched)",
                    target_transform="yeo-johnson", use_scaler=False)
print(f"  R2 = {res_hgb['r2_mean']:+.3f} +/- {res_hgb['r2_std']:.3f}  MAE = {res_hgb['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")
print(f"  Folds: {[f'{f:+.3f}' for f in res_hgb['folds']]}")

# HistGB with absolute_error (robust to outliers, like Huber)
def hgb_abs_factory():
    return HistGradientBoostingRegressor(
        max_iter=500, max_depth=6, max_leaf_nodes=31,
        learning_rate=0.05, l2_regularization=0.1,
        loss="absolute_error", random_state=42,
    )

t1 = time.time()
res_hgb_abs = cv_score(X_vals, y, groups, hgb_abs_factory,
                        name="HistGB (MAE loss)",
                        target_transform="yeo-johnson", use_scaler=False)
print(f"\n  HistGB MAE: R2 = {res_hgb_abs['r2_mean']:+.3f} +/- {res_hgb_abs['r2_std']:.3f}  MAE = {res_hgb_abs['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")


# ---------------------------------------------------------------------------
# 4. LightGBM without Yeo-Johnson (is the transform helping?)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("4. Ablation: LightGBM WITHOUT Yeo-Johnson transform")
print("=" * 70)

t1 = time.time()
res_no_yj = cv_score(X_vals, y, groups, lgbm_factory, name="LightGBM (no YJ)",
                      target_transform=None, monotonic=mono)
print(f"  R2 = {res_no_yj['r2_mean']:+.3f} +/- {res_no_yj['r2_std']:.3f}  MAE = {res_no_yj['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")


# ---------------------------------------------------------------------------
# 5. LightGBM with RMSE loss instead of Huber
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("5. Ablation: LightGBM with RMSE loss (instead of Huber)")
print("=" * 70)

def lgbm_rmse_factory():
    return lgb.LGBMRegressor(
        n_estimators=300, max_depth=8, num_leaves=41,
        learning_rate=0.039, feature_fraction=0.93, subsample=0.79,
        objective="regression", verbosity=-1, random_state=42, n_jobs=1,
    )

t1 = time.time()
res_rmse = cv_score(X_vals, y, groups, lgbm_rmse_factory, name="LightGBM (RMSE)",
                     target_transform="yeo-johnson", monotonic=mono)
print(f"  R2 = {res_rmse['r2_mean']:+.3f} +/- {res_rmse['r2_std']:.3f}  MAE = {res_rmse['mae_mean']:.1f}%  ({time.time()-t1:.1f}s)")


# ---------------------------------------------------------------------------
# 6. Stacking ensemble: LightGBM + CatBoost + HistGB
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("6. Stacking: LightGBM + CatBoost + HistGB")
print("=" * 70)

from sklearn.linear_model import Ridge

n_unique = len(set(groups))
n_splits = min(5, n_unique)
splitter = GroupKFold(n_splits=n_splits)

r2s_stack, maes_stack = [], []

for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
    X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
    y_tr, y_va = y[train_idx], y[val_idx]

    lo, hi = np.percentile(y_tr, [1, 99])
    y_tr_w = np.clip(y_tr, lo, hi)

    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_tr_t = pt.fit_transform(y_tr_w.reshape(-1, 1)).ravel()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    # Train 3 base models
    m1 = lgb.LGBMRegressor(
        n_estimators=300, max_depth=8, num_leaves=41,
        learning_rate=0.039, feature_fraction=0.93, subsample=0.79,
        objective="huber", alpha=1.0, verbosity=-1, random_state=42, n_jobs=1,
    )
    m1.set_params(monotone_constraints=mono)
    m1.fit(X_tr_s, y_tr_t)

    m2 = CatBoostRegressor(
        iterations=300, depth=6, learning_rate=0.05,
        l2_leaf_reg=3.0, loss_function="Huber:delta=1.0",
        verbose=0, random_seed=42,
    )
    m2.fit(X_tr, y_tr_t)

    m3 = HistGradientBoostingRegressor(
        max_iter=300, max_depth=6, max_leaf_nodes=31,
        learning_rate=0.05, l2_regularization=0.1,
        loss="squared_error", random_state=42,
    )
    m3.fit(X_tr, y_tr_t)

    # OOF predictions from inner CV for meta-learner
    # (simplified: use val predictions directly for quick test)
    p1 = pt.inverse_transform(m1.predict(X_va_s).reshape(-1, 1)).ravel()
    p2 = pt.inverse_transform(m2.predict(X_va).reshape(-1, 1)).ravel()
    p3 = pt.inverse_transform(m3.predict(X_va).reshape(-1, 1)).ravel()

    # Simple average blend
    y_pred_avg = (p1 + p2 + p3) / 3

    ss_res = np.sum((y_va - y_pred_avg) ** 2)
    ss_tot = np.sum((y_va - y_va.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    r2s_stack.append(r2)
    maes_stack.append(mean_absolute_error(y_va, y_pred_avg))

t1 = time.time()
print(f"  R2 = {np.mean(r2s_stack):+.3f} +/- {np.std(r2s_stack):.3f}  MAE = {np.mean(maes_stack):.1f}%")
print(f"  Folds: {[f'{f:+.3f}' for f in r2s_stack]}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

results = [
    res_lgbm, res_lgbm_def, res_no_yj, res_rmse,
    res_cb, res_cb_def, res_cb_mae,
    res_hgb, res_hgb_abs,
    {"name": "Stack (LGB+CB+HGB avg)", "r2_mean": np.mean(r2s_stack),
     "r2_std": np.std(r2s_stack), "mae_mean": np.mean(maes_stack)},
]

results.sort(key=lambda r: r["r2_mean"], reverse=True)

print(f"\n{'Model':<35} {'R2':>8} {'+-':>6} {'MAE':>8}")
print("-" * 60)
for r in results:
    marker = " <-- PROD" if r["name"] == "LightGBM (prod params)" else ""
    print(f"  {r['name']:<33} {r['r2_mean']:+.3f}  {r['r2_std']:.3f}  {r['mae_mean']:>6.1f}%{marker}")

best = results[0]
prod = res_lgbm
delta = best["r2_mean"] - prod["r2_mean"]
print(f"\nBest: {best['name']} (R2 delta vs prod: {delta:+.3f})")

if delta > 0.01:
    print("VERDICT: Alternative model beats LightGBM -- worth investigating further")
elif delta > -0.01:
    print("VERDICT: Roughly tied -- stick with LightGBM (better tooling, monotonic constraints)")
else:
    print("VERDICT: LightGBM still wins -- no switch needed")

elapsed = time.time() - t0
print(f"\nTotal time: {elapsed:.0f}s")
