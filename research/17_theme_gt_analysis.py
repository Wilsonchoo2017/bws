"""
17 - Theme-Level YouTube Google Trends Analysis
================================================
Analyzes the GT data collected by 17_theme_gt_collection.py against
BrickEconomy growth data to test whether theme-level YouTube interest
predicts post-retirement growth.

Key questions:
1. Does lego_share (LEGO fraction of YouTube interest) correlate with growth?
2. Does raw LEGO YouTube interest correlate with growth?
3. Does GT add info beyond what theme_bayes/subtheme_loo already capture?
4. Is the signal different for named IPs vs generic themes?

Run with: python research/17_theme_gt_analysis.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "gt_themes"
DB_PATH = Path.home() / ".bws" / "bws.duckdb"


def weighted_pearsonr(
    x: pd.Series,
    y: pd.Series,
    w: pd.Series,
) -> tuple[float, int]:
    """Weighted Pearson correlation. Returns (r, n)."""
    mask = x.notna() & y.notna() & w.notna()
    x, y, w = x[mask], y[mask], w[mask]
    n = len(x)
    if n < 3:
        return float("nan"), n

    w_sum = w.sum()
    x_mean = (x * w).sum() / w_sum
    y_mean = (y * w).sum() / w_sum
    cov_xy = (w * (x - x_mean) * (y - y_mean)).sum() / w_sum
    var_x = (w * (x - x_mean) ** 2).sum() / w_sum
    var_y = (w * (y - y_mean) ** 2).sum() / w_sum
    denom = np.sqrt(var_x * var_y)

    return round(float(cov_xy / denom), 4) if denom > 0 else float("nan"), n


def safe_pearsonr(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    """Pearson r with p-value and sample size. Handles small/missing data."""
    mask = x.notna() & y.notna()
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan"), n
    r, p = stats.pearsonr(x, y)
    return round(float(r), 4), round(float(p), 4), n


def partial_corr(
    x: pd.Series,
    y: pd.Series,
    z: pd.Series,
) -> tuple[float, int]:
    """Partial Pearson r between x and y, controlling for z. Returns (r, n)."""
    mask = x.notna() & y.notna() & z.notna()
    x, y, z = x[mask].values, y[mask].values, z[mask].values
    n = len(x)
    if n < 5:
        return float("nan"), n

    # Residualize x and y against z
    z_mat = np.column_stack([z, np.ones(n)])
    coef_x = np.linalg.lstsq(z_mat, x, rcond=None)[0]
    coef_y = np.linalg.lstsq(z_mat, y, rcond=None)[0]
    res_x = x - z_mat @ coef_x
    res_y = y - z_mat @ coef_y

    r, _ = stats.pearsonr(res_x, res_y)
    return round(float(r), 4), n


def main() -> None:
    gt_path = RESULTS_DIR / "theme_gt_summary.csv"
    if not gt_path.exists():
        print(f"ERROR: {gt_path} not found. Run 17_theme_gt_collection.py first.")
        sys.exit(1)

    gt_df = pd.read_csv(gt_path)

    print("=" * 70)
    print("EXPERIMENT 17: Theme-Level YouTube Google Trends Analysis")
    print(f"Loaded {len(gt_df)} themes from GT collection")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Load growth training data
    # -----------------------------------------------------------------------
    db = duckdb.connect(str(DB_PATH), read_only=True)
    training_df = db.execute("""
        SELECT
            li.set_number, li.theme,
            be.subtheme, be.annual_growth_pct
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
    """).df()
    db.close()

    print(f"Loaded {len(training_df)} sets with growth data")
    print()

    # -----------------------------------------------------------------------
    # Theme-level growth aggregates
    # -----------------------------------------------------------------------
    theme_growth = (
        training_df.groupby("theme")["annual_growth_pct"]
        .agg(["mean", "median", "std", "count"])
        .rename(columns={
            "mean": "avg_growth",
            "median": "med_growth",
            "std": "std_growth",
            "count": "n_sets",
        })
        .reset_index()
    )
    theme_growth = theme_growth[theme_growth["n_sets"] >= 3]

    print(f"Theme-level growth aggregates ({len(theme_growth)} themes with >= 3 sets)")
    print()

    # -----------------------------------------------------------------------
    # Join GT with growth
    # -----------------------------------------------------------------------
    merged = pd.merge(gt_df, theme_growth, on="theme", how="inner")

    print("=" * 70)
    print("THEME-LEVEL DATA (sorted by avg_growth)")
    print("=" * 70)
    display_cols = [
        "theme", "theme_type", "avg_growth", "n_sets",
        "avg_lego", "avg_bare", "lego_share",
    ]
    print(
        merged.sort_values("avg_growth", ascending=False)[display_cols]
        .to_string(index=False, float_format="%.2f")
    )
    print()

    # -----------------------------------------------------------------------
    # SECTION 1: Theme-level correlations
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("SECTION 1: Theme-Level Correlations")
    print("=" * 70)

    # All themes
    print("\n--- All Themes ---")
    for feature in ["avg_lego", "peak_lego", "lego_share"]:
        r, p, n = safe_pearsonr(merged[feature], merged["avg_growth"])
        print(f"  {feature:15s} vs avg_growth: r={r:+.4f}, p={p:.4f}, n={n}")

    # Weighted by n_sets
    print("\n--- Weighted by n_sets (all themes) ---")
    for feature in ["avg_lego", "peak_lego", "lego_share"]:
        r, n = weighted_pearsonr(
            merged[feature], merged["avg_growth"], merged["n_sets"]
        )
        print(f"  {feature:15s} vs avg_growth: weighted_r={r:+.4f}, n={n}")

    # Named IPs only (where lego_share is meaningful)
    named = merged[merged["theme_type"] == "named_ip"]
    print(f"\n--- Named IP Themes Only (n={len(named)}) ---")
    for feature in ["avg_lego", "avg_bare", "peak_lego", "peak_bare", "lego_share"]:
        r, p, n = safe_pearsonr(named[feature], named["avg_growth"])
        print(f"  {feature:15s} vs avg_growth: r={r:+.4f}, p={p:.4f}, n={n}")

    # Generic themes (only raw LEGO interest)
    generic = merged[merged["theme_type"] == "generic"]
    print(f"\n--- Generic Themes Only (n={len(generic)}) ---")
    for feature in ["avg_lego", "peak_lego"]:
        r, p, n = safe_pearsonr(generic[feature], generic["avg_growth"])
        print(f"  {feature:15s} vs avg_growth: r={r:+.4f}, p={p:.4f}, n={n}")

    # -----------------------------------------------------------------------
    # SECTION 2: Set-level analysis
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("SECTION 2: Set-Level Correlations")
    print("=" * 70)

    # Merge GT features to individual sets by theme
    set_gt = pd.merge(
        training_df,
        gt_df[["theme", "avg_lego", "avg_bare", "lego_share", "theme_type"]],
        on="theme",
        how="inner",
    )

    print(f"\nSets with GT data: {len(set_gt)}")

    print("\n--- All Sets ---")
    for feature in ["avg_lego", "lego_share"]:
        r, p, n = safe_pearsonr(set_gt[feature], set_gt["annual_growth_pct"])
        print(f"  {feature:15s} vs annual_growth_pct: r={r:+.4f}, p={p:.4f}, n={n}")

    # Named IP sets only
    set_named = set_gt[set_gt["theme_type"] == "named_ip"]
    print(f"\n--- Named IP Sets Only (n={len(set_named)}) ---")
    for feature in ["avg_lego", "avg_bare", "lego_share"]:
        r, p, n = safe_pearsonr(
            set_named[feature], set_named["annual_growth_pct"]
        )
        print(f"  {feature:15s} vs annual_growth_pct: r={r:+.4f}, p={p:.4f}, n={n}")

    # -----------------------------------------------------------------------
    # SECTION 3: Partial correlation (controlling for theme identity)
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("SECTION 3: Partial Correlation (controlling for theme_bayes proxy)")
    print("=" * 70)

    # Use theme average growth as a proxy for theme_bayes
    # (the actual Bayesian encoding is close to the LOO mean for large themes)
    theme_mean_map = theme_growth.set_index("theme")["avg_growth"]
    set_gt = set_gt.copy()
    set_gt["theme_avg_growth"] = set_gt["theme"].map(theme_mean_map)

    for feature in ["avg_lego", "lego_share"]:
        r, n = partial_corr(
            set_gt[feature],
            set_gt["annual_growth_pct"],
            set_gt["theme_avg_growth"],
        )
        print(f"  {feature:15s} | theme_avg: partial_r={r:+.4f}, n={n}")

    set_named_gt = set_gt[set_gt["theme_type"] == "named_ip"].copy()
    print(f"\n  Named IPs only (n={len(set_named_gt)}):")
    for feature in ["avg_lego", "avg_bare", "lego_share"]:
        r, n = partial_corr(
            set_named_gt[feature],
            set_named_gt["annual_growth_pct"],
            set_named_gt["theme_avg_growth"],
        )
        print(f"  {feature:15s} | theme_avg: partial_r={r:+.4f}, n={n}")

    # -----------------------------------------------------------------------
    # SECTION 4: Growth tiers vs GT (like experiment 16)
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("SECTION 4: Growth Tiers vs YouTube GT (cf. Experiment 16)")
    print("=" * 70)

    set_gt = set_gt.copy()
    bins = [-100, 5, 10, 15, 20, 999]
    labels = ["<5%", "5-10%", "10-15%", "15-20%", "20%+"]
    set_gt["growth_tier"] = pd.cut(
        set_gt["annual_growth_pct"], bins=bins, labels=labels
    )

    tier_stats = (
        set_gt.groupby("growth_tier", observed=True)
        .agg(
            n_sets=("annual_growth_pct", "count"),
            avg_lego_gt=("avg_lego", "mean"),
            avg_bare_gt=("avg_bare", "mean"),
            avg_lego_share=("lego_share", "mean"),
        )
        .round(2)
    )
    print()
    print(tier_stats.to_string())

    # -----------------------------------------------------------------------
    # SECTION 5: Outlier themes (high GT interest but low growth, or vice versa)
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("SECTION 5: Interesting Outliers")
    print("=" * 70)

    if "avg_growth" in merged.columns and "avg_lego" in merged.columns:
        # High LEGO GT but below-median growth
        median_growth = merged["avg_growth"].median()
        median_gt = merged["avg_lego"].median()

        high_gt_low_growth = merged[
            (merged["avg_lego"] > median_gt) & (merged["avg_growth"] < median_growth)
        ][["theme", "avg_growth", "avg_lego", "lego_share", "n_sets"]]

        low_gt_high_growth = merged[
            (merged["avg_lego"] <= median_gt) & (merged["avg_growth"] >= median_growth)
        ][["theme", "avg_growth", "avg_lego", "lego_share", "n_sets"]]

        print(f"\nMedian growth: {median_growth:.2f}%, Median LEGO GT: {median_gt:.2f}")

        print(f"\nHigh YouTube Interest, Low Growth (\"priced in\"):")
        if len(high_gt_low_growth) > 0:
            print(high_gt_low_growth.to_string(index=False, float_format="%.2f"))
        else:
            print("  (none)")

        print(f"\nLow YouTube Interest, High Growth (\"hidden gems\"):")
        if len(low_gt_high_growth) > 0:
            print(low_gt_high_growth.to_string(index=False, float_format="%.2f"))
        else:
            print("  (none)")

    # -----------------------------------------------------------------------
    # VERDICT
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    print()
    print("Review the correlations above. Key thresholds:")
    print("  r > 0.3  with lego_share -> worth adding as a feature")
    print("  Significant partial corr  -> adds info beyond theme_bayes")
    print("  Near zero everywhere      -> theme-level YouTube GT doesn't help")
    print()

    # Save merged data for further analysis
    out_path = RESULTS_DIR / "theme_gt_with_growth.csv"
    merged.to_csv(out_path, index=False)
    print(f"Saved merged data to {out_path}")


if __name__ == "__main__":
    main()
