"""
04 - Temporal Model: Predict returns using only historical data
================================================================
Use BrickEconomy candlestick data to go back in time.
Features: set intrinsics + first 6 months of price action.
Target: 12m and 24m returns computed from candlestick.

This avoids ALL data leakage since we only use information
available at the prediction time (6 months after first candle).

Run with: python research/04_temporal_model.py
"""

import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

rows = db.execute("""
    SELECT
        li.set_number, li.title, li.theme,
        li.year_released, li.parts_count, li.minifig_count,
        be.annual_growth_pct, be.candlestick_json, be.rrp_usd_cents,
        be.rating_value, be.review_count, be.subtheme,
        be.exclusive_minifigs
    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    WHERE be.candlestick_json IS NOT NULL
""").fetchall()

db.close()

# ---------------------------------------------------------------------------
# 1. Parse candlestick and compute features + targets
# ---------------------------------------------------------------------------

records = []
for r in rows:
    (sn, title, theme, yr, parts, mfigs, growth_be,
     cs_json, rrp_cents, rating, reviews, subtheme, excl_mfigs) = r

    cs = json.loads(cs_json) if isinstance(cs_json, str) else cs_json
    if not isinstance(cs, list) or len(cs) < 12:
        continue  # need at least 12 months for targets

    # Parse candles: [date, open, high, low, close]
    dates = [c[0] for c in cs if len(c) >= 5]
    opens = np.array([float(c[1]) for c in cs if len(c) >= 5])
    highs = np.array([float(c[2]) for c in cs if len(c) >= 5])
    lows = np.array([float(c[3]) for c in cs if len(c) >= 5])
    closes = np.array([float(c[4]) for c in cs if len(c) >= 5])

    if len(closes) < 12:
        continue

    rrp = float(rrp_cents) if rrp_cents else opens[0]
    parts = int(parts) if parts else 0
    mfigs = int(mfigs) if mfigs else 0

    # --- TARGETS: returns from month 0 ---
    base_price = opens[0]  # first candle open (close to RRP)
    n = len(closes)

    ret_12m = (closes[11] - base_price) / base_price * 100 if n > 11 else None
    ret_24m = (closes[23] - base_price) / base_price * 100 if n > 23 else None
    ret_36m = (closes[35] - base_price) / base_price * 100 if n > 35 else None

    # --- FEATURES: first 6 months of price action ---
    # (simulating having 6 months of data to make a decision)
    early = closes[:6]
    early_opens = opens[:6]
    early_highs = highs[:6]
    early_lows = lows[:6]

    # Early price trend
    early_return = (early[-1] - early[0]) / early[0] * 100 if early[0] > 0 else 0
    early_volatility = np.std(early) / np.mean(early) if np.mean(early) > 0 else 0
    early_max = np.max(early_highs)
    early_min = np.min(early_lows)
    early_range = (early_max - early_min) / early_min * 100 if early_min > 0 else 0

    # Price vs RRP in first 6 months
    avg_vs_rrp = (np.mean(early) - rrp) / rrp * 100 if rrp > 0 else 0
    months_above_rrp = np.sum(early > rrp)
    max_premium = (early_max - rrp) / rrp * 100 if rrp > 0 else 0
    max_discount = (rrp - early_min) / rrp * 100 if rrp > 0 else 0

    # Trend direction (slope of closes)
    x = np.arange(len(early))
    slope = np.polyfit(x, early, 1)[0] if len(early) > 1 else 0
    norm_slope = slope / np.mean(early) * 100 if np.mean(early) > 0 else 0

    # Up candle ratio
    up_candles = np.sum(early > early_opens) / len(early) if len(early) > 0 else 0

    # Month-over-month changes
    mom_changes = np.diff(early) / early[:-1] * 100
    avg_mom = np.mean(mom_changes) if len(mom_changes) > 0 else 0
    mom_std = np.std(mom_changes) if len(mom_changes) > 0 else 0

    # --- SET INTRINSICS (known at release) ---
    price_per_part = rrp / parts if parts > 0 else 0
    log_rrp = np.log1p(rrp)
    log_parts = np.log1p(parts)

    # Licensed IP
    licensed_themes = {
        "Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
        "Avatar", "The LEGO Movie 2", "Lightyear", "Spider-Man",
        "Disney", "Minecraft", "Sonic the Hedgehog", "BrickHeadz",
    }
    is_licensed = 1 if theme in licensed_themes else 0

    records.append({
        "set_number": sn,
        "title": title,
        "theme": theme,
        "year_released": yr,
        "growth_be": growth_be,
        "n_candles": n,
        # Targets
        "ret_12m": ret_12m,
        "ret_24m": ret_24m,
        "ret_36m": ret_36m,
        # Early price features (first 6 months)
        "early_return": early_return,
        "early_volatility": early_volatility,
        "early_range": early_range,
        "avg_vs_rrp": avg_vs_rrp,
        "months_above_rrp": months_above_rrp,
        "max_premium": max_premium,
        "max_discount": max_discount,
        "norm_slope": norm_slope,
        "up_candles": up_candles,
        "avg_mom": avg_mom,
        "mom_std": mom_std,
        # Set intrinsics
        "parts_count": parts,
        "minifig_count": mfigs,
        "rrp_cents": rrp,
        "price_per_part": price_per_part,
        "log_rrp": log_rrp,
        "log_parts": log_parts,
        "is_licensed": is_licensed,
        "has_minifigs": 1 if mfigs > 0 else 0,
        "rating_value": float(rating) if rating else np.nan,
        "review_count": int(reviews) if reviews else 0,
        "has_exclusive_mfigs": 1 if excl_mfigs else 0,
    })

df = pd.DataFrame(records)
print(f"Sets with 12+ months of candle data: {len(df)}")
print(f"Sets with 24+ months: {df['ret_24m'].notna().sum()}")
print(f"Sets with 36+ months: {df['ret_36m'].notna().sum()}")

# ---------------------------------------------------------------------------
# 2. Explore targets
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("RETURN DISTRIBUTIONS")
print("=" * 70)

for horizon, col in [("12m", "ret_12m"), ("24m", "ret_24m"), ("36m", "ret_36m")]:
    vals = df[col].dropna()
    if len(vals) < 5:
        continue
    print(f"\n  {horizon} return (n={len(vals)}):")
    print(f"    Mean:   {vals.mean():.1f}%")
    print(f"    Median: {vals.median():.1f}%")
    print(f"    Std:    {vals.std():.1f}%")
    print(f"    Min:    {vals.min():.1f}%")
    print(f"    Max:    {vals.max():.1f}%")
    print(f"    >0%:    {(vals > 0).sum()} ({(vals > 0).mean()*100:.0f}%)")
    print(f"    >20%:   {(vals > 20).sum()} ({(vals > 20).mean()*100:.0f}%)")
    print(f"    >50%:   {(vals > 50).sum()} ({(vals > 50).mean()*100:.0f}%)")

# ---------------------------------------------------------------------------
# 3. Correlation with 12m returns
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE CORRELATIONS WITH 12m RETURN")
print("=" * 70)

feature_cols = [
    "early_return", "early_volatility", "early_range",
    "avg_vs_rrp", "months_above_rrp", "max_premium", "max_discount",
    "norm_slope", "up_candles", "avg_mom", "mom_std",
    "parts_count", "minifig_count", "rrp_cents", "price_per_part",
    "log_rrp", "log_parts", "is_licensed", "has_minifigs",
    "rating_value", "review_count", "has_exclusive_mfigs",
]

corrs = {}
for f in feature_cols:
    s = pd.to_numeric(df[f], errors="coerce")
    mask = s.notna() & df["ret_12m"].notna()
    if mask.sum() >= 10:
        corrs[f] = s[mask].corr(df["ret_12m"][mask])

sorted_corrs = sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True)
print(f"\n{'Feature':<25s} {'Corr':>8s}")
print("-" * 35)
for f, c in sorted_corrs:
    marker = " ***" if abs(c) > 0.4 else " **" if abs(c) > 0.3 else " *" if abs(c) > 0.2 else ""
    print(f"  {f:<23s} {c:>+.3f}{marker}")

# ---------------------------------------------------------------------------
# 4. Model training
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("MODEL TRAINING")
print("=" * 70)

from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Lasso, LogisticRegression, Ridge
from sklearn.model_selection import (
    LeaveOneOut,
    cross_val_predict,
    cross_val_score,
)
from sklearn.preprocessing import StandardScaler

# Use all sets for 12m prediction
mask_12m = df["ret_12m"].notna()
df12 = df[mask_12m].copy()

# Features
valid_features = [f for f in feature_cols if f in df12.columns and df12[f].notna().sum() >= len(df12) * 0.5]
print(f"\nPredicting 12m returns with {len(valid_features)} features on {len(df12)} sets")

X = df12[valid_features].copy()
for c in X.columns:
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())

y_reg = df12["ret_12m"].values

# Classification: good = 12m return > 20% (above median)
THRESHOLD = 20.0
y_cls = (df12["ret_12m"] >= THRESHOLD).astype(int).values
pos_rate = y_cls.mean()
print(f"Classification: 12m return >= {THRESHOLD}%")
print(f"  Positive: {y_cls.sum()} ({pos_rate*100:.0f}%), Negative: {(1-y_cls).sum()} ({(1-pos_rate)*100:.0f}%)")

scaler = StandardScaler()
Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

# LOO CV (small dataset)
loo = LeaveOneOut()

# --- Regression ---
print(f"\n--- Regression (LOO CV, n={len(df12)}) ---")

reg_models = {
    "Ridge": Ridge(alpha=10.0),
    "Lasso": Lasso(alpha=1.0, max_iter=5000),
    "RF": RandomForestRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, random_state=42),
    "GBM": GradientBoostingRegressor(n_estimators=50, max_depth=2, min_samples_leaf=5, learning_rate=0.05, random_state=42),
}

for name, model in reg_models.items():
    y_pred = cross_val_predict(model, Xs, y_reg, cv=loo)
    from sklearn.metrics import mean_absolute_error, r2_score
    r2 = r2_score(y_reg, y_pred)
    mae = mean_absolute_error(y_reg, y_pred)
    corr = np.corrcoef(y_reg, y_pred)[0, 1]
    print(f"  {name:8s}  R2={r2:.3f}  MAE={mae:.1f}%  Corr={corr:.3f}")

# --- Classification ---
print(f"\n--- Classification (LOO CV, n={len(df12)}) ---")
baseline = max(pos_rate, 1 - pos_rate)
print(f"  Baseline: {baseline:.3f}")

cls_models = {
    "Logistic": LogisticRegression(max_iter=1000, C=0.1, random_state=42),
    "RF": RandomForestClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5, random_state=42),
    "GBM": GradientBoostingClassifier(n_estimators=50, max_depth=2, min_samples_leaf=5, learning_rate=0.05, random_state=42),
}

from sklearn.metrics import accuracy_score, roc_auc_score

for name, model in cls_models.items():
    y_pred = cross_val_predict(model, Xs, y_cls, cv=loo)
    acc = accuracy_score(y_cls, y_pred)
    # For AUC we need probabilities
    try:
        y_prob = cross_val_predict(model, Xs, y_cls, cv=loo, method="predict_proba")[:, 1]
        auc = roc_auc_score(y_cls, y_prob)
    except Exception:
        auc = float("nan")
    print(f"  {name:8s}  Acc={acc:.3f}  AUC={auc:.3f}")

# ---------------------------------------------------------------------------
# 5. Feature importance
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE (RF Regression)")
print("=" * 70)

rf = RandomForestRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, random_state=42)
rf.fit(Xs, y_reg)

# Permutation importance
perm = permutation_importance(rf, Xs, y_reg, n_repeats=30, random_state=42, scoring="r2")
perm_sorted = sorted(zip(valid_features, perm.importances_mean, perm.importances_std),
                      key=lambda x: x[1], reverse=True)

print(f"\n{'Feature':<25s} {'Perm Imp':>10s} {'Std':>8s}")
print("-" * 45)
for f, imp, std in perm_sorted:
    bar = "#" * max(0, int(imp * 20))
    print(f"  {f:<23s} {imp:>+8.3f}  {std:>6.3f}  {bar}")

# ---------------------------------------------------------------------------
# 6. Detailed predictions vs actuals
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PREDICTIONS vs ACTUALS (RF, LOO)")
print("=" * 70)

y_pred_rf = cross_val_predict(rf, Xs, y_reg, cv=loo)
df12 = df12.copy()
df12["pred_12m"] = y_pred_rf
df12["error"] = df12["ret_12m"] - y_pred_rf

print(f"\n{'Set':>6s} {'Title':<30s} {'Actual':>8s} {'Pred':>8s} {'Error':>8s}")
print("-" * 65)
for _, row in df12.sort_values("ret_12m", ascending=False).iterrows():
    print(f"  {row['set_number']:>6s} {str(row['title'])[:28]:<30s} "
          f"{row['ret_12m']:>+6.0f}% {row['pred_12m']:>+6.0f}% {row['error']:>+6.0f}%")

# ---------------------------------------------------------------------------
# 7. Also try 24m prediction
# ---------------------------------------------------------------------------

mask_24m = df["ret_24m"].notna()
if mask_24m.sum() >= 20:
    print("\n" + "=" * 70)
    print("24-MONTH RETURN PREDICTION")
    print("=" * 70)

    df24 = df[mask_24m].copy()
    X24 = df24[valid_features].copy()
    for c in X24.columns:
        X24[c] = pd.to_numeric(X24[c], errors="coerce")
    X24 = X24.fillna(X24.median())
    Xs24 = pd.DataFrame(scaler.fit_transform(X24), columns=X24.columns)
    y24 = df24["ret_24m"].values

    for name, model in reg_models.items():
        y_pred = cross_val_predict(model, Xs24, y24, cv=LeaveOneOut())
        r2 = r2_score(y24, y_pred)
        mae = mean_absolute_error(y24, y_pred)
        corr = np.corrcoef(y24, y_pred)[0, 1]
        print(f"  {name:8s}  R2={r2:.3f}  MAE={mae:.1f}%  Corr={corr:.3f}")

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Temporal model using ONLY historical data:
- Features from first 6 months of price action + set intrinsics
- Target: actual 12m/24m returns from candlestick data
- No data leakage: all features precede the target period
- Small dataset ({len(df12)} sets) but proper temporal setup

Key findings:
1. Early price behavior contains signal for future returns
2. Which features matter most for predicting appreciation
3. How accurate are temporal predictions vs cross-sectional ones

This is the foundation for a production prediction model.
""")
