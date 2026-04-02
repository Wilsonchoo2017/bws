"""
08 - Combined: Intrinsics + Temporal Candlestick + Keepa Timeline
==================================================================
For the ~40 sets that have ALL data sources, combine:
- Set intrinsics (theme, parts, price - exp 05)
- Early candlestick features (first 6m price action - exp 04)
- Pre-OOS Amazon features (Keepa timeline - exp 07)

Also try theme-specific models for Star Wars (largest theme).

Run with: .venv/bin/python research/08_combined_temporal_intrinsics.py
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import (
    LeaveOneOut,
    RepeatedKFold,
    RepeatedStratifiedKFold,
    cross_val_predict,
    cross_val_score,
)
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

# ---------------------------------------------------------------------------
# 1. Load all data
# ---------------------------------------------------------------------------

# All BE sets with growth + RRP (intrinsics model base)
df_all = db.execute("""
    SELECT
        li.set_number, li.title, li.theme,
        li.parts_count, li.minifig_count, li.weight,
        be.annual_growth_pct, be.rrp_usd_cents,
        be.rating_value, be.review_count AS be_reviews,
        be.exclusive_minifigs, be.subtheme_avg_growth_pct,
        be.pieces, be.minifigs AS be_mfigs,
        be.candlestick_json,
        be.rrp_gbp_cents
    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    WHERE be.annual_growth_pct IS NOT NULL
      AND be.rrp_usd_cents > 0
""").fetchdf()

# Keepa data
df_keepa = db.execute("""
    SELECT set_number, amazon_price_json, buy_box_json, new_3p_fba_json,
           tracking_users, review_count AS kp_reviews, rating AS kp_rating
    FROM keepa_snapshots
    WHERE amazon_price_json IS NOT NULL
""").fetchdf()

db.close()

print(f"BE sets with growth+RRP: {len(df_all)}")
print(f"Keepa sets with Amazon history: {len(df_keepa)}")

# ---------------------------------------------------------------------------
# 2. Feature engineering
# ---------------------------------------------------------------------------

df = df_all.copy()
for col in ["parts_count", "minifig_count", "weight", "rrp_usd_cents",
            "rrp_gbp_cents", "be_reviews", "subtheme_avg_growth_pct",
            "pieces", "be_mfigs", "rating_value"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["parts"] = df["parts_count"].fillna(df["pieces"])
df["mfigs"] = df["minifig_count"].fillna(df["be_mfigs"])
rrp = df["rrp_usd_cents"].fillna(0)
parts = df["parts"].fillna(0)

# --- INTRINSICS ---
df["log_rrp"] = np.log1p(rrp)
df["log_parts"] = np.log1p(parts)
df["price_per_part"] = np.where(parts > 0, rrp / parts, np.nan)
df["mfigs_val"] = df["mfigs"].fillna(0)
df["minifig_density"] = np.where(parts > 0, df["mfigs"].fillna(0) / parts * 100, np.nan)
df["price_tier"] = pd.cut(rrp / 100, bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999],
                           labels=range(1, 9)).astype(float)

LICENSED = {"Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
            "Avatar", "The LEGO Movie 2", "Disney", "Minecraft", "BrickHeadz"}
df["is_licensed"] = df["theme"].isin(LICENSED).astype(int)

def loo_mean(d, col, group):
    s = d.groupby(group)[col].transform("sum")
    c = d.groupby(group)[col].transform("count")
    return ((s - d[col]) / (c - 1)).fillna(d[col].mean())

df["theme_loo_growth"] = loo_mean(df, "annual_growth_pct", "theme")
df["theme_size"] = df["theme"].map(df["theme"].value_counts())

_gbp = df["rrp_gbp_cents"].fillna(0)
df["usd_gbp_ratio"] = np.where(_gbp > 0, rrp / _gbp, np.nan)

# --- CANDLESTICK (temporal) ---
def extract_candle_features(cs_json, rrp_val):
    if cs_json is None or (isinstance(cs_json, float) and np.isnan(cs_json)):
        return {}
    cs = json.loads(cs_json) if isinstance(cs_json, str) else cs_json
    if not isinstance(cs, list) or len(cs) < 6:
        return {}

    opens = [c[1] for c in cs if len(c) >= 5 and c[1]]
    closes = [c[4] for c in cs if len(c) >= 5 and c[4]]

    if not opens or not closes or len(closes) < 6:
        return {}

    early = closes[:6]
    early_opens = [c[1] for c in cs[:6] if len(c) >= 5]
    early_highs = [c[2] for c in cs[:6] if len(c) >= 5]
    early_lows = [c[3] for c in cs[:6] if len(c) >= 5]

    rrp_v = float(rrp_val) if rrp_val and rrp_val > 0 else early[0]

    return {
        "cs_early_return": (early[-1] - early[0]) / early[0] * 100 if early[0] > 0 else 0,
        "cs_early_vol": np.std(early) / np.mean(early) if np.mean(early) > 0 else 0,
        "cs_avg_vs_rrp": (np.mean(early) - rrp_v) / rrp_v * 100 if rrp_v > 0 else 0,
        "cs_up_pct": sum(1 for i in range(len(early)) if early[i] > early_opens[i]) / len(early) if early_opens else 0,
        "cs_max_discount": (rrp_v - min(early_lows)) / rrp_v * 100 if early_lows and rrp_v > 0 else 0,
        "cs_n_candles": len(cs),
    }

candle_records = []
for _, row in df.iterrows():
    candle_records.append(extract_candle_features(row["candlestick_json"], row["rrp_usd_cents"]))

cs_df = pd.DataFrame(candle_records)
for col in cs_df.columns:
    df[col] = cs_df[col].values

# --- KEEPA TIMELINE ---
keepa_features = {}
for _, row in df_keepa.iterrows():
    sn = row["set_number"]
    amz = json.loads(row["amazon_price_json"]) if isinstance(row["amazon_price_json"], str) else row["amazon_price_json"]
    if not isinstance(amz, list) or len(amz) < 5:
        continue

    prices = []
    oos_date = None
    last_price = None
    for point in amz:
        if point[1] is not None and point[1] > 0:
            prices.append(point[1])
            last_price = point[1]
        elif point[1] is None and last_price is not None and oos_date is None:
            oos_date = point[0]

    if not prices:
        continue

    keepa_features[sn] = {
        "kp_below_rrp_pct": 0,  # will be computed per-set with RRP
        "kp_price_trend": 0,
        "kp_price_cv": np.std(prices) / np.mean(prices) if np.mean(prices) > 0 else 0,
        "kp_n_points": len(prices),
        "kp_avg_price": np.mean(prices),
        "kp_min_price": min(prices),
        "kp_tracking": int(row["tracking_users"]) if pd.notna(row["tracking_users"]) else 0,
    }
    if len(prices) >= 6:
        early_p = np.mean(prices[:3])
        late_p = np.mean(prices[-3:])
        keepa_features[sn]["kp_price_trend"] = (late_p - early_p) / early_p * 100 if early_p > 0 else 0

# Merge Keepa
for feat in ["kp_below_rrp_pct", "kp_price_trend", "kp_price_cv", "kp_n_points", "kp_tracking"]:
    df[feat] = df["set_number"].map(lambda sn: keepa_features.get(sn, {}).get(feat, np.nan))

# Compute below_rrp_pct properly
for idx, row in df.iterrows():
    sn = row["set_number"]
    if sn in keepa_features and row["rrp_usd_cents"] and row["rrp_usd_cents"] > 0:
        rrp_v = row["rrp_usd_cents"]
        kf = keepa_features[sn]
        # Need original prices - recompute from avg/min
        # Actually just use the stored feature
        pass

# ---------------------------------------------------------------------------
# 3. Define feature groups
# ---------------------------------------------------------------------------

INTRINSICS = [
    "log_rrp", "log_parts", "price_per_part", "mfigs_val",
    "minifig_density", "price_tier",
    "rating_value", "be_reviews",
    "theme_loo_growth", "theme_size", "is_licensed",
    "usd_gbp_ratio", "subtheme_avg_growth_pct",
]

TEMPORAL = [
    "cs_early_return", "cs_early_vol", "cs_avg_vs_rrp",
    "cs_up_pct", "cs_max_discount", "cs_n_candles",
]

KEEPA = [
    "kp_price_trend", "kp_price_cv", "kp_tracking",
]

y_all = df["annual_growth_pct"].values.astype(float)
THRESHOLD = 10.0

# ---------------------------------------------------------------------------
# 4. Full dataset: intrinsics only (baseline)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print(f"PART 1: FULL DATASET ({len(df)} sets)")
print("=" * 70)

def evaluate(X_df, y, label, features):
    valid = [f for f in features if f in X_df.columns and X_df[f].notna().sum() >= len(X_df) * 0.3]
    X = X_df[valid].copy()
    for c in X.columns: X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())
    Xs = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns)

    y_cls = (y >= THRESHOLD).astype(int)
    baseline = max(y_cls.mean(), 1 - y_cls.mean())

    gb_r = GradientBoostingRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42)
    gb_c = GradientBoostingClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42)

    cv_cls = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
    cv_reg = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)

    auc = cross_val_score(gb_c, Xs, y_cls, cv=cv_cls, scoring="roc_auc")
    r2 = cross_val_score(gb_r, Xs, y, cv=cv_reg, scoring="r2")
    mae = cross_val_score(gb_r, Xs, y, cv=cv_reg, scoring="neg_mean_absolute_error")

    y_pred = cross_val_predict(gb_r, Xs, y, cv=LeaveOneOut())
    loo_r2 = r2_score(y, y_pred)
    loo_corr = np.corrcoef(y, y_pred)[0, 1]
    loo_mae = mean_absolute_error(y, y_pred)

    print(f"\n  {label} ({len(valid)} feats, n={len(y)}):")
    print(f"    CV:  AUC={auc.mean():.3f}  R2={r2.mean():.3f}  MAE={-mae.mean():.2f}%")
    print(f"    LOO: R2={loo_r2:.3f}  Corr={loo_corr:.3f}  MAE={loo_mae:.2f}%")
    print(f"    Baseline: {baseline:.3f}")

    return loo_r2, loo_corr, auc.mean(), valid, y_pred

# Full dataset: intrinsics
r2_base, _, auc_base, _, _ = evaluate(df, y_all, "Intrinsics only", INTRINSICS)

# ---------------------------------------------------------------------------
# 5. Temporal subset: sets with candlestick data
# ---------------------------------------------------------------------------

has_candle = df["cs_early_return"].notna()
df_cs = df[has_candle].copy()
y_cs = df_cs["annual_growth_pct"].values.astype(float)

print(f"\n" + "=" * 70)
print(f"PART 2: CANDLESTICK SUBSET ({len(df_cs)} sets)")
print("=" * 70)

evaluate(df_cs, y_cs, "Intrinsics only", INTRINSICS)
evaluate(df_cs, y_cs, "Temporal only", TEMPORAL)
evaluate(df_cs, y_cs, "Intrinsics + Temporal", INTRINSICS + TEMPORAL)

# ---------------------------------------------------------------------------
# 6. Keepa subset: sets with Amazon timeline
# ---------------------------------------------------------------------------

has_keepa = df["kp_price_trend"].notna()
df_kp = df[has_keepa].copy()
y_kp = df_kp["annual_growth_pct"].values.astype(float)

print(f"\n" + "=" * 70)
print(f"PART 3: KEEPA TIMELINE SUBSET ({len(df_kp)} sets)")
print("=" * 70)

evaluate(df_kp, y_kp, "Intrinsics only", INTRINSICS)
evaluate(df_kp, y_kp, "Keepa timeline only", KEEPA)
evaluate(df_kp, y_kp, "Intrinsics + Keepa", INTRINSICS + KEEPA)

# ---------------------------------------------------------------------------
# 7. Triple overlap: sets with everything
# ---------------------------------------------------------------------------

has_all = has_candle & has_keepa
df_triple = df[has_all].copy()
y_triple = df_triple["annual_growth_pct"].values.astype(float)

if len(df_triple) >= 15:
    print(f"\n" + "=" * 70)
    print(f"PART 4: TRIPLE OVERLAP ({len(df_triple)} sets)")
    print("=" * 70)

    evaluate(df_triple, y_triple, "Intrinsics only", INTRINSICS)
    evaluate(df_triple, y_triple, "All features", INTRINSICS + TEMPORAL + KEEPA)

# ---------------------------------------------------------------------------
# 8. Star Wars specific model
# ---------------------------------------------------------------------------

df_sw = df[df["theme"] == "Star Wars"].copy()
y_sw = df_sw["annual_growth_pct"].values.astype(float)

if len(df_sw) >= 15:
    print(f"\n" + "=" * 70)
    print(f"PART 5: STAR WARS ONLY ({len(df_sw)} sets)")
    print("=" * 70)

    # Can't use theme features for single-theme model
    SW_INTRINSICS = [f for f in INTRINSICS if f not in ("theme_loo_growth", "theme_size", "is_licensed")]
    SW_TEMPORAL = TEMPORAL

    has_sw_candle = df_sw["cs_early_return"].notna()
    n_sw_candle = has_sw_candle.sum()

    evaluate(df_sw, y_sw, "SW Intrinsics", SW_INTRINSICS)

    if n_sw_candle >= 15:
        df_sw_cs = df_sw[has_sw_candle].copy()
        y_sw_cs = df_sw_cs["annual_growth_pct"].values.astype(float)
        evaluate(df_sw_cs, y_sw_cs, "SW Intrinsics + Temporal", SW_INTRINSICS + SW_TEMPORAL)

# ---------------------------------------------------------------------------
# 9. Feature importance for best model
# ---------------------------------------------------------------------------

print(f"\n" + "=" * 70)
print("FEATURE IMPORTANCE (Full dataset, intrinsics)")
print("=" * 70)

valid = [f for f in INTRINSICS if f in df.columns and df[f].notna().sum() >= len(df) * 0.3]
X = df[valid].copy()
for c in X.columns: X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())
Xs = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns)

gb = GradientBoostingRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42)
gb.fit(Xs, y_all)
perm = permutation_importance(gb, Xs, y_all, n_repeats=30, random_state=42, scoring="r2")

for f, p in sorted(zip(valid, perm.importances_mean), key=lambda x: x[1], reverse=True):
    bar = "#" * max(0, int(p * 15))
    print(f"  {f:<25s} {p:>+6.3f}  {bar}")

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Experiment 08: Combined feature sets

Full dataset: {len(df)} sets (intrinsics only)
Candlestick subset: {has_candle.sum()} sets
Keepa timeline subset: {has_keepa.sum()} sets
Triple overlap: {has_all.sum()} sets
Star Wars: {len(df_sw)} sets

Question: Does combining data sources beat intrinsics alone?
""")
