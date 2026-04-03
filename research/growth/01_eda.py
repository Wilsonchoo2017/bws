"""
01 - Exploratory Data Analysis: LEGO Set Investment Returns
============================================================
Starting with 38 sets that have complete data across all three sources:
BrickEconomy (growth/value), BrickLink (price history), and Keepa (Amazon).

Goal: Understand the data, find patterns, identify predictive features.

Findings are documented inline. Run with: python research/01_eda.py
"""

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

df = db.execute("""
    SELECT
        -- Item basics
        li.set_number,
        li.title,
        li.theme,
        li.year_released,
        li.year_retired,
        li.parts_count,
        li.minifig_count,
        li.retiring_soon,
        li.weight,

        -- BrickEconomy: growth & valuation
        be.annual_growth_pct,
        be.rolling_growth_pct,
        be.growth_90d_pct,
        be.total_growth_pct,
        be.value_new_cents,
        be.value_used_cents,
        be.rrp_usd_cents,
        be.distribution_mean_cents,
        be.distribution_stddev_cents,
        be.rating_value,
        be.review_count        AS be_review_count,
        be.exclusive_minifigs,
        be.subtheme_avg_growth_pct,
        be.theme_rank,
        be.candlestick_json,

        -- BrickLink: price history
        bp.six_month_new,
        bp.six_month_used,
        bp.current_new,
        bp.current_used,

        -- Keepa: Amazon data
        ks.current_new_cents   AS keepa_price_cents,
        ks.lowest_ever_cents   AS keepa_lowest_cents,
        ks.highest_ever_cents  AS keepa_highest_cents,
        ks.rating              AS keepa_rating,
        ks.review_count        AS keepa_review_count,
        ks.tracking_users      AS keepa_tracking_users,
        ks.current_buy_box_cents AS keepa_buy_box_cents,
        ks.current_amazon_cents AS keepa_amazon_cents

    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    JOIN bricklink_price_history bp ON (li.set_number || '-1') = bp.item_id
    JOIN keepa_snapshots ks ON li.set_number = ks.set_number
    WHERE be.annual_growth_pct IS NOT NULL
      AND be.value_new_cents IS NOT NULL
""").fetchdf()

db.close()

print(f"Loaded {len(df)} sets with complete data across all 3 sources\n")

# ---------------------------------------------------------------------------
# 2. Basic stats
# ---------------------------------------------------------------------------

print("=" * 70)
print("BASIC STATISTICS")
print("=" * 70)

print(f"\nSets: {len(df)}")
print(f"Themes: {df['theme'].nunique()} unique")
print(f"Year range: {df['year_released'].min()} - {df['year_released'].max()}")
print(f"Parts range: {df['parts_count'].min()} - {df['parts_count'].max()}")

print("\n--- Annual Growth Distribution ---")
growth = df["annual_growth_pct"]
print(f"  Mean:   {growth.mean():.1f}%")
print(f"  Median: {growth.median():.1f}%")
print(f"  Std:    {growth.std():.1f}%")
print(f"  Min:    {growth.min():.1f}%")
print(f"  Max:    {growth.max():.1f}%")
print(f"  >10%:   {(growth > 10).sum()} sets ({(growth > 10).mean()*100:.0f}%)")
print(f"  >15%:   {(growth > 15).sum()} sets ({(growth > 15).mean()*100:.0f}%)")
print(f"  >20%:   {(growth > 20).sum()} sets ({(growth > 20).mean()*100:.0f}%)")

# ---------------------------------------------------------------------------
# 3. Derived features
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE ENGINEERING")
print("=" * 70)

# Price-based features
df["rrp_usd"] = df["rrp_usd_cents"] / 100.0
df["value_new_usd"] = df["value_new_cents"] / 100.0
df["roi_pct"] = np.where(
    df["rrp_usd_cents"] > 0,
    (df["value_new_cents"] - df["rrp_usd_cents"]) / df["rrp_usd_cents"] * 100,
    np.nan,
)
df["price_per_part"] = np.where(
    df["parts_count"] > 0,
    df["rrp_usd_cents"] / df["parts_count"],
    np.nan,
)

# Value distribution features
df["dist_cv"] = np.where(
    df["distribution_mean_cents"] > 0,
    df["distribution_stddev_cents"] / df["distribution_mean_cents"],
    np.nan,
)

# Keepa features
_keepa_price = pd.to_numeric(df["keepa_price_cents"], errors="coerce")
_rrp = pd.to_numeric(df["rrp_usd_cents"], errors="coerce")
df["keepa_discount_pct"] = np.where(
    (_rrp > 0) & (_keepa_price.notna()),
    (_rrp - _keepa_price) / _rrp * 100,
    np.nan,
)
_keepa_lo = pd.to_numeric(df["keepa_lowest_cents"], errors="coerce").fillna(0)
_keepa_hi = pd.to_numeric(df["keepa_highest_cents"], errors="coerce").fillna(0)
df["keepa_price_range_pct"] = np.where(
    _keepa_lo > 0,
    (_keepa_hi - _keepa_lo) / _keepa_lo * 100,
    np.nan,
)

# BrickLink features - extract from JSON
def extract_bl_avg_price(json_col: pd.Series) -> pd.Series:
    """Extract average price from BrickLink JSON price data."""
    def _extract(val):
        if val is None:
            return np.nan
        try:
            data = val if isinstance(val, dict) else json.loads(val)
            avg = data.get("avg_price", {})
            if isinstance(avg, dict):
                return float(avg.get("amount", 0))
            return float(avg) if avg else np.nan
        except (json.JSONDecodeError, TypeError, ValueError):
            return np.nan
    return json_col.apply(_extract)

def extract_bl_qty(json_col: pd.Series) -> pd.Series:
    """Extract total quantity from BrickLink JSON price data."""
    def _extract(val):
        if val is None:
            return np.nan
        try:
            data = val if isinstance(val, dict) else json.loads(val)
            return float(data.get("total_qty", 0) or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            return np.nan
    return json_col.apply(_extract)

df["bl_6m_new_avg"] = extract_bl_avg_price(df["six_month_new"])
df["bl_6m_new_qty"] = extract_bl_qty(df["six_month_new"])
df["bl_current_new_qty"] = extract_bl_qty(df["current_new"])
df["bl_6m_used_qty"] = extract_bl_qty(df["six_month_used"])

# Supply/demand ratio
df["bl_supply_demand"] = np.where(
    df["bl_6m_new_qty"] > 0,
    df["bl_current_new_qty"] / df["bl_6m_new_qty"],
    np.nan,
)

# ---------------------------------------------------------------------------
# 4. Classification target: "good investment" = annual growth > 10%
# ---------------------------------------------------------------------------

GROWTH_THRESHOLD = 10.0
df["good_investment"] = (df["annual_growth_pct"] >= GROWTH_THRESHOLD).astype(int)

print(f"\nTarget: annual_growth >= {GROWTH_THRESHOLD}%")
print(f"  Good investments: {df['good_investment'].sum()} ({df['good_investment'].mean()*100:.0f}%)")
print(f"  Below threshold:  {(1 - df['good_investment']).sum()} ({(1 - df['good_investment']).mean()*100:.0f}%)")

# ---------------------------------------------------------------------------
# 5. Correlation analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRELATION WITH ANNUAL GROWTH")
print("=" * 70)

numeric_features = [
    "parts_count", "minifig_count", "rrp_usd", "price_per_part",
    "dist_cv", "rating_value", "be_review_count",
    "keepa_discount_pct", "keepa_price_range_pct",
    "keepa_rating", "keepa_review_count", "keepa_tracking_users",
    "bl_6m_new_qty", "bl_current_new_qty", "bl_6m_used_qty",
    "bl_supply_demand",
]

# Filter to features that exist and have variance
valid_features = []
for f in numeric_features:
    if f in df.columns:
        series = pd.to_numeric(df[f], errors="coerce")
        if series.notna().sum() >= 5 and series.std() > 0:
            valid_features.append(f)

correlations = {}
for f in valid_features:
    series = pd.to_numeric(df[f], errors="coerce")
    mask = series.notna() & df["annual_growth_pct"].notna()
    if mask.sum() >= 5:
        corr = series[mask].corr(df["annual_growth_pct"][mask])
        correlations[f] = corr

sorted_corrs = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
print(f"\n{'Feature':<30s} {'Correlation':>12s}")
print("-" * 44)
for feat, corr in sorted_corrs:
    marker = " ***" if abs(corr) > 0.3 else " **" if abs(corr) > 0.2 else ""
    print(f"  {feat:<28s} {corr:>+.3f}{marker}")

# ---------------------------------------------------------------------------
# 6. Theme analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("THEME ANALYSIS")
print("=" * 70)

theme_stats = (
    df.groupby("theme")
    .agg(
        count=("set_number", "count"),
        avg_growth=("annual_growth_pct", "mean"),
        median_growth=("annual_growth_pct", "median"),
        avg_parts=("parts_count", "mean"),
        good_pct=("good_investment", "mean"),
    )
    .sort_values("avg_growth", ascending=False)
)

print(f"\n{'Theme':<25s} {'N':>3s} {'Avg%':>6s} {'Med%':>6s} {'Good%':>6s}")
print("-" * 50)
for theme, row in theme_stats.iterrows():
    print(
        f"  {str(theme)[:23]:<23s} {row['count']:3.0f} "
        f"{row['avg_growth']:5.1f}% {row['median_growth']:5.1f}% "
        f"{row['good_pct']*100:5.0f}%"
    )

# ---------------------------------------------------------------------------
# 7. Price tier analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PRICE TIER ANALYSIS")
print("=" * 70)

bins = [0, 20, 50, 100, 200, 500, float("inf")]
labels = ["<$20", "$20-50", "$50-100", "$100-200", "$200-500", "$500+"]
df["price_tier"] = pd.cut(df["rrp_usd"], bins=bins, labels=labels)

tier_stats = (
    df.groupby("price_tier", observed=True)
    .agg(
        count=("set_number", "count"),
        avg_growth=("annual_growth_pct", "mean"),
        median_growth=("annual_growth_pct", "median"),
        good_pct=("good_investment", "mean"),
    )
)

print(f"\n{'Price Tier':<15s} {'N':>3s} {'Avg%':>6s} {'Med%':>6s} {'Good%':>6s}")
print("-" * 38)
for tier, row in tier_stats.iterrows():
    print(
        f"  {str(tier):<13s} {row['count']:3.0f} "
        f"{row['avg_growth']:5.1f}% {row['median_growth']:5.1f}% "
        f"{row['good_pct']*100:5.0f}%"
    )

# ---------------------------------------------------------------------------
# 8. Quick model test (if we have enough data)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("QUICK MODEL TEST")
print("=" * 70)

try:
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    from sklearn.model_selection import LeaveOneOut, cross_val_score
    from sklearn.preprocessing import StandardScaler

    # Use features with decent coverage
    model_features = [f for f in valid_features if df[f].notna().sum() >= len(df) * 0.7]
    print(f"\nUsing {len(model_features)} features with >=70% coverage:")
    for f in model_features:
        coverage = df[f].notna().sum() / len(df) * 100
        print(f"  {f:<28s} coverage={coverage:.0f}%")

    # Prepare data
    X = df[model_features].copy()
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    X = X.fillna(X.median())

    y_reg = df["annual_growth_pct"].values
    y_cls = df["good_investment"].values

    # Leave-one-out CV (small dataset)
    loo = LeaveOneOut()

    # Regression: predict growth rate
    reg = GradientBoostingRegressor(
        n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
    )
    reg_scores = cross_val_score(reg, X, y_reg, cv=loo, scoring="r2")
    print(f"\nRegression (LOO CV):")
    print(f"  R2 mean: {reg_scores.mean():.3f}")
    print(f"  R2 std:  {reg_scores.std():.3f}")

    # Classification: predict good investment
    cls = GradientBoostingClassifier(
        n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
    )
    cls_scores = cross_val_score(cls, X, y_cls, cv=loo, scoring="accuracy")
    print(f"\nClassification (LOO CV):")
    print(f"  Accuracy: {cls_scores.mean():.3f}")
    print(f"  Baseline: {max(y_cls.mean(), 1 - y_cls.mean()):.3f} (majority class)")

    # Feature importance from full model
    reg.fit(X, y_reg)
    importances = sorted(
        zip(model_features, reg.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print(f"\nFeature importance (regression):")
    for feat, imp in importances:
        bar = "#" * int(imp * 50)
        print(f"  {feat:<28s} {imp:.3f} {bar}")

except ImportError:
    print("\nscikit-learn not installed. Run: pip install scikit-learn")
    print("Skipping model test.")

# ---------------------------------------------------------------------------
# 9. Summary of findings
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY OF FINDINGS")
print("=" * 70)
print("""
Dataset: {n} sets with complete data (BrickEconomy + BrickLink + Keepa)

Key observations to investigate further:
1. Growth distribution and what separates winners from losers
2. Which features correlate most strongly with growth
3. Whether theme/price tier alone are predictive
4. Model performance with limited data (LOO CV)

Next steps:
- Expand to 204 sets (BE + BL only, skip Keepa requirement)
- Engineer more features from candlestick/price history JSON
- Try different model architectures
- Cross-validate with time-based splits
""".format(n=len(df)))
