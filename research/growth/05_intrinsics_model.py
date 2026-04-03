"""
05 - Intrinsics-Only Model: 266 sets using set characteristics only
====================================================================
Use the larger dataset of sets with BE value_new + RRP + annual_growth.
Features: only set intrinsics and theme info (known at release).
No current prices, no BrickLink, no candlestick = zero leakage.

Target: annual_growth_pct from BrickEconomy.

Run with: python research/05_intrinsics_model.py
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
from sklearn.linear_model import Lasso, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
)
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
        li.year_released, li.parts_count, li.minifig_count,
        li.weight,

        be.annual_growth_pct,
        be.rrp_usd_cents,
        be.rrp_gbp_cents,
        be.rrp_eur_cents,
        be.rating_value,
        be.review_count         AS be_review_count,
        be.exclusive_minifigs,
        be.subtheme,
        be.subtheme_avg_growth_pct,
        be.pieces               AS be_pieces,
        be.minifigs             AS be_minifigs,
        be.theme_rank,
        be.designer

    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    WHERE be.annual_growth_pct IS NOT NULL
      AND be.value_new_cents IS NOT NULL
      AND be.rrp_usd_cents IS NOT NULL
      AND be.rrp_usd_cents > 0
""").fetchdf()

db.close()

print(f"Loaded {len(df)} sets with intrinsics + growth data\n")

# ---------------------------------------------------------------------------
# Feature engineering (intrinsics only -- known at release)
# ---------------------------------------------------------------------------

for col in ["parts_count", "minifig_count", "weight", "rrp_usd_cents",
            "rrp_gbp_cents", "rrp_eur_cents", "be_review_count",
            "theme_rank", "subtheme_avg_growth_pct", "be_pieces",
            "be_minifigs", "rating_value"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Use BE pieces if lego_items parts_count is missing
df["parts"] = df["parts_count"].fillna(df["be_pieces"])
df["mfigs"] = df["minifig_count"].fillna(df["be_minifigs"])

# Basic derived
rrp = df["rrp_usd_cents"].fillna(0)
parts = df["parts"].fillna(0)

df["rrp_usd"] = rrp / 100.0
df["log_rrp"] = np.log1p(rrp)
df["log_parts"] = np.log1p(parts)
df["price_per_part"] = np.where(parts > 0, rrp / parts, np.nan)
df["has_minifigs"] = (df["mfigs"].fillna(0) > 0).astype(int)
df["minifig_density"] = np.where(parts > 0, df["mfigs"].fillna(0) / parts * 100, np.nan)

# Weight-based features
weight = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
df["weight_per_part"] = np.where(parts > 0, weight / parts, np.nan)
df["price_per_gram"] = np.where(weight > 0, rrp / weight, np.nan)

# Price tiers
df["price_tier"] = pd.cut(
    df["rrp_usd"].fillna(0),
    bins=[0, 15, 30, 50, 80, 120, 200, 500, float("inf")],
    labels=[1, 2, 3, 4, 5, 6, 7, 8],
).astype(float)

df["parts_bucket"] = pd.cut(
    parts,
    bins=[0, 50, 150, 300, 500, 800, 1200, 2000, float("inf")],
    labels=[1, 2, 3, 4, 5, 6, 7, 8],
).astype(float)

# Licensed IP
LICENSED_THEMES = {
    "Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
    "Avatar", "The LEGO Movie 2", "Lightyear", "Spider-Man",
    "Disney", "Minecraft", "Sonic the Hedgehog", "BrickHeadz",
    "Overwatch", "Stranger Things", "Trolls World Tour",
}
df["is_licensed"] = df["theme"].isin(LICENSED_THEMES).astype(int)

# Theme encoding (leave-one-out to avoid target leakage)
# For each set, theme_avg_growth = mean growth of OTHER sets in same theme
def loo_theme_mean(dataframe: pd.DataFrame) -> pd.Series:
    theme_sum = dataframe.groupby("theme")["annual_growth_pct"].transform("sum")
    theme_count = dataframe.groupby("theme")["annual_growth_pct"].transform("count")
    own_val = dataframe["annual_growth_pct"]
    return (theme_sum - own_val) / (theme_count - 1)

df["theme_loo_growth"] = loo_theme_mean(df)
# Fill NaN for themes with only 1 set
df["theme_loo_growth"] = df["theme_loo_growth"].fillna(df["annual_growth_pct"].mean())

# Theme size (number of sets in theme)
theme_counts = df["theme"].value_counts()
df["theme_size"] = df["theme"].map(theme_counts)

# Exclusive minifigs flag
df["has_exclusive_mfigs"] = df["exclusive_minifigs"].notna().astype(int)

# Year released
df["year_released"] = pd.to_numeric(df["year_released"], errors="coerce")

# RRP regional ratios (pricing strategy signal)
_gbp = pd.to_numeric(df["rrp_gbp_cents"], errors="coerce").fillna(0)
_eur = pd.to_numeric(df["rrp_eur_cents"], errors="coerce").fillna(0)
df["usd_gbp_ratio"] = np.where(_gbp > 0, rrp / _gbp, np.nan)
df["usd_eur_ratio"] = np.where(_eur > 0, rrp / _eur, np.nan)

# ---------------------------------------------------------------------------
# Feature list
# ---------------------------------------------------------------------------

FEATURES = [
    # Size/complexity
    "log_parts", "log_rrp", "price_per_part", "parts_bucket", "price_tier",
    "mfigs", "has_minifigs", "minifig_density",
    # Weight
    "weight_per_part", "price_per_gram",
    # Quality/reviews
    "rating_value", "be_review_count",
    # Theme
    "theme_loo_growth", "theme_size", "is_licensed",
    # Exclusivity
    "has_exclusive_mfigs",
    # Pricing strategy
    "usd_gbp_ratio", "usd_eur_ratio",
    # Subtheme
    "subtheme_avg_growth_pct",
]

valid = []
for f in FEATURES:
    if f not in df.columns:
        continue
    s = pd.to_numeric(df[f], errors="coerce")
    cov = s.notna().sum() / len(df) * 100
    if cov >= 40:
        valid.append(f)

print(f"Features: {len(valid)} (intrinsics only, zero leakage)")
for f in valid:
    cov = pd.to_numeric(df[f], errors="coerce").notna().sum() / len(df) * 100
    print(f"  {f:<25s} {cov:5.1f}%")

# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------

y_reg = df["annual_growth_pct"].values.astype(float)

# Try multiple classification thresholds
for threshold in [8.0, 10.0, 12.0, 15.0]:
    pos = (y_reg >= threshold).sum()
    print(f"\n  Threshold {threshold}%: {pos} positive ({pos/len(df)*100:.0f}%)")

THRESHOLD = 10.0
y_cls = (y_reg >= THRESHOLD).astype(int)

print(f"\nUsing threshold: {THRESHOLD}%")
print(f"  Positive: {y_cls.sum()} ({y_cls.mean()*100:.0f}%), Negative: {(1-y_cls).sum()}")

# Prepare X
X = df[valid].copy()
for c in X.columns:
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())

scaler = StandardScaler()
Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRELATION WITH ANNUAL GROWTH")
print("=" * 70)

corrs = {}
for f in valid:
    s = pd.to_numeric(df[f], errors="coerce")
    mask = s.notna()
    if mask.sum() >= 20:
        corrs[f] = s[mask].corr(pd.Series(y_reg)[mask])

for f, c in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True):
    marker = " ***" if abs(c) > 0.3 else " **" if abs(c) > 0.2 else ""
    print(f"  {f:<25s} {c:>+.3f}{marker}")

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CLASSIFICATION")
print("=" * 70)

cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
baseline = max(y_cls.mean(), 1 - y_cls.mean())
print(f"\nBaseline: {baseline:.3f}  (n={len(df)})")

models_cls = {
    "Logistic": LogisticRegression(max_iter=1000, C=0.5, random_state=42),
    "RF": RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=5, random_state=42),
    "GBM": GradientBoostingClassifier(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42),
}

best_auc = 0
best_name = ""
for name, model in models_cls.items():
    acc = cross_val_score(model, Xs, y_cls, cv=cv, scoring="accuracy")
    auc = cross_val_score(model, Xs, y_cls, cv=cv, scoring="roc_auc")
    print(f"  {name:12s}  Acc={acc.mean():.3f}+/-{acc.std():.3f}  AUC={auc.mean():.3f}+/-{auc.std():.3f}")
    if auc.mean() > best_auc:
        best_auc = auc.mean()
        best_name = name

print(f"\n  Best: {best_name} (AUC={best_auc:.3f})")

# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("REGRESSION")
print("=" * 70)

rcv = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)

models_reg = {
    "Ridge": Ridge(alpha=10.0),
    "Lasso": Lasso(alpha=0.5, max_iter=5000),
    "RF": RandomForestRegressor(n_estimators=200, max_depth=5, min_samples_leaf=5, random_state=42),
    "GBM": GradientBoostingRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42),
}

for name, model in models_reg.items():
    r2 = cross_val_score(model, Xs, y_reg, cv=rcv, scoring="r2")
    mae = cross_val_score(model, Xs, y_reg, cv=rcv, scoring="neg_mean_absolute_error")
    print(f"  {name:12s}  R2={r2.mean():.3f}+/-{r2.std():.3f}  MAE={-mae.mean():.2f}%+/-{mae.std():.2f}%")

# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE")
print("=" * 70)

gb = GradientBoostingRegressor(n_estimators=100, max_depth=3, min_samples_leaf=5, learning_rate=0.05, random_state=42)
gb.fit(Xs, y_reg)

perm = permutation_importance(gb, Xs, y_reg, n_repeats=30, random_state=42, scoring="r2")
sorted_imp = sorted(zip(valid, perm.importances_mean, gb.feature_importances_),
                     key=lambda x: x[1], reverse=True)

print(f"\n{'Feature':<25s} {'Perm':>8s} {'Tree':>8s}")
print("-" * 43)
for f, p, t in sorted_imp:
    bar = "#" * max(0, int(p * 30))
    print(f"  {f:<23s} {p:>+6.3f}  {t:>6.3f}  {bar}")

# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ERROR ANALYSIS")
print("=" * 70)

loo = LeaveOneOut()
y_pred = cross_val_predict(gb, Xs, y_reg, cv=loo)
errors = y_reg - y_pred

print(f"\nLOO Regression (GBM):")
print(f"  R2:          {r2_score(y_reg, y_pred):.3f}")
print(f"  MAE:         {mean_absolute_error(y_reg, y_pred):.2f}%")
print(f"  Correlation: {np.corrcoef(y_reg, y_pred)[0,1]:.3f}")
print(f"  Mean error:  {errors.mean():.2f}%")
print(f"  Median AE:   {np.median(np.abs(errors)):.2f}%")

# By theme
print(f"\nPer-theme performance:")
df["pred"] = y_pred
df["error"] = errors
theme_perf = (
    df.groupby("theme")
    .agg(
        n=("error", "count"),
        mae=("error", lambda x: np.abs(x).mean()),
        corr=("annual_growth_pct", lambda x: x.corr(df.loc[x.index, "pred"]) if len(x) > 2 else np.nan),
        avg_growth=("annual_growth_pct", "mean"),
    )
    .sort_values("n", ascending=False)
)
for theme, row in theme_perf.head(15).iterrows():
    print(f"  {str(theme)[:22]:22s}  n={row['n']:3.0f}  MAE={row['mae']:.1f}%  corr={row['corr']:.2f}  avg={row['avg_growth']:.1f}%")

# Biggest misses
print(f"\nBiggest underpredictions (model too conservative):")
df_sorted = df.nlargest(10, "error")
for _, row in df_sorted.iterrows():
    print(f"  {row['set_number']:>7s} {str(row['title'])[:30]:30s} actual={row['annual_growth_pct']:.1f}% pred={row['pred']:.1f}% err={row['error']:+.1f}%")

print(f"\nBiggest overpredictions:")
df_sorted = df.nsmallest(10, "error")
for _, row in df_sorted.iterrows():
    print(f"  {row['set_number']:>7s} {str(row['title'])[:30]:30s} actual={row['annual_growth_pct']:.1f}% pred={row['pred']:.1f}% err={row['error']:+.1f}%")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Intrinsics-only model on {len(df)} sets (no price data, zero leakage):
- Features: {len(valid)} set characteristics (parts, price, theme, etc.)
- Target: BE annual_growth_pct
- Best classification AUC: {best_auc:.3f} ({best_name})
- This tells us how much signal is in set DNA alone.
""")
