"""
10 - Sales Trend + Subtheme + BrickLink Monthly Sales Features
===============================================================
New features from untapped data:
1. BE sales_trend_json: monthly BrickLink sales counts over time
2. Subtheme identity: finer-grained than theme
3. BrickLink monthly_sales: granular sales data with prices

Run with: .venv/bin/python research/10_sales_subtheme_features.py
"""

import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.inspection import permutation_importance
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

df = db.execute("""
    SELECT
        li.set_number, li.title, li.theme,
        li.parts_count, li.minifig_count,
        be.annual_growth_pct, be.rrp_usd_cents,
        be.rating_value, be.review_count AS be_reviews,
        be.rrp_gbp_cents, be.subtheme,
        be.sales_trend_json, be.value_chart_json,
        be.pieces, be.minifigs AS be_mfigs
    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
""").fetchdf()

# BrickLink monthly sales
bl_sales = db.execute("""
    SELECT item_id, year, month, condition, times_sold, total_quantity,
           avg_price, currency
    FROM bricklink_monthly_sales
    WHERE condition = 'new'
    ORDER BY item_id, year, month
""").fetchdf()

db.close()

print(f"BE sets: {len(df)}")
print(f"BL monthly sales rows: {len(bl_sales)}")

# =========================================================================
# Numeric coercion
# =========================================================================

for col in ["parts_count", "minifig_count", "rrp_usd_cents", "rrp_gbp_cents",
            "be_reviews", "pieces", "be_mfigs", "rating_value"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["parts"] = df["parts_count"].fillna(df["pieces"])
df["mfigs"] = df["minifig_count"].fillna(df["be_mfigs"])
rrp = df["rrp_usd_cents"].fillna(0)
parts = df["parts"].fillna(0)

# =========================================================================
# BASELINE INTRINSICS (same as best model)
# =========================================================================

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

BASELINE = [
    "log_rrp", "log_parts", "price_per_part", "mfigs_val",
    "minifig_density", "price_tier",
    "rating_value", "be_reviews",
    "theme_loo_growth", "theme_size", "is_licensed",
    "usd_gbp_ratio",
]

# =========================================================================
# NEW FEATURE 1: Sales Trend (BE sales_trend_json)
# =========================================================================

def extract_sales_trend(json_val):
    """Extract features from BE monthly sales trend data."""
    if json_val is None or (isinstance(json_val, float) and np.isnan(json_val)):
        return {}
    data = json.loads(json_val) if isinstance(json_val, str) else json_val
    if not isinstance(data, list) or len(data) < 3:
        return {}

    # data is [[date_str, count], ...]
    counts = [float(d[1]) for d in data if d[1] is not None]
    if not counts:
        return {}

    result = {
        "st_avg_sales": np.mean(counts),
        "st_median_sales": np.median(counts),
        "st_total_sales": sum(counts),
        "st_n_months": len(counts),
        "st_std_sales": np.std(counts),
        "st_cv_sales": np.std(counts) / np.mean(counts) if np.mean(counts) > 0 else 0,
    }

    # Trend: last quarter vs first quarter
    if len(counts) >= 6:
        early = np.mean(counts[:3])
        late = np.mean(counts[-3:])
        result["st_trend"] = (late - early) / early * 100 if early > 0 else 0
        # Is demand accelerating or decelerating?
        if len(counts) >= 9:
            mid = np.mean(counts[len(counts)//3 : 2*len(counts)//3])
            result["st_acceleration"] = (late - mid) - (mid - early) if mid > 0 else 0

    # Peak month position (0=early, 1=late)
    peak_idx = np.argmax(counts)
    result["st_peak_position"] = peak_idx / len(counts) if len(counts) > 1 else 0.5

    # Sales consistency: what fraction of months had above-average sales?
    avg = np.mean(counts)
    result["st_above_avg_pct"] = sum(1 for c in counts if c >= avg) / len(counts) * 100

    return result

st_records = [extract_sales_trend(v) for v in df["sales_trend_json"]]
st_df = pd.DataFrame(st_records)
for col in st_df.columns:
    df[col] = st_df[col].values

SALES_TREND = [
    "st_avg_sales", "st_total_sales", "st_n_months",
    "st_cv_sales", "st_trend", "st_peak_position",
    "st_above_avg_pct", "st_acceleration",
]

# =========================================================================
# NEW FEATURE 2: Subtheme encoding
# =========================================================================

# LOO subtheme growth (for subthemes with 2+ sets)
subtheme_counts = df["subtheme"].value_counts()
df["subtheme_size"] = df["subtheme"].map(subtheme_counts).fillna(0)

# Only compute LOO for subthemes with 3+ sets
mask_sub = df["subtheme_size"] >= 3
df.loc[mask_sub, "subtheme_loo_growth"] = loo_mean(
    df[mask_sub], "annual_growth_pct", "subtheme"
)
df["subtheme_loo_growth"] = df["subtheme_loo_growth"].fillna(df["annual_growth_pct"].mean())

SUBTHEME = [
    "subtheme_loo_growth", "subtheme_size",
]

# =========================================================================
# NEW FEATURE 3: BrickLink Monthly Sales
# =========================================================================

# Aggregate BL monthly sales per set
bl_features = {}

for item_id, group in bl_sales.groupby("item_id"):
    set_number = item_id.split("-")[0] if "-" in str(item_id) else str(item_id)

    sold = pd.to_numeric(group["times_sold"], errors="coerce").fillna(0)
    qty = pd.to_numeric(group["total_quantity"], errors="coerce").fillna(0)
    avg_p = pd.to_numeric(group["avg_price"], errors="coerce").fillna(0)

    if len(sold) < 2:
        continue

    bl_features[set_number] = {
        "bl_avg_monthly_sold": sold.mean(),
        "bl_total_sold": sold.sum(),
        "bl_months_active": len(sold),
        "bl_sold_cv": sold.std() / sold.mean() if sold.mean() > 0 else 0,
        "bl_avg_price": avg_p[avg_p > 0].mean() if (avg_p > 0).any() else 0,
        "bl_price_trend": 0,
    }

    # Price trend: last 3 months avg vs first 3 months
    valid_prices = avg_p[avg_p > 0].values
    if len(valid_prices) >= 6:
        early_p = np.mean(valid_prices[:3])
        late_p = np.mean(valid_prices[-3:])
        bl_features[set_number]["bl_price_trend"] = (
            (late_p - early_p) / early_p * 100 if early_p > 0 else 0
        )

    # Sales ramp: were sales increasing over time?
    if len(sold) >= 6:
        early_s = sold.iloc[:3].mean()
        late_s = sold.iloc[-3:].mean()
        bl_features[set_number]["bl_sales_ramp"] = (
            (late_s - early_s) / early_s * 100 if early_s > 0 else 0
        )

for feat in ["bl_avg_monthly_sold", "bl_total_sold", "bl_months_active",
             "bl_sold_cv", "bl_avg_price", "bl_price_trend", "bl_sales_ramp"]:
    df[feat] = df["set_number"].map(
        lambda sn, f=feat: bl_features.get(sn, {}).get(f, np.nan)
    )

BL_MONTHLY = [
    "bl_avg_monthly_sold", "bl_total_sold", "bl_months_active",
    "bl_sold_cv", "bl_price_trend", "bl_sales_ramp",
]

# =========================================================================
# EVALUATE
# =========================================================================

y_reg = df["annual_growth_pct"].values.astype(float)
THRESHOLD = 10.0
y_cls = (y_reg >= THRESHOLD).astype(int)

print(f"\nTarget >= {THRESHOLD}%: {y_cls.sum()} positive ({y_cls.mean()*100:.0f}%)")


def evaluate(features, label):
    valid = [f for f in features if f in df.columns and df[f].notna().sum() >= len(df) * 0.3]
    X = df[valid].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())
    Xs = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns)

    gb_c = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, min_samples_leaf=5,
        learning_rate=0.05, random_state=42,
    )
    gb_r = GradientBoostingRegressor(
        n_estimators=100, max_depth=3, min_samples_leaf=5,
        learning_rate=0.05, random_state=42,
    )

    auc = cross_val_score(
        gb_c, Xs, y_cls,
        cv=RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42),
        scoring="roc_auc",
    )

    y_pred = cross_val_predict(gb_r, Xs, y_reg, cv=LeaveOneOut())
    loo_r2 = r2_score(y_reg, y_pred)
    loo_corr = np.corrcoef(y_reg, y_pred)[0, 1]
    loo_mae = mean_absolute_error(y_reg, y_pred)

    print(f"  {label} ({len(valid)} feats):")
    print(f"    AUC={auc.mean():.3f}+/-{auc.std():.3f}  LOO: R2={loo_r2:.3f}  Corr={loo_corr:.3f}  MAE={loo_mae:.2f}%")
    return loo_r2, loo_corr, auc.mean(), valid, y_pred


# Correlations first
print("\n" + "=" * 70)
print("NEW FEATURE CORRELATIONS")
print("=" * 70)

new_feats = SALES_TREND + SUBTHEME + BL_MONTHLY
corrs = {}
for f in new_feats:
    if f not in df.columns:
        continue
    s = pd.to_numeric(df[f], errors="coerce")
    mask = s.notna()
    if mask.sum() >= 20:
        corrs[f] = s[mask].corr(pd.Series(y_reg)[mask])

for f, c in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True):
    group = "SALES_TR" if f in SALES_TREND else "SUBTHEME" if f in SUBTHEME else "BL_MONTH"
    marker = " ***" if abs(c) > 0.3 else " **" if abs(c) > 0.2 else ""
    print(f"  {f:<25s} r={c:>+.3f}  {group:>10s}{marker}")

# Ablation
print("\n" + "=" * 70)
print("ABLATION")
print("=" * 70)

r2_b, _, auc_b, _, _ = evaluate(BASELINE, "A: Baseline")
evaluate(BASELINE + SALES_TREND, "B: + Sales Trend")
evaluate(BASELINE + SUBTHEME, "C: + Subtheme")
evaluate(BASELINE + BL_MONTHLY, "D: + BL Monthly")
evaluate(BASELINE + SALES_TREND + SUBTHEME, "E: + Sales + Subtheme")
r2_all, corr_all, auc_all, valid_all, yp_all = evaluate(
    BASELINE + SALES_TREND + SUBTHEME + BL_MONTHLY, "F: ALL new features"
)

# Feature importance for best combo
print("\n" + "=" * 70)
print("FEATURE IMPORTANCE")
print("=" * 70)

X = df[valid_all].copy()
for c in X.columns:
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())
Xs = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns)

gb = GradientBoostingRegressor(
    n_estimators=100, max_depth=3, min_samples_leaf=5,
    learning_rate=0.05, random_state=42,
)
gb.fit(Xs, y_reg)
perm = permutation_importance(gb, Xs, y_reg, n_repeats=30, random_state=42, scoring="r2")

for f, p in sorted(zip(valid_all, perm.importances_mean), key=lambda x: x[1], reverse=True):
    group = "SALES" if f in SALES_TREND else "SUB" if f in SUBTHEME else "BL" if f in BL_MONTHLY else "base"
    bar = "#" * max(0, int(p * 12))
    print(f"  {f:<25s} {p:>+6.3f}  {group:>5s}  {bar}")

# Error analysis on breakout sets
print("\n" + "=" * 70)
print("BREAKOUT SETS")
print("=" * 70)

df["pred_new"] = yp_all

# Baseline predictions for comparison
valid_base = [f for f in BASELINE if f in df.columns and df[f].notna().sum() >= len(df) * 0.3]
Xb = df[valid_base].copy()
for c in Xb.columns:
    Xb[c] = pd.to_numeric(Xb[c], errors="coerce")
Xb = Xb.fillna(Xb.median())
Xbs = pd.DataFrame(StandardScaler().fit_transform(Xb), columns=Xb.columns)
gb_b = GradientBoostingRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42)
yp_base = cross_val_predict(gb_b, Xbs, y_reg, cv=LeaveOneOut())
df["pred_base"] = yp_base

print(f"\n{'Set':>6s} {'Title':22s} {'Actual':>7s} {'Base':>6s} {'New':>6s} {'Better?':>8s}")
print("-" * 60)
for _, row in df.nlargest(15, "annual_growth_pct").iterrows():
    better = "YES" if abs(row["annual_growth_pct"] - row["pred_new"]) < abs(row["annual_growth_pct"] - row["pred_base"]) else ""
    print(f"  {row['set_number']:>6s} {str(row['title'])[:20]:22s} {row['annual_growth_pct']:>5.1f}% {row['pred_base']:>5.1f}% {row['pred_new']:>5.1f}% {better:>8s}")

print(f"\n\nSummary: Baseline R2={r2_b:.3f}, New R2={r2_all:.3f}, Delta={r2_all-r2_b:+.3f}")
