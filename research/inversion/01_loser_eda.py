"""
01 - Munger Inversion EDA: Understanding the Losers
====================================================
"All I want to know is where I'm going to die, so I'll never go there."
-- Charlie Munger

Goal: Understand the LEFT TAIL of LEGO set growth.
- What % of sets have low growth (the "avoid" zone)?
- What distinguishes low-growth from high-growth sets?
- Which themes/subthemes are overrepresented in the bottom quintile?
- What features correlate with low growth?

Uses BrickEconomy annual_growth_pct as target (same as production growth model,
345 sets available). NOT the BrickLink retirement-return pipeline (only 5 sets).

Run with: python research/inversion/01_loser_eda.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.ml import InversionConfig

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "inversion"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

inversion_config = InversionConfig()

print("=" * 70)
print("MUNGER INVERSION EDA: Understanding the Losers")
print("=" * 70)

# ---------------------------------------------------------------------------
# 1. Load all sets with BE annual_growth_pct
# ---------------------------------------------------------------------------

df = db.execute("""
    SELECT
        li.set_number,
        li.title,
        li.theme,
        li.year_released,
        li.year_retired,
        li.parts_count,
        li.minifig_count,
        li.retiring_soon,
        be.annual_growth_pct,
        be.rolling_growth_pct,
        be.growth_90d_pct,
        be.total_growth_pct,
        be.value_new_cents,
        be.rrp_usd_cents,
        be.rating_value,
        be.review_count,
        be.subtheme,
        be.subtheme_avg_growth_pct,
        be.theme_rank
    FROM lego_items li
    JOIN (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
        FROM brickeconomy_snapshots
        WHERE annual_growth_pct IS NOT NULL
    ) be ON be.set_number = li.set_number AND be.rn = 1
    ORDER BY be.annual_growth_pct ASC
""").df()

print(f"\nTotal sets with annual_growth_pct: {len(df)}")

# Derived features
parts = pd.to_numeric(df["parts_count"], errors="coerce").fillna(0)
rrp = pd.to_numeric(df["rrp_usd_cents"], errors="coerce").fillna(0)
val_new = pd.to_numeric(df["value_new_cents"], errors="coerce").fillna(0)
mfigs = pd.to_numeric(df["minifig_count"], errors="coerce").fillna(0)

df["price_per_part"] = np.where(parts > 0, rrp / parts, np.nan)
df["minifig_density"] = np.where(parts > 0, mfigs / parts * 100, 0)
df["value_vs_rrp"] = np.where(rrp > 0, val_new / rrp, np.nan)

# ---------------------------------------------------------------------------
# 2. Growth distribution analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ANNUAL GROWTH DISTRIBUTION")
print("=" * 70)

growth = df["annual_growth_pct"]
print(f"  Count:  {len(growth)}")
print(f"  Mean:   {growth.mean():.1f}%")
print(f"  Median: {growth.median():.1f}%")
print(f"  Std:    {growth.std():.1f}%")
print(f"  Min:    {growth.min():.1f}%")
print(f"  Max:    {growth.max():.1f}%")

for p in [5, 10, 25, 75, 90, 95]:
    print(f"  P{p:<3}:   {growth.quantile(p / 100):.1f}%")

# Inversion thresholds (adapted for growth % instead of return)
# Since BE growth is always positive (min ~1%), adjust thresholds
avoid_threshold = 5.0  # below 5% annual growth = avoid
low_growth = 8.0  # below median-ish

print(f"\n  Below {avoid_threshold}%:  {(growth < avoid_threshold).sum()} ({(growth < avoid_threshold).mean():.1%})")
print(f"  Below {low_growth}%:  {(growth < low_growth).sum()} ({(growth < low_growth).mean():.1%})")

# Quintile analysis
df["quintile"] = pd.qcut(growth, 5, labels=["Q1_worst", "Q2", "Q3", "Q4", "Q5_best"])
print("\n  Quintile breakdown:")
for q in ["Q1_worst", "Q2", "Q3", "Q4", "Q5_best"]:
    subset = df[df["quintile"] == q]["annual_growth_pct"]
    print(f"    {q:<10}: n={len(subset):>3}, range=[{subset.min():.1f}%, {subset.max():.1f}%], mean={subset.mean():.1f}%")

# ---------------------------------------------------------------------------
# 3. Theme breakdown
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("THEME BREAKDOWN: Bottom Quintile Concentration")
print("=" * 70)

df["is_bottom_q"] = df["quintile"] == "Q1_worst"
df["is_avoid"] = growth < avoid_threshold

theme_stats = (
    df.groupby("theme")
    .agg(
        count=("annual_growth_pct", "size"),
        mean_growth=("annual_growth_pct", "mean"),
        median_growth=("annual_growth_pct", "median"),
        pct_bottom_q=("is_bottom_q", "mean"),
        pct_avoid=("is_avoid", "mean"),
    )
    .sort_values("pct_avoid", ascending=False)
)

print(f"\n{'Theme':<25} {'N':>4} {'Mean%':>7} {'Med%':>7} {'%BotQ':>7} {'%Avoid':>7}")
print("-" * 60)
for theme, row in theme_stats.iterrows():
    if row["count"] >= 5:
        print(
            f"{str(theme)[:24]:<25} {int(row['count']):>4} "
            f"{row['mean_growth']:>6.1f} {row['median_growth']:>6.1f} "
            f"{row['pct_bottom_q']:>6.1%} {row['pct_avoid']:>6.1%}"
        )

# ---------------------------------------------------------------------------
# 4. Subtheme breakdown (more granular)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUBTHEME BREAKDOWN: Worst Subthemes (avg growth)")
print("=" * 70)

subtheme_stats = (
    df.groupby(["theme", "subtheme"])
    .agg(
        count=("annual_growth_pct", "size"),
        mean_growth=("annual_growth_pct", "mean"),
        pct_avoid=("is_avoid", "mean"),
    )
    .sort_values("mean_growth")
)

print(f"\n{'Theme':<20} {'Subtheme':<25} {'N':>4} {'Mean%':>7} {'%Avoid':>7}")
print("-" * 68)
for (theme, subtheme), row in subtheme_stats.head(20).iterrows():
    if row["count"] >= 2:
        print(
            f"{str(theme)[:19]:<20} {str(subtheme)[:24]:<25} "
            f"{int(row['count']):>4} {row['mean_growth']:>6.1f} {row['pct_avoid']:>6.1%}"
        )

# ---------------------------------------------------------------------------
# 5. Feature correlations with growth
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE CORRELATIONS WITH annual_growth_pct")
print("=" * 70)

numeric_features = [
    "parts_count", "minifig_count", "rrp_usd_cents", "price_per_part",
    "minifig_density", "value_vs_rrp", "rating_value", "review_count",
    "rolling_growth_pct", "growth_90d_pct", "subtheme_avg_growth_pct",
    "theme_rank",
]

print(f"\n{'Feature':<30} {'Corr':>8} {'Corr(BotQ)':>12}")
print("-" * 55)
for feat in numeric_features:
    if feat not in df.columns:
        continue
    valid = df[[feat, "annual_growth_pct", "is_bottom_q"]].dropna()
    if len(valid) < 20:
        continue
    corr_growth = valid[feat].corr(valid["annual_growth_pct"])
    corr_bottom = valid[feat].corr(valid["is_bottom_q"].astype(float))
    print(f"  {feat:<28} {corr_growth:>7.3f} {corr_bottom:>11.3f}")

# ---------------------------------------------------------------------------
# 6. Bottom quintile vs top quintile comparison
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("BOTTOM QUINTILE vs TOP QUINTILE: Feature Comparison")
print("=" * 70)

bottom_q = df[df["quintile"] == "Q1_worst"]
top_q = df[df["quintile"] == "Q5_best"]

compare_features = [
    "parts_count", "minifig_count", "rrp_usd_cents", "price_per_part",
    "minifig_density", "rating_value", "review_count",
]

# Ensure numeric types for comparison
for col in compare_features:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

bottom_q = df[df["quintile"] == "Q1_worst"]
top_q = df[df["quintile"] == "Q5_best"]

print(f"\n{'Feature':<25} {'Bot Q1 Mean':>12} {'Top Q5 Mean':>12} {'Ratio':>8}")
print("-" * 62)
for feat in compare_features:
    if feat not in df.columns:
        continue
    bot_mean = bottom_q[feat].mean()
    top_mean = top_q[feat].mean()
    ratio = bot_mean / top_mean if top_mean != 0 else 0
    print(f"  {feat:<23} {bot_mean:>11.1f} {top_mean:>11.1f} {ratio:>7.2f}x")

# ---------------------------------------------------------------------------
# 7. Worst performers (case studies)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("WORST 15 SETS (lowest annual_growth_pct)")
print("=" * 70)

bottom = df.head(15)
print(f"\n{'Set':<10} {'Title':<30} {'Theme':<18} {'Growth':>7}")
print("-" * 70)
for _, row in bottom.iterrows():
    title = str(row.get("title", ""))[:29]
    theme = str(row.get("theme", ""))[:17]
    print(f"{row['set_number']:<10} {title:<30} {theme:<18} {row['annual_growth_pct']:>6.1f}%")

# ---------------------------------------------------------------------------
# 8. Best performers (contrast)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("BEST 15 SETS (highest annual_growth_pct)")
print("=" * 70)

top = df.tail(15).iloc[::-1]
print(f"\n{'Set':<10} {'Title':<30} {'Theme':<18} {'Growth':>7}")
print("-" * 70)
for _, row in top.iterrows():
    title = str(row.get("title", ""))[:29]
    theme = str(row.get("theme", ""))[:17]
    print(f"{row['set_number']:<10} {title:<30} {theme:<18} {row['annual_growth_pct']:>6.1f}%")

# ---------------------------------------------------------------------------
# 9. Save results
# ---------------------------------------------------------------------------

output_path = RESULTS_DIR / "01_eda_full.csv"
df.to_csv(output_path, index=False)
print(f"\nFull dataset saved to: {output_path}")

theme_stats.to_csv(RESULTS_DIR / "01_eda_theme_stats.csv")
print(f"Theme stats saved to: {RESULTS_DIR / '01_eda_theme_stats.csv'}")

subtheme_stats.to_csv(RESULTS_DIR / "01_eda_subtheme_stats.csv")
print(f"Subtheme stats saved to: {RESULTS_DIR / '01_eda_subtheme_stats.csv'}")

db.close()
print("\nDone.")
