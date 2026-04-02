"""
09 - Enriched Intrinsics: Theme-relative + Cohort Ranking + Interactions
=========================================================================
New features buildable from existing data:
1. Price/parts z-score within theme (relative positioning)
2. Cohort ranking within release year (relative traction)
3. Interaction features (licensed x price, etc.)
4. Collector-target proxy (display vs play sets)

Run with: .venv/bin/python research/09_enriched_intrinsics.py
"""

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
        li.year_released, li.parts_count, li.minifig_count, li.weight,
        be.annual_growth_pct, be.rrp_usd_cents,
        be.rating_value, be.review_count AS be_reviews,
        be.exclusive_minifigs, be.subtheme_avg_growth_pct,
        be.pieces, be.minifigs AS be_mfigs,
        be.rrp_gbp_cents, be.subtheme
    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    WHERE be.annual_growth_pct IS NOT NULL
      AND be.rrp_usd_cents > 0
""").fetchdf()

db.close()

print(f"Loaded {len(df)} sets\n")

# Numeric coercion
for col in ["parts_count", "minifig_count", "weight", "rrp_usd_cents",
            "rrp_gbp_cents", "be_reviews", "subtheme_avg_growth_pct",
            "pieces", "be_mfigs", "rating_value", "year_released"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["parts"] = df["parts_count"].fillna(df["pieces"])
df["mfigs"] = df["minifig_count"].fillna(df["be_mfigs"])
rrp = df["rrp_usd_cents"].fillna(0)
parts = df["parts"].fillna(0)

# =========================================================================
# BASELINE INTRINSICS (same as exp 05/08)
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
    "usd_gbp_ratio", "subtheme_avg_growth_pct",
]

# =========================================================================
# NEW FEATURE 1: Theme-relative positioning
# =========================================================================

# Z-score of price within theme
theme_rrp_mean = df.groupby("theme")["rrp_usd_cents"].transform("mean")
theme_rrp_std = df.groupby("theme")["rrp_usd_cents"].transform("std").replace(0, np.nan)
df["price_zscore_theme"] = (rrp - theme_rrp_mean) / theme_rrp_std

# Z-score of parts within theme
theme_parts_mean = df.groupby("theme")["parts"].transform("mean")
theme_parts_std = df.groupby("theme")["parts"].transform("std").replace(0, np.nan)
df["parts_zscore_theme"] = (parts - theme_parts_mean) / theme_parts_std

# Price percentile within theme (0-1)
df["price_pctile_theme"] = df.groupby("theme")["rrp_usd_cents"].rank(pct=True)

# Parts percentile within theme
df["parts_pctile_theme"] = df.groupby("theme")["parts"].rank(pct=True)

# Minifig density relative to theme
theme_mfd_mean = df.groupby("theme")["minifig_density"].transform("mean")
df["mfd_vs_theme"] = df["minifig_density"] - theme_mfd_mean

# Price-per-part relative to theme average
theme_ppp_mean = df.groupby("theme")["price_per_part"].transform("mean")
df["ppp_vs_theme"] = np.where(
    theme_ppp_mean > 0,
    (df["price_per_part"] - theme_ppp_mean) / theme_ppp_mean * 100,
    np.nan,
)

THEME_RELATIVE = [
    "price_zscore_theme", "parts_zscore_theme",
    "price_pctile_theme", "parts_pctile_theme",
    "mfd_vs_theme", "ppp_vs_theme",
]

# =========================================================================
# NEW FEATURE 2: Cohort ranking (within release year)
# =========================================================================

# Rank by rating within release year cohort
df["rating_rank_cohort"] = df.groupby("year_released")["rating_value"].rank(
    pct=True, ascending=True, na_option="bottom"
)

# Rank by review count within cohort (more reviews = more traction)
df["reviews_rank_cohort"] = df.groupby("year_released")["be_reviews"].rank(
    pct=True, ascending=True, na_option="bottom"
)

# Rank by parts count within cohort (bigger = more noticed?)
df["parts_rank_cohort"] = df.groupby("year_released")["parts"].rank(
    pct=True, ascending=True,
)

# Rank by price within cohort
df["price_rank_cohort"] = df.groupby("year_released")["rrp_usd_cents"].rank(
    pct=True, ascending=True,
)

# Combined "traction score" within cohort: rating_rank * reviews_rank
# (sets that are both highly rated AND highly reviewed stood out)
df["traction_cohort"] = df["rating_rank_cohort"] * df["reviews_rank_cohort"]

# Also rank within theme+year (more granular)
df["rating_rank_theme_year"] = df.groupby(["theme", "year_released"])["rating_value"].rank(
    pct=True, ascending=True, na_option="bottom"
)
df["reviews_rank_theme_year"] = df.groupby(["theme", "year_released"])["be_reviews"].rank(
    pct=True, ascending=True, na_option="bottom"
)

COHORT = [
    "rating_rank_cohort", "reviews_rank_cohort",
    "parts_rank_cohort", "price_rank_cohort",
    "traction_cohort",
    "rating_rank_theme_year", "reviews_rank_theme_year",
]

# =========================================================================
# NEW FEATURE 3: Interaction features
# =========================================================================

# Licensed x price tier (cheap licensed sets might be the sweet spot)
df["licensed_x_price"] = df["is_licensed"] * df["price_tier"]

# Licensed x minifig density
df["licensed_x_mfd"] = df["is_licensed"] * df["minifig_density"].fillna(0)

# Theme size x price (cheap set in big theme vs small theme)
df["theme_size_x_price"] = df["theme_size"] * df["price_tier"]

# Rating x reviews (quality * popularity)
df["rating_x_reviews"] = df["rating_value"].fillna(0) * np.log1p(df["be_reviews"].fillna(0))

INTERACTIONS = [
    "licensed_x_price", "licensed_x_mfd",
    "theme_size_x_price", "rating_x_reviews",
]

# =========================================================================
# NEW FEATURE 4: Set category proxy
# =========================================================================

# "Collector/display" proxy: high price, high parts, LOW minifig density
# vs "play set": moderate price, HIGH minifig density
mfd = df["minifig_density"].fillna(0)
df["collector_score"] = (
    df["price_pctile_theme"] * 0.4 +
    df["parts_pctile_theme"] * 0.3 +
    (1 - mfd / mfd.max()) * 0.3
)

# Value density: price per part relative to overall median
median_ppp = df["price_per_part"].median()
df["value_density"] = np.where(
    median_ppp > 0,
    df["price_per_part"] / median_ppp,
    np.nan,
)

CATEGORY = [
    "collector_score", "value_density",
]

# =========================================================================
# EVALUATE
# =========================================================================

y_reg = df["annual_growth_pct"].values.astype(float)
THRESHOLD = 10.0
y_cls = (y_reg >= THRESHOLD).astype(int)

print(f"Target >= {THRESHOLD}%: {y_cls.sum()} positive ({y_cls.mean()*100:.0f}%)\n")

cv_cls = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
cv_reg = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)


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

    auc = cross_val_score(gb_c, Xs, y_cls, cv=cv_cls, scoring="roc_auc")
    r2 = cross_val_score(gb_r, Xs, y_reg, cv=cv_reg, scoring="r2")

    y_pred = cross_val_predict(gb_r, Xs, y_reg, cv=LeaveOneOut())
    loo_r2 = r2_score(y_reg, y_pred)
    loo_corr = np.corrcoef(y_reg, y_pred)[0, 1]
    loo_mae = mean_absolute_error(y_reg, y_pred)

    print(f"  {label} ({len(valid)} feats):")
    print(f"    CV:  AUC={auc.mean():.3f}+/-{auc.std():.3f}  R2={r2.mean():.3f}")
    print(f"    LOO: R2={loo_r2:.3f}  Corr={loo_corr:.3f}  MAE={loo_mae:.2f}%")

    return loo_r2, loo_corr, auc.mean(), valid


# ---------------------------------------------------------------------------
# Ablation study
# ---------------------------------------------------------------------------

print("=" * 70)
print("ABLATION STUDY")
print("=" * 70)

r2_base, corr_base, auc_base, _ = evaluate(BASELINE, "A: Baseline intrinsics")
evaluate(BASELINE + THEME_RELATIVE, "B: + Theme-relative")
evaluate(BASELINE + COHORT, "C: + Cohort ranking")
evaluate(BASELINE + INTERACTIONS, "D: + Interactions")
evaluate(BASELINE + CATEGORY, "E: + Category proxy")
evaluate(BASELINE + THEME_RELATIVE + COHORT, "F: + Theme-rel + Cohort")

ALL_NEW = BASELINE + THEME_RELATIVE + COHORT + INTERACTIONS + CATEGORY
r2_all, corr_all, auc_all, valid_all = evaluate(ALL_NEW, "G: ALL features")

# Best subset: incrementally add features that help
evaluate(BASELINE + COHORT + THEME_RELATIVE + CATEGORY, "H: Base + Cohort + Theme-rel + Category")

# ---------------------------------------------------------------------------
# Feature importance for best model
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE (all features)")
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

sorted_imp = sorted(
    zip(valid_all, perm.importances_mean),
    key=lambda x: x[1], reverse=True,
)

def feat_group(f):
    if f in THEME_RELATIVE:
        return "THEME-REL"
    if f in COHORT:
        return "COHORT"
    if f in INTERACTIONS:
        return "INTERACT"
    if f in CATEGORY:
        return "CATEGORY"
    return "baseline"

print(f"\n{'Feature':<28s} {'Perm':>8s} {'Group':>10s}")
print("-" * 50)
for f, p in sorted_imp:
    bar = "#" * max(0, int(p * 12))
    print(f"  {f:<26s} {p:>+6.3f}  {feat_group(f):>10s}  {bar}")

# ---------------------------------------------------------------------------
# Correlation check for new features
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("NEW FEATURE CORRELATIONS")
print("=" * 70)

new_feats = THEME_RELATIVE + COHORT + INTERACTIONS + CATEGORY
corrs = {}
for f in new_feats:
    if f not in df.columns:
        continue
    s = pd.to_numeric(df[f], errors="coerce")
    mask = s.notna()
    if mask.sum() >= 20:
        corrs[f] = s[mask].corr(pd.Series(y_reg)[mask])

for f, c in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True):
    g = feat_group(f)
    marker = " ***" if abs(c) > 0.3 else " **" if abs(c) > 0.2 else ""
    print(f"  {f:<28s} r={c:>+.3f}  {g:>10s}{marker}")

# ---------------------------------------------------------------------------
# Error analysis: did we fix the breakout underprediction?
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ERROR ANALYSIS")
print("=" * 70)

y_pred_all = cross_val_predict(gb, Xs, y_reg, cv=LeaveOneOut())
df["pred_new"] = y_pred_all
df["err_new"] = y_reg - y_pred_all

# Compare to baseline predictions
valid_base = [f for f in BASELINE if f in df.columns and df[f].notna().sum() >= len(df) * 0.3]
Xb = df[valid_base].copy()
for c in Xb.columns:
    Xb[c] = pd.to_numeric(Xb[c], errors="coerce")
Xb = Xb.fillna(Xb.median())
Xbs = pd.DataFrame(StandardScaler().fit_transform(Xb), columns=Xb.columns)
gb_base = GradientBoostingRegressor(
    n_estimators=100, max_depth=3, min_samples_leaf=5,
    learning_rate=0.05, random_state=42,
)
y_pred_base = cross_val_predict(gb_base, Xbs, y_reg, cv=LeaveOneOut())
df["pred_base"] = y_pred_base
df["err_base"] = y_reg - y_pred_base

# Top underpredictions: did new features help?
print("\nBreakout sets (top 10 by growth):")
print(f"{'Set':>7s} {'Title':25s} {'Actual':>7s} {'Base':>7s} {'New':>7s} {'Improved?':>10s}")
print("-" * 70)
for _, row in df.nlargest(10, "annual_growth_pct").iterrows():
    improved = "YES" if abs(row["err_new"]) < abs(row["err_base"]) else "no"
    print(f"  {row['set_number']:>7s} {str(row['title'])[:23]:25s} "
          f"{row['annual_growth_pct']:>5.1f}% {row['pred_base']:>5.1f}% {row['pred_new']:>5.1f}% {improved:>10s}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
delta_r2 = r2_all - r2_base
delta_corr = corr_all - corr_base
delta_auc = auc_all - auc_base
print(f"""
Baseline (exp 08): LOO R2={r2_base:.3f}, Corr={corr_base:.3f}, AUC={auc_base:.3f}
All new features:  LOO R2={r2_all:.3f}, Corr={corr_all:.3f}, AUC={auc_all:.3f}
Delta:             R2={delta_r2:+.3f}, Corr={delta_corr:+.3f}, AUC={delta_auc:+.3f}

New feature groups tested:
  - Theme-relative: price/parts z-scores within theme
  - Cohort ranking: rating/review/traction rank within release year
  - Interactions: licensed*price, rating*reviews
  - Category proxy: collector vs play set score
""")
