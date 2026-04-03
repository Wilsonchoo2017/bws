"""Leakage-free evaluation for growth models.

Addresses critical data leakage vectors:
1. Feature-target circularity: excludes features derived from same source as target
2. Temporal leakage: proper train/test split by year
3. In-sample inflation: reports only out-of-sample metrics
4. Cutoff enforcement: ensures Tier 2 Keepa features are filtered

Uses walk-forward evaluation: train on older data, test on newer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Features that are derived from the SAME data source as annual_growth_pct.
# Using these to predict growth is circular (target leakage).
CIRCULAR_FEATURES: frozenset[str] = frozenset({
    # BrickEconomy chart features -- computed from value_chart_json which
    # is the underlying data behind annual_growth_pct
    "be_value_trend_pct",
    "be_value_momentum",
    "be_value_cv",
    "be_value_max_drawdown",
    "be_value_recovery",
    "be_value_months",
    # These directly reference current market value
    "value_new_vs_rrp",
    "annual_growth_pct",
    "rolling_growth_pct",
    "growth_90d_pct",
    # BE future estimate is derived from value trajectory
    "be_future_est_return",
})

# Features that are acceptable: static attributes, demand signals,
# and supply-side signals that exist INDEPENDENTLY of price appreciation.
# e.g. parts_count, theme, Keepa tracking_users, BrickLink volume, etc.


@dataclass(frozen=True)
class LeakageReport:
    """Results of a leakage-free evaluation."""

    n_train: int
    n_test: int
    n_features: int
    feature_names: tuple[str, ...]
    # Out-of-sample metrics
    oos_r2: float
    oos_mae: float
    oos_rmse: float
    # Directional accuracy
    direction_accuracy: float  # % of test sets where predicted direction matches actual
    # Quintile analysis
    top_quintile_avg_return: float
    bottom_quintile_avg_return: float
    quintile_spread: float
    # Feature importance (non-circular features only)
    top_features: tuple[tuple[str, float], ...] = ()
    # Leakage flags
    circular_features_excluded: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def evaluate_leakage_free(
    conn: DuckDBPyConnection,
) -> LeakageReport:
    """Run a full leakage-free evaluation of the growth prediction model.

    1. Loads all sets with growth data
    2. Excludes circular features (derived from same source as target)
    3. Splits by year (older train, newer test)
    4. Trains a clean model
    5. Reports out-of-sample metrics only
    """
    from services.ml.extractors import extract_all as extract_all_plugin
    from services.ml.helpers import compute_cutoff_dates
    from services.ml.queries import load_base_metadata, load_growth_training_data

    # Load training data
    df_raw = load_growth_training_data(conn)
    if df_raw.empty:
        raise ValueError("No growth training data available")

    set_numbers = df_raw["set_number"].tolist()
    target = df_raw.set_index("set_number")["annual_growth_pct"]

    # Extract features via plugin system
    from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT

    base = load_base_metadata(conn, set_numbers)
    base = compute_cutoff_dates(base, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)

    features_df = extract_all_plugin(conn, base)
    if features_df.empty:
        raise ValueError("No features extracted")

    # features_df already contains annual_growth_pct from extractors;
    # use the canonical target from df_raw instead
    if "annual_growth_pct" in features_df.columns:
        features_df = features_df.drop(columns=["annual_growth_pct"])

    # Merge features with target
    merged = features_df.merge(
        target.reset_index(), on="set_number", how="inner"
    )
    logger.info("Merged: %d sets with features + target", len(merged))

    # Identify and exclude circular features
    all_feature_cols = [
        c for c in merged.columns
        if c not in {"set_number", "annual_growth_pct"}
        and merged[c].dtype in ("float64", "int64", "float32", "int32")
    ]

    excluded = [f for f in all_feature_cols if f in CIRCULAR_FEATURES]
    clean_features = [f for f in all_feature_cols if f not in CIRCULAR_FEATURES]

    # Drop features with <10% coverage
    clean_features = [
        f for f in clean_features
        if merged[f].notna().sum() / len(merged) >= 0.10
    ]

    logger.info(
        "Features: %d total, %d circular excluded, %d clean",
        len(all_feature_cols), len(excluded), len(clean_features),
    )

    if len(clean_features) < 3:
        raise ValueError(f"Only {len(clean_features)} non-circular features")

    # Temporal split: use year_released as proxy for cohort ordering
    # (since most sets here are active, year_retired isn't available)
    year_col = None
    if "year_released" in base.columns:
        yr_map = base.set_index("set_number")["year_released"]
        merged["_split_year"] = merged["set_number"].map(yr_map)
        year_col = "_split_year"

    if year_col and merged[year_col].notna().sum() > len(merged) * 0.5:
        sorted_df = merged.sort_values(year_col)
    else:
        # Fallback: random split with seed (less ideal but honest)
        sorted_df = merged.sample(frac=1, random_state=42)

    # 80/20 split
    split_idx = int(len(sorted_df) * 0.8)
    train_df = sorted_df.iloc[:split_idx].copy()
    test_df = sorted_df.iloc[split_idx:].copy()

    warnings: list[str] = []
    if len(train_df) < 20:
        warnings.append(f"Small training set: {len(train_df)}")
    if len(test_df) < 10:
        warnings.append(f"Small test set: {len(test_df)}")

    # Prepare matrices
    X_train = train_df[clean_features].copy()
    y_train = train_df["annual_growth_pct"].values.astype(float)
    X_test = test_df[clean_features].copy()
    y_test = test_df["annual_growth_pct"].values.astype(float)

    for c in X_train.columns:
        X_train[c] = pd.to_numeric(X_train[c], errors="coerce")
        X_test[c] = pd.to_numeric(X_test[c], errors="coerce")

    fill = X_train.median()
    X_train = X_train.fillna(fill)
    X_test = X_test.fillna(fill)

    # Drop highly correlated features
    corr = X_train.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1))
    to_drop = set()
    for col in upper.columns:
        for hc in upper.index[upper[col] > 0.95]:
            if hc not in to_drop:
                if X_train[col].var() >= X_train[hc].var():
                    to_drop.add(hc)
                else:
                    to_drop.add(col)

    final_features = [f for f in clean_features if f not in to_drop]
    X_train = X_train[final_features]
    X_test = X_test[final_features]

    # Train
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=5,
        learning_rate=0.02,
        random_state=42,
    )
    model.fit(X_train_s, y_train)

    # Out-of-sample predictions
    y_pred = model.predict(X_test_s)

    # Metrics
    ss_res = np.sum((y_test - y_pred) ** 2)
    ss_tot = np.sum((y_test - y_test.mean()) ** 2)
    oos_r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    oos_mae = float(mean_absolute_error(y_test, y_pred))
    oos_rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))

    # Directional accuracy
    direction_correct = np.sum(np.sign(y_pred) == np.sign(y_test))
    direction_accuracy = float(direction_correct / len(y_test) * 100)

    # Quintile analysis
    n_q = max(1, len(y_test) // 5)
    pred_order = np.argsort(y_pred)
    top_q_actual = y_test[pred_order[-n_q:]]
    bottom_q_actual = y_test[pred_order[:n_q]]
    top_avg = float(np.mean(top_q_actual))
    bottom_avg = float(np.mean(bottom_q_actual))

    # Feature importances
    importances = model.feature_importances_
    ranked = sorted(zip(final_features, importances), key=lambda x: -x[1])[:10]

    return LeakageReport(
        n_train=len(y_train),
        n_test=len(y_test),
        n_features=len(final_features),
        feature_names=tuple(final_features),
        oos_r2=oos_r2,
        oos_mae=oos_mae,
        oos_rmse=oos_rmse,
        direction_accuracy=direction_accuracy,
        top_quintile_avg_return=top_avg,
        bottom_quintile_avg_return=bottom_avg,
        quintile_spread=top_avg - bottom_avg,
        top_features=tuple((n, float(v)) for n, v in ranked),
        circular_features_excluded=tuple(excluded),
        warnings=tuple(warnings),
    )


def compare_with_vs_without_leakage(
    conn: DuckDBPyConnection,
) -> None:
    """Print side-by-side comparison of leaked vs clean model performance.

    This is the key diagnostic: shows how much of the R2 was from leakage.
    """
    from services.ml.extractors import extract_all as extract_all_plugin
    from services.ml.helpers import offset_months
    from services.ml.queries import load_base_metadata, load_growth_training_data

    df_raw = load_growth_training_data(conn)
    set_numbers = df_raw["set_number"].tolist()
    target = df_raw.set_index("set_number")["annual_growth_pct"]

    base = load_base_metadata(conn, set_numbers)
    base["cutoff_year"] = None
    base["cutoff_month"] = None

    features_df = extract_all_plugin(conn, base)

    # features_df already contains annual_growth_pct from extractors;
    # use the canonical target from df_raw instead
    if "annual_growth_pct" in features_df.columns:
        features_df = features_df.drop(columns=["annual_growth_pct"])

    merged = features_df.merge(target.reset_index(), on="set_number", how="inner")

    all_feature_cols = [
        c for c in merged.columns
        if c not in {"set_number", "annual_growth_pct"}
        and merged[c].dtype in ("float64", "int64", "float32", "int32")
    ]

    # Split
    if "year_released" in base.columns:
        yr_map = base.set_index("set_number")["year_released"]
        merged["_yr"] = merged["set_number"].map(yr_map)
        sorted_df = merged.sort_values("_yr")
    else:
        sorted_df = merged.sample(frac=1, random_state=42)

    split_idx = int(len(sorted_df) * 0.8)
    train = sorted_df.iloc[:split_idx]
    test = sorted_df.iloc[split_idx:]

    y_train = train["annual_growth_pct"].values.astype(float)
    y_test = test["annual_growth_pct"].values.astype(float)

    results: list[tuple[str, float, float, int]] = []

    for label, feature_set in [
        ("ALL features (leaked)", all_feature_cols),
        ("Circular excluded (clean)", [f for f in all_feature_cols if f not in CIRCULAR_FEATURES]),
        ("Intrinsics only (safest)", [
            f for f in all_feature_cols
            if f.startswith(("parts_", "minifig_", "is_", "shelf_", "pieces_", "price_tier",
                             "price_per", "rrp_", "rating_", "review_", "keepa_rating",
                             "keepa_review", "keepa_tracking"))
        ]),
    ]:
        usable = [f for f in feature_set if f in merged.columns and merged[f].notna().sum() / len(merged) >= 0.10]
        if len(usable) < 3:
            results.append((label, float("nan"), float("nan"), len(usable)))
            continue

        Xtr = train[usable].copy()
        Xte = test[usable].copy()
        for c in Xtr.columns:
            Xtr[c] = pd.to_numeric(Xtr[c], errors="coerce")
            Xte[c] = pd.to_numeric(Xte[c], errors="coerce")
        fill = Xtr.median()
        Xtr = Xtr.fillna(fill)
        Xte = Xte.fillna(fill)

        scaler = StandardScaler()
        Xtr_s = scaler.fit_transform(Xtr)
        Xte_s = scaler.transform(Xte)

        model = GradientBoostingRegressor(
            n_estimators=300, max_depth=4, min_samples_leaf=5,
            learning_rate=0.02, random_state=42,
        )
        model.fit(Xtr_s, y_train)

        # In-sample
        y_pred_train = model.predict(Xtr_s)
        ss_res_tr = np.sum((y_train - y_pred_train) ** 2)
        ss_tot_tr = np.sum((y_train - y_train.mean()) ** 2)
        r2_in = float(1 - ss_res_tr / ss_tot_tr) if ss_tot_tr > 0 else 0

        # Out-of-sample
        y_pred = model.predict(Xte_s)
        ss_res = np.sum((y_test - y_pred) ** 2)
        ss_tot = np.sum((y_test - y_test.mean()) ** 2)
        r2_oos = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0

        results.append((label, r2_in, r2_oos, len(usable)))

    print()
    print("=" * 80)
    print("LEAKAGE COMPARISON: In-Sample vs Out-of-Sample R2")
    print("=" * 80)
    print(f"Train: {len(y_train)} sets | Test: {len(y_test)} sets (80/20 temporal split)")
    print()
    print(f"{'Model':<35s}  {'Features':>8s}  {'R2 (in)':>8s}  {'R2 (OOS)':>8s}  {'Gap':>6s}")
    print("-" * 75)
    for label, r2_in, r2_oos, n_feat in results:
        gap = r2_in - r2_oos if not np.isnan(r2_in) else float("nan")
        print(f"{label:<35s}  {n_feat:>8d}  {r2_in:>8.3f}  {r2_oos:>8.3f}  {gap:>+5.3f}")
    print()
    print("A large gap (In - OOS) indicates leakage or overfitting.")
    print("Circular features excluded: value_trend, momentum, CV, drawdown, growth_%")
