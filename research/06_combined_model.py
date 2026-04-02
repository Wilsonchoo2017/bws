"""
06 - Combined Model: Intrinsics + Keepa + Google Trends
=========================================================
Combine set intrinsics (exp 05) with Amazon/Keepa demand signals
and Google Trends search interest. 178 sets have all 3 sources.

Keepa features are demand-side signals (tracking users, ratings,
Amazon discount) that capture consumer interest. Google Trends
captures search buzz. Both are arguably available near retirement.

Run with: python research/06_combined_model.py
"""

import warnings
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
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
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
# Load: sets with BE + Keepa (178 sets)
# ---------------------------------------------------------------------------

df_full = db.execute("""
    SELECT
        li.set_number, li.title, li.theme,
        li.year_released, li.parts_count, li.minifig_count, li.weight,

        be.annual_growth_pct,
        be.rrp_usd_cents, be.rrp_gbp_cents, be.rrp_eur_cents,
        be.rating_value, be.review_count AS be_review_count,
        be.exclusive_minifigs, be.subtheme,
        be.subtheme_avg_growth_pct,
        be.pieces AS be_pieces, be.minifigs AS be_minifigs,

        ks.current_new_cents   AS keepa_new_cents,
        ks.current_buy_box_cents AS keepa_bb_cents,
        ks.current_amazon_cents AS keepa_amz_cents,
        ks.lowest_ever_cents   AS keepa_lowest,
        ks.highest_ever_cents  AS keepa_highest,
        ks.rating              AS keepa_rating,
        ks.review_count        AS keepa_reviews,
        ks.tracking_users      AS keepa_tracking

    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    JOIN keepa_snapshots ks ON li.set_number = ks.set_number
    WHERE be.annual_growth_pct IS NOT NULL
      AND be.value_new_cents IS NOT NULL
      AND be.rrp_usd_cents IS NOT NULL AND be.rrp_usd_cents > 0
""").fetchdf()

# Also load Google Trends for those that have it
gt_rows = db.execute("""
    SELECT set_number, peak_value, average_value
    FROM google_trends_snapshots
""").fetchdf()

db.close()

# Merge GT
df = df_full.merge(gt_rows, on="set_number", how="left")

print(f"Loaded {len(df)} sets (BE + Keepa)")
print(f"  With Google Trends: {df['peak_value'].notna().sum()}")

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

for col in ["parts_count", "minifig_count", "weight", "rrp_usd_cents",
            "rrp_gbp_cents", "rrp_eur_cents", "be_review_count",
            "subtheme_avg_growth_pct", "be_pieces", "be_minifigs",
            "rating_value", "keepa_new_cents", "keepa_bb_cents",
            "keepa_amz_cents", "keepa_lowest", "keepa_highest",
            "keepa_rating", "keepa_reviews", "keepa_tracking",
            "peak_value", "average_value"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# --- Intrinsics (same as exp 05) ---
df["parts"] = df["parts_count"].fillna(df["be_pieces"])
df["mfigs"] = df["minifig_count"].fillna(df["be_minifigs"])

rrp = df["rrp_usd_cents"].fillna(0)
parts = df["parts"].fillna(0)

df["rrp_usd"] = rrp / 100.0
df["log_rrp"] = np.log1p(rrp)
df["log_parts"] = np.log1p(parts)
df["price_per_part"] = np.where(parts > 0, rrp / parts, np.nan)
df["has_minifigs"] = (df["mfigs"].fillna(0) > 0).astype(int)
df["minifig_density"] = np.where(parts > 0, df["mfigs"].fillna(0) / parts * 100, np.nan)

weight = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
df["weight_per_part"] = np.where(parts > 0, weight / parts, np.nan)
df["price_per_gram"] = np.where(weight > 0, rrp / weight, np.nan)

df["price_tier"] = pd.cut(
    df["rrp_usd"].fillna(0),
    bins=[0, 15, 30, 50, 80, 120, 200, 500, float("inf")],
    labels=[1, 2, 3, 4, 5, 6, 7, 8],
).astype(float)

df["parts_bucket"] = pd.cut(
    parts, bins=[0, 50, 150, 300, 500, 800, 1200, 2000, float("inf")],
    labels=[1, 2, 3, 4, 5, 6, 7, 8],
).astype(float)

LICENSED_THEMES = {
    "Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
    "Avatar", "The LEGO Movie 2", "Lightyear", "Spider-Man",
    "Disney", "Minecraft", "Sonic the Hedgehog", "BrickHeadz",
    "Overwatch", "Stranger Things", "Trolls World Tour",
}
df["is_licensed"] = df["theme"].isin(LICENSED_THEMES).astype(int)

# LOO theme growth
def loo_theme_mean(dataframe: pd.DataFrame) -> pd.Series:
    theme_sum = dataframe.groupby("theme")["annual_growth_pct"].transform("sum")
    theme_count = dataframe.groupby("theme")["annual_growth_pct"].transform("count")
    own_val = dataframe["annual_growth_pct"]
    return (theme_sum - own_val) / (theme_count - 1)

df["theme_loo_growth"] = loo_theme_mean(df)
df["theme_loo_growth"] = df["theme_loo_growth"].fillna(df["annual_growth_pct"].mean())

theme_counts = df["theme"].value_counts()
df["theme_size"] = df["theme"].map(theme_counts)

df["has_exclusive_mfigs"] = df["exclusive_minifigs"].notna().astype(int)

_gbp = df["rrp_gbp_cents"].fillna(0)
_eur = df["rrp_eur_cents"].fillna(0)
df["usd_gbp_ratio"] = np.where(_gbp > 0, rrp / _gbp, np.nan)
df["usd_eur_ratio"] = np.where(_eur > 0, rrp / _eur, np.nan)

# --- Keepa features (Amazon demand signals) ---
keepa_new = df["keepa_new_cents"].fillna(0)
keepa_amz = df["keepa_amz_cents"].fillna(0)
keepa_lo = df["keepa_lowest"].fillna(0)
keepa_hi = df["keepa_highest"].fillna(0)

# Discount from RRP (how much Amazon discounts)
df["keepa_discount_pct"] = np.where(
    rrp > 0, (rrp - keepa_new) / rrp * 100, np.nan
)

# Amazon vs 3P price gap
df["keepa_amz_vs_3p"] = np.where(
    keepa_new > 0, (keepa_amz - keepa_new) / keepa_new * 100, np.nan
)

# Price volatility on Amazon
df["keepa_price_range_pct"] = np.where(
    keepa_lo > 0, (keepa_hi - keepa_lo) / keepa_lo * 100, np.nan
)

# Demand signals
df["log_keepa_tracking"] = np.log1p(df["keepa_tracking"].fillna(0))
df["log_keepa_reviews"] = np.log1p(df["keepa_reviews"].fillna(0))
df["keepa_rating_val"] = df["keepa_rating"]

# Reviews per dollar (normalized interest)
df["keepa_reviews_per_dollar"] = np.where(
    df["rrp_usd"] > 0,
    df["keepa_reviews"].fillna(0) / df["rrp_usd"],
    np.nan,
)

# Tracking users per dollar
df["keepa_tracking_per_dollar"] = np.where(
    df["rrp_usd"] > 0,
    df["keepa_tracking"].fillna(0) / df["rrp_usd"],
    np.nan,
)

# --- Google Trends features ---
df["gt_peak"] = df["peak_value"]
df["gt_avg"] = df["average_value"]
df["gt_peak_avg_ratio"] = np.where(
    df["gt_avg"] > 0,
    df["gt_peak"] / df["gt_avg"],
    np.nan,
)

# ---------------------------------------------------------------------------
# Feature sets
# ---------------------------------------------------------------------------

INTRINSICS = [
    "log_parts", "log_rrp", "price_per_part", "parts_bucket", "price_tier",
    "mfigs", "has_minifigs", "minifig_density",
    "weight_per_part",
    "rating_value", "be_review_count",
    "theme_loo_growth", "theme_size", "is_licensed",
    "has_exclusive_mfigs",
    "usd_gbp_ratio", "usd_eur_ratio",
    "subtheme_avg_growth_pct",
]

KEEPA_FEATURES = [
    "keepa_discount_pct",
    "keepa_amz_vs_3p",
    "keepa_price_range_pct",
    "log_keepa_tracking",
    "log_keepa_reviews",
    "keepa_rating_val",
    "keepa_reviews_per_dollar",
    "keepa_tracking_per_dollar",
]

GT_FEATURES = [
    "gt_peak", "gt_avg", "gt_peak_avg_ratio",
]

ALL_FEATURES = INTRINSICS + KEEPA_FEATURES + GT_FEATURES

# Filter to valid features
def get_valid(feature_list, min_coverage=0.4):
    valid = []
    for f in feature_list:
        if f not in df.columns:
            continue
        s = pd.to_numeric(df[f], errors="coerce")
        cov = s.notna().sum() / len(df) * 100
        if cov >= min_coverage * 100:
            valid.append(f)
    return valid

valid_intrinsics = get_valid(INTRINSICS)
valid_keepa = get_valid(KEEPA_FEATURES)
valid_gt = get_valid(GT_FEATURES)
valid_all = get_valid(ALL_FEATURES)

print(f"\nValid features: {len(valid_intrinsics)} intrinsics, {len(valid_keepa)} keepa, {len(valid_gt)} GT, {len(valid_all)} total")

# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------

y_reg = df["annual_growth_pct"].values.astype(float)
THRESHOLD = 10.0
y_cls = (y_reg >= THRESHOLD).astype(int)
print(f"\nTarget: growth >= {THRESHOLD}%")
print(f"  Positive: {y_cls.sum()} ({y_cls.mean()*100:.0f}%), Negative: {(1-y_cls).sum()}")

# ---------------------------------------------------------------------------
# Compare feature sets: intrinsics vs intrinsics+keepa vs all
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE SET COMPARISON")
print("=" * 70)

cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
rcv = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)
scaler = StandardScaler()

feature_sets = {
    "Intrinsics only": valid_intrinsics,
    "Intrinsics + Keepa": valid_intrinsics + valid_keepa,
    "Intrinsics + Keepa + GT": valid_all,
}

for fs_name, features in feature_sets.items():
    X = df[features].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())
    Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

    gb_cls = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, min_samples_leaf=5,
        learning_rate=0.05, random_state=42
    )
    gb_reg = GradientBoostingRegressor(
        n_estimators=100, max_depth=3, min_samples_leaf=5,
        learning_rate=0.05, random_state=42
    )

    acc = cross_val_score(gb_cls, Xs, y_cls, cv=cv, scoring="accuracy")
    auc = cross_val_score(gb_cls, Xs, y_cls, cv=cv, scoring="roc_auc")
    r2 = cross_val_score(gb_reg, Xs, y_reg, cv=rcv, scoring="r2")
    mae = cross_val_score(gb_reg, Xs, y_reg, cv=rcv, scoring="neg_mean_absolute_error")

    print(f"\n  {fs_name} ({len(features)} features):")
    print(f"    Classification: Acc={acc.mean():.3f}+/-{acc.std():.3f}  AUC={auc.mean():.3f}+/-{auc.std():.3f}")
    print(f"    Regression:     R2={r2.mean():.3f}+/-{r2.std():.3f}  MAE={-mae.mean():.2f}%+/-{mae.std():.2f}%")

# ---------------------------------------------------------------------------
# Best model: full feature set analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("BEST MODEL ANALYSIS (Intrinsics + Keepa + GT)")
print("=" * 70)

X = df[valid_all].copy()
for c in X.columns:
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())
Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

# Multiple classifiers
baseline = max(y_cls.mean(), 1 - y_cls.mean())
print(f"\nBaseline: {baseline:.3f}  (n={len(df)})")

models_cls = {
    "Logistic": LogisticRegression(max_iter=1000, C=0.5, random_state=42),
    "RF": RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=4, random_state=42),
    "GBM": GradientBoostingClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42),
}

for name, model in models_cls.items():
    acc = cross_val_score(model, Xs, y_cls, cv=cv, scoring="accuracy")
    auc = cross_val_score(model, Xs, y_cls, cv=cv, scoring="roc_auc")
    print(f"  {name:12s}  Acc={acc.mean():.3f}+/-{acc.std():.3f}  AUC={auc.mean():.3f}+/-{auc.std():.3f}")

models_reg = {
    "Ridge": Ridge(alpha=10.0),
    "RF": RandomForestRegressor(n_estimators=200, max_depth=5, min_samples_leaf=4, random_state=42),
    "GBM": GradientBoostingRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42),
}

print()
for name, model in models_reg.items():
    r2 = cross_val_score(model, Xs, y_reg, cv=rcv, scoring="r2")
    mae = cross_val_score(model, Xs, y_reg, cv=rcv, scoring="neg_mean_absolute_error")
    print(f"  {name:12s}  R2={r2.mean():.3f}+/-{r2.std():.3f}  MAE={-mae.mean():.2f}%+/-{mae.std():.2f}%")

# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE (GBM, full feature set)")
print("=" * 70)

gb = GradientBoostingRegressor(
    n_estimators=100, max_depth=3, min_samples_leaf=5,
    learning_rate=0.05, random_state=42
)
gb.fit(Xs, y_reg)

perm = permutation_importance(gb, Xs, y_reg, n_repeats=30, random_state=42, scoring="r2")
sorted_imp = sorted(zip(valid_all, perm.importances_mean, gb.feature_importances_),
                     key=lambda x: x[1], reverse=True)

print(f"\n{'Feature':<28s} {'Perm':>8s} {'Tree':>8s} {'Source':>10s}")
print("-" * 58)
for f, p, t in sorted_imp:
    source = "KEEPA" if f in KEEPA_FEATURES else "GT" if f in GT_FEATURES else "intrinsic"
    bar = "#" * max(0, int(p * 20))
    print(f"  {f:<26s} {p:>+6.3f}  {t:>6.3f}  {source:>10s}  {bar}")

# ---------------------------------------------------------------------------
# Correlation with growth
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRELATIONS (all features)")
print("=" * 70)

corrs = {}
for f in valid_all:
    s = pd.to_numeric(df[f], errors="coerce")
    mask = s.notna()
    if mask.sum() >= 20:
        corrs[f] = s[mask].corr(pd.Series(y_reg)[mask])

for f, c in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True):
    source = "KEEPA" if f in KEEPA_FEATURES else "GT" if f in GT_FEATURES else ""
    marker = " ***" if abs(c) > 0.3 else " **" if abs(c) > 0.2 else ""
    print(f"  {f:<26s} {c:>+.3f}{marker}  {source}")

# ---------------------------------------------------------------------------
# LOO Error analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ERROR ANALYSIS (LOO)")
print("=" * 70)

loo = LeaveOneOut()
y_pred = cross_val_predict(gb, Xs, y_reg, cv=loo)
errors = y_reg - y_pred

print(f"\n  R2:          {r2_score(y_reg, y_pred):.3f}")
print(f"  MAE:         {mean_absolute_error(y_reg, y_pred):.2f}%")
print(f"  Correlation: {np.corrcoef(y_reg, y_pred)[0,1]:.3f}")

# Accuracy by bucket
df["pred"] = y_pred
df["error"] = errors
df["growth_bucket"] = pd.cut(df["annual_growth_pct"], bins=[0, 5, 8, 10, 12, 15, 20, 100])
df["pred_cls"] = (y_pred >= THRESHOLD).astype(int)

bucket_acc = df.groupby("growth_bucket", observed=True).agg(
    n=("set_number", "count"),
    cls_acc=("pred_cls", lambda x: (x == df.loc[x.index, "good_inv"]).mean()
             if "good_inv" in df.columns else np.nan),
    mae=("error", lambda x: np.abs(x).mean()),
).reset_index()

print(f"\n  Growth bucket accuracy:")
for _, row in bucket_acc.iterrows():
    print(f"    {str(row['growth_bucket']):12s}  n={row['n']:3.0f}  MAE={row['mae']:.1f}%")

# Biggest misses
print(f"\n  Top 5 underpredictions:")
top_under = df.nlargest(5, "error")
for _, row in top_under.iterrows():
    print(f"    {row['set_number']:>7s} {str(row['title'])[:30]:30s} actual={row['annual_growth_pct']:.1f}% pred={row['pred']:.1f}%")

print(f"\n  Top 5 overpredictions:")
top_over = df.nsmallest(5, "error")
for _, row in top_over.iterrows():
    print(f"    {row['set_number']:>7s} {str(row['title'])[:30]:30s} actual={row['annual_growth_pct']:.1f}% pred={row['pred']:.1f}%")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Combined model on {len(df)} sets:
- Intrinsics: {len(valid_intrinsics)} features (set DNA)
- Keepa: {len(valid_keepa)} features (Amazon demand)
- Google Trends: {len(valid_gt)} features (search interest)
- Total: {len(valid_all)} features

Key question: Do Keepa/GT features add signal beyond intrinsics?
""")
