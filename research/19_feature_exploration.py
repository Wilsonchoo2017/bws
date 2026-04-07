"""
19 - Quick Feature Exploration on 700+ Sets
=============================================
Fast correlation scan of untested features against annual_growth_pct.
Uses PostgreSQL directly (no DuckDB lock issues).

Run with: python research/19_feature_exploration.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PG_URL = "postgresql://bws:bws@localhost:5432/bws"


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def corr_report(df: pd.DataFrame, features: list[str], target: str = "annual_growth_pct") -> pd.DataFrame:
    """Compute Pearson + Spearman correlations for each feature vs target."""
    rows = []
    y = df[target]
    for f in features:
        x = pd.to_numeric(df[f], errors="coerce")
        mask = x.notna() & y.notna()
        if mask.sum() < 20:
            continue
        r_p, p_p = stats.pearsonr(x[mask], y[mask])
        r_s, p_s = stats.spearmanr(x[mask], y[mask])
        rows.append({
            "feature": f,
            "n": int(mask.sum()),
            "pearson_r": round(r_p, 3),
            "pearson_p": round(p_p, 4),
            "spearman_r": round(r_s, 3),
            "spearman_p": round(p_s, 4),
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("spearman_r", key=abs, ascending=False)
    return result


def main() -> None:
    import psycopg2

    conn = psycopg2.connect(PG_URL)

    # ----------------------------------------------------------------
    # 1. BASE DATASET
    # ----------------------------------------------------------------
    section("1. BASE DATASET")

    df = pd.read_sql("""
        SELECT
            b.set_number, b.theme, b.subtheme,
            b.year_released, b.year_retired,
            b.pieces as parts_count, b.minifigs as minifig_count,
            b.rrp_usd_cents, b.rrp_gbp_cents,
            b.annual_growth_pct, b.total_growth_pct, b.rolling_growth_pct,
            b.growth_90d_pct, b.theme_rank, b.subtheme_avg_growth_pct,
            b.rating_value, b.review_count,
            b.value_new_cents, b.value_used_cents,
            b.minifig_value_cents, b.exclusive_minifigs,
            b.future_estimate_cents,
            b.distribution_mean_cents, b.distribution_stddev_cents,
            b.designer,
            b.candlestick_json,
            b.sales_trend_json
        FROM brickeconomy_snapshots b
        WHERE b.annual_growth_pct IS NOT NULL
    """, conn)

    print(f"Sets with growth label: {len(df)}")
    print(f"Growth range: [{df['annual_growth_pct'].min():.1f}%, {df['annual_growth_pct'].max():.1f}%]")

    # ----------------------------------------------------------------
    # 2. RATING & REVIEW FEATURES (never tested)
    # ----------------------------------------------------------------
    section("2. RATING & REVIEW FEATURES")

    df["rating"] = pd.to_numeric(df["rating_value"], errors="coerce")
    df["reviews"] = pd.to_numeric(df["review_count"], errors="coerce")
    df["log_reviews"] = np.log1p(df["reviews"])
    df["has_reviews"] = (df["reviews"] > 0).astype(int)

    # Rating per price tier
    df["rrp_usd"] = pd.to_numeric(df["rrp_usd_cents"], errors="coerce") / 100
    df["price_tier"] = pd.cut(df["rrp_usd"], bins=[0, 20, 50, 100, 200, 1000], labels=["budget", "mid", "premium", "high", "ultra"])
    df["rating_x_reviews"] = df["rating"] * df["log_reviews"]

    # New BE fields
    df["mfig_value"] = pd.to_numeric(df["minifig_value_cents"], errors="coerce") / 100
    df["exclusive_mfigs"] = pd.to_numeric(df["exclusive_minifigs"], errors="coerce")
    df["future_est"] = pd.to_numeric(df["future_estimate_cents"], errors="coerce") / 100
    df["dist_mean"] = pd.to_numeric(df["distribution_mean_cents"], errors="coerce") / 100
    df["dist_std"] = pd.to_numeric(df["distribution_stddev_cents"], errors="coerce") / 100
    df["dist_cv"] = df["dist_std"] / df["dist_mean"].replace(0, np.nan)  # coefficient of variation
    df["mfig_value_to_rrp"] = df["mfig_value"] / df["rrp_usd"].replace(0, np.nan)
    df["has_exclusive_mfig"] = (df["exclusive_mfigs"] > 0).astype(int)
    df["has_designer"] = df["designer"].notna().astype(int)
    df["theme_rank_num"] = pd.to_numeric(df["theme_rank"], errors="coerce")
    df["subtheme_avg_g"] = pd.to_numeric(df["subtheme_avg_growth_pct"], errors="coerce")
    df["total_growth"] = pd.to_numeric(df["total_growth_pct"], errors="coerce")
    df["rolling_growth"] = pd.to_numeric(df["rolling_growth_pct"], errors="coerce")
    df["growth_90d"] = pd.to_numeric(df["growth_90d_pct"], errors="coerce")

    rating_features = [
        "rating", "reviews", "log_reviews", "has_reviews", "rating_x_reviews",
        "mfig_value", "exclusive_mfigs", "mfig_value_to_rrp", "has_exclusive_mfig",
        "has_designer", "dist_cv", "theme_rank_num", "subtheme_avg_g",
    ]
    report = corr_report(df, rating_features)
    print(report.to_string(index=False))

    # ----------------------------------------------------------------
    # 3. SHELF LIFE & TIMING FEATURES (never tested)
    # ----------------------------------------------------------------
    section("3. SHELF LIFE & TIMING FEATURES")

    df["yr_released"] = pd.to_numeric(df["year_released"], errors="coerce")
    df["yr_retired"] = pd.to_numeric(df["year_retired"], errors="coerce")
    df["shelf_life_years"] = df["yr_retired"] - df["yr_released"]
    df["retirement_era"] = df["yr_retired"]  # raw year as feature

    # Sets retired quickly vs slowly
    df["short_shelf"] = (df["shelf_life_years"] <= 1).astype(int)
    df["long_shelf"] = (df["shelf_life_years"] >= 3).astype(int)

    timing_features = ["shelf_life_years", "retirement_era", "short_shelf", "long_shelf", "yr_released"]
    report = corr_report(df, timing_features)
    print(report.to_string(index=False))

    # ----------------------------------------------------------------
    # 4. PRICE GEOMETRY FEATURES (new combinations)
    # ----------------------------------------------------------------
    section("4. PRICE GEOMETRY FEATURES")

    df["rrp_gbp"] = pd.to_numeric(df["rrp_gbp_cents"], errors="coerce") / 100
    df["parts"] = pd.to_numeric(df["parts_count"], errors="coerce")
    df["mfigs"] = pd.to_numeric(df["minifig_count"], errors="coerce")

    df["usd_gbp_ratio"] = df["rrp_usd"] / df["rrp_gbp"].replace(0, np.nan)
    df["price_per_part"] = df["rrp_usd"] / df["parts"].replace(0, np.nan)
    df["price_per_mfig"] = df["rrp_usd"] / df["mfigs"].replace(0, np.nan)
    df["parts_per_mfig"] = df["parts"] / df["mfigs"].replace(0, np.nan)
    df["log_rrp"] = np.log1p(df["rrp_usd"])
    df["log_parts"] = np.log1p(df["parts"])
    df["rrp_squared"] = df["rrp_usd"] ** 2  # nonlinear price effect

    # Value premium: current value vs RRP
    df["value_new"] = pd.to_numeric(df["value_new_cents"], errors="coerce") / 100
    df["value_to_rrp"] = df["value_new"] / df["rrp_usd"].replace(0, np.nan)

    price_features = [
        "usd_gbp_ratio", "price_per_part", "price_per_mfig", "parts_per_mfig",
        "log_rrp", "log_parts", "rrp_squared", "rrp_usd", "parts", "mfigs",
        "value_to_rrp",
    ]
    report = corr_report(df, price_features)
    print(report.to_string(index=False))
    print("\nNOTE: value_to_rrp is LEAKY (uses current value)")

    # ----------------------------------------------------------------
    # 5. BRICKLINK CURRENT MARKET FEATURES
    # ----------------------------------------------------------------
    section("5. BRICKLINK CURRENT MARKET (skipped -- current snapshot is leaky)")

    # ----------------------------------------------------------------
    # 6. BRICKLINK MONTHLY SALES FEATURES (time-gated)
    # ----------------------------------------------------------------
    section("6. BRICKLINK MONTHLY SALES (pre-retirement, time-gated)")

    # Get monthly sales joined with retirement year
    sales_df = pd.read_sql("""
        SELECT
            b.set_number,
            bm.year as sale_year, bm.month as sale_month,
            bm.condition, bm.times_sold, bm.total_quantity,
            bm.avg_price, bm.min_price, bm.max_price,
            b.year_retired,
            b.annual_growth_pct
        FROM bricklink_monthly_sales bm
        JOIN bricklink_items bi ON bm.item_id = bi.item_id
        JOIN brickeconomy_snapshots b ON (bi.item_id = b.set_number || '-1')
        WHERE b.annual_growth_pct IS NOT NULL
          AND b.year_retired IS NOT NULL
    """, conn)

    print(f"Monthly sales rows: {len(sales_df)}")
    print(f"Unique sets: {sales_df['set_number'].nunique()}")

    if not sales_df.empty:
        # Time-gate: only use sales data from BEFORE retirement year
        sales_df["sale_year"] = pd.to_numeric(sales_df["sale_year"], errors="coerce")
        sales_df["year_retired"] = pd.to_numeric(sales_df["year_retired"], errors="coerce")
        pre_retire = sales_df[sales_df["sale_year"] < sales_df["year_retired"]]
        print(f"Pre-retirement sales rows: {len(pre_retire)}")

        if not pre_retire.empty:
            # Aggregate per set: pre-retirement sales velocity
            agg = pre_retire.groupby("set_number").agg(
                total_sold=("times_sold", "sum"),
                total_qty=("total_quantity", "sum"),
                avg_price_mean=("avg_price", "mean"),
                price_spread=("max_price", "max"),  # will compute spread below
                min_price=("min_price", "min"),
                n_months=("sale_month", "count"),
                annual_growth_pct=("annual_growth_pct", "first"),
            ).reset_index()

            agg["price_spread"] = agg["price_spread"] - agg["min_price"]
            agg["monthly_velocity"] = agg["total_sold"] / agg["n_months"].replace(0, np.nan)
            agg["log_total_sold"] = np.log1p(agg["total_sold"])
            agg["avg_qty_per_sale"] = agg["total_qty"] / agg["total_sold"].replace(0, np.nan)

            sales_features = [
                "total_sold", "log_total_sold", "monthly_velocity",
                "avg_price_mean", "price_spread", "n_months", "avg_qty_per_sale",
            ]
            report = corr_report(agg, sales_features)
            print(report.to_string(index=False))
        else:
            print("No pre-retirement sales data available")

    # ----------------------------------------------------------------
    # 7. MINIFIG FEATURES (new: minifig value signals)
    # ----------------------------------------------------------------
    section("7. MINIFIG VALUE FEATURES")

    mfig_df = pd.read_sql("""
        SELECT
            b.set_number,
            COUNT(DISTINCT sm.minifig_id) as unique_mfigs,
            SUM(sm.quantity) as total_mfig_qty,
            b.annual_growth_pct
        FROM set_minifigures sm
        JOIN brickeconomy_snapshots b ON (sm.set_item_id = b.set_number || '-1')
        WHERE b.annual_growth_pct IS NOT NULL
        GROUP BY b.set_number, b.annual_growth_pct
    """, conn)

    print(f"Sets with minifig data: {len(mfig_df)}")

    if not mfig_df.empty:
        mfig_merged = mfig_df.merge(
            df[["set_number", "rrp_usd", "parts"]].drop_duplicates(),
            on="set_number", how="left",
        )
        mfig_merged["mfigs_per_dollar"] = mfig_merged["unique_mfigs"] / mfig_merged["rrp_usd"].replace(0, np.nan)
        mfig_merged["mfig_qty_ratio"] = mfig_merged["total_mfig_qty"] / mfig_merged["unique_mfigs"].replace(0, np.nan)

        mfig_features = ["unique_mfigs", "total_mfig_qty", "mfigs_per_dollar", "mfig_qty_ratio"]
        report = corr_report(mfig_merged, mfig_features)
        print(report.to_string(index=False))

    # ----------------------------------------------------------------
    # 8. GOOGLE TRENDS RE-CHECK (488 sets now vs 78 before)
    # ----------------------------------------------------------------
    section("8. GOOGLE TRENDS RE-CHECK (488 sets)")

    gt_df = pd.read_sql("""
        SELECT
            g.set_number,
            g.interest_json,
            b.annual_growth_pct
        FROM google_trends_snapshots g
        JOIN brickeconomy_snapshots b ON g.set_number = b.set_number
        WHERE b.annual_growth_pct IS NOT NULL
          AND g.interest_json IS NOT NULL
    """, conn)

    print(f"GT sets with growth: {len(gt_df)}")

    if not gt_df.empty:
        import json

        gt_features_rows = []
        for _, row in gt_df.iterrows():
            try:
                interest = json.loads(row["interest_json"]) if isinstance(row["interest_json"], str) else row["interest_json"]
                if not interest:
                    continue
                # Format: list of [date, value] pairs OR list of values OR dict
                if isinstance(interest, dict):
                    values = [v for v in interest.values() if isinstance(v, (int, float))]
                elif isinstance(interest, list):
                    if interest and isinstance(interest[0], list):
                        values = [pair[1] for pair in interest if len(pair) >= 2 and isinstance(pair[1], (int, float))]
                    else:
                        values = [v for v in interest if isinstance(v, (int, float))]
                else:
                    continue
                if not values:
                    continue
                arr = np.array(values, dtype=float)
                gt_features_rows.append({
                    "set_number": row["set_number"],
                    "annual_growth_pct": row["annual_growth_pct"],
                    "gt_mean": np.mean(arr),
                    "gt_max": np.max(arr),
                    "gt_nonzero_pct": (arr > 0).mean() * 100,
                    "gt_n_spikes": int((arr >= 50).sum()),
                    "gt_trend": np.polyfit(range(len(arr)), arr, 1)[0] if len(arr) > 1 else 0,
                    "gt_last_quarter_mean": np.mean(arr[-13:]) if len(arr) >= 13 else np.mean(arr),
                })
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        gt_feat_df = pd.DataFrame(gt_features_rows)
        print(f"Parsed GT features: {len(gt_feat_df)} sets")

        if not gt_feat_df.empty:
            gt_feature_names = ["gt_mean", "gt_max", "gt_nonzero_pct", "gt_n_spikes", "gt_trend", "gt_last_quarter_mean"]
            report = corr_report(gt_feat_df, gt_feature_names)
            print(report.to_string(index=False))
        else:
            print("No parseable GT features found")

    # ----------------------------------------------------------------
    # 9. KEEPA FEATURES RE-CHECK (440 sets)
    # ----------------------------------------------------------------
    section("9. KEEPA RE-CHECK (440 sets)")

    keepa_df = pd.read_sql("""
        SELECT
            k.set_number,
            k.amazon_price_json, k.new_3p_fba_json,
            k.buy_box_json, k.tracking_users,
            b.annual_growth_pct,
            b.rrp_usd_cents
        FROM keepa_snapshots k
        JOIN brickeconomy_snapshots b ON k.set_number = b.set_number
        WHERE b.annual_growth_pct IS NOT NULL
    """, conn)

    print(f"Keepa sets with growth: {len(keepa_df)}")

    if not keepa_df.empty:
        keepa_df["tracking_users"] = pd.to_numeric(keepa_df["tracking_users"], errors="coerce")
        keepa_df["log_tracking"] = np.log1p(keepa_df["tracking_users"])

        keepa_features = ["tracking_users", "log_tracking"]
        report = corr_report(keepa_df, keepa_features)
        print(report.to_string(index=False))

    # ----------------------------------------------------------------
    # 10. THEME COHORT FEATURES
    # ----------------------------------------------------------------
    section("10. THEME COHORT SIZE & COMPETITION")

    cohort = df.groupby("theme").agg(
        theme_size=("set_number", "count"),
        theme_avg_growth=("annual_growth_pct", "mean"),
        theme_std_growth=("annual_growth_pct", "std"),
    ).reset_index()

    df_cohort = df.merge(cohort, on="theme", how="left")
    df_cohort["theme_crowded"] = (df_cohort["theme_size"] > df_cohort["theme_size"].median()).astype(int)

    sub_cohort = df.groupby("subtheme").agg(
        subtheme_size=("set_number", "count"),
    ).reset_index()
    df_cohort = df_cohort.merge(sub_cohort, on="subtheme", how="left")

    cohort_features = ["theme_size", "theme_crowded", "subtheme_size", "theme_std_growth"]
    report = corr_report(df_cohort, cohort_features)
    print(report.to_string(index=False))

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    section("SUMMARY: TOP FEATURES BY |SPEARMAN r|")

    # Collect all results we printed
    all_features = []

    # Re-run on the full merged dataset
    df_full = df.copy()
    all_feat_names = [
        "rating", "reviews", "log_reviews", "rating_x_reviews",
        "mfig_value", "exclusive_mfigs", "mfig_value_to_rrp",
        "has_exclusive_mfig", "has_designer", "dist_cv",
        "theme_rank_num", "subtheme_avg_g",
        "shelf_life_years", "retirement_era", "short_shelf", "long_shelf",
        "usd_gbp_ratio", "price_per_part", "log_rrp", "log_parts",
        "rrp_usd", "parts", "mfigs", "rrp_squared",
        "theme_size", "subtheme_size",
    ]

    # Add cohort features
    df_full = df_full.merge(cohort, on="theme", how="left")
    df_full = df_full.merge(sub_cohort, on="subtheme", how="left")

    report = corr_report(df_full, [f for f in all_feat_names if f in df_full.columns])
    print(report.to_string(index=False))

    print(f"\n{'=' * 60}")
    print("  EXPLORATION COMPLETE")
    print(f"{'=' * 60}")

    conn.close()


if __name__ == "__main__":
    main()
