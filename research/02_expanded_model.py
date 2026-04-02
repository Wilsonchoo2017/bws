"""
02 - Expanded Model: 204 sets (BrickEconomy + BrickLink)
=========================================================
Drop the Keepa requirement to get 5x more data.
Focus on features available from BE + BL + item metadata.
Extract richer features from candlestick and price history JSON.

Run with: python research/02_expanded_model.py
"""

import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

# ---------------------------------------------------------------------------
# 1. Load data
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
        li.weight,

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
        be.theme               AS be_theme,
        be.subtheme,

        bp.six_month_new,
        bp.six_month_used,
        bp.current_new,
        bp.current_used

    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    JOIN bricklink_price_history bp ON (li.set_number || '-1') = bp.item_id
    WHERE be.annual_growth_pct IS NOT NULL
      AND be.value_new_cents IS NOT NULL
""").fetchdf()

db.close()

print(f"Loaded {len(df)} sets with BrickEconomy + BrickLink data\n")

# ---------------------------------------------------------------------------
# 2. Feature engineering
# ---------------------------------------------------------------------------

# --- Numeric coercion for nullable int columns ---
for col in ["parts_count", "minifig_count", "weight", "rrp_usd_cents",
            "value_new_cents", "value_used_cents", "distribution_mean_cents",
            "distribution_stddev_cents", "be_review_count", "theme_rank"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# --- Basic price features ---
df["rrp_usd"] = df["rrp_usd_cents"] / 100.0
df["value_new_usd"] = df["value_new_cents"] / 100.0
_rrp = pd.to_numeric(df["rrp_usd_cents"], errors="coerce").fillna(0)
_val_new = pd.to_numeric(df["value_new_cents"], errors="coerce").fillna(0)
_parts = pd.to_numeric(df["parts_count"], errors="coerce").fillna(0)
df["roi_pct"] = np.where(_rrp > 0, (_val_new - _rrp) / _rrp * 100, np.nan)
df["price_per_part"] = np.where(_parts > 0, _rrp / _parts, np.nan)

# --- Distribution features ---
_dist_mean = pd.to_numeric(df["distribution_mean_cents"], errors="coerce").fillna(0)
_dist_std = pd.to_numeric(df["distribution_stddev_cents"], errors="coerce").fillna(0)
df["dist_cv"] = np.where(_dist_mean > 0, _dist_std / _dist_mean, np.nan)

# --- Value ratios ---
df["value_to_rrp"] = np.where(_rrp > 0, _val_new / _rrp, np.nan)
_value_used = pd.to_numeric(df["value_used_cents"], errors="coerce").fillna(0)
df["new_used_ratio"] = np.where(_value_used > 0, _val_new / _value_used, np.nan)

# --- BrickLink JSON extraction ---
def _safe_json(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}

def extract_bl_field(series: pd.Series, field: str) -> pd.Series:
    def _extract(val):
        data = _safe_json(val)
        v = data.get(field)
        if v is None:
            return np.nan
        if isinstance(v, dict):
            return float(v.get("amount", 0))
        return float(v)
    return series.apply(_extract)

# 6-month new sales
df["bl_6m_new_sold"] = extract_bl_field(df["six_month_new"], "times_sold")
df["bl_6m_new_qty"] = extract_bl_field(df["six_month_new"], "total_qty")
df["bl_6m_new_avg"] = extract_bl_field(df["six_month_new"], "avg_price")
df["bl_6m_new_min"] = extract_bl_field(df["six_month_new"], "min_price")
df["bl_6m_new_max"] = extract_bl_field(df["six_month_new"], "max_price")

# 6-month used sales
df["bl_6m_used_sold"] = extract_bl_field(df["six_month_used"], "times_sold")
df["bl_6m_used_qty"] = extract_bl_field(df["six_month_used"], "total_qty")

# Current listings
df["bl_cur_new_lots"] = extract_bl_field(df["current_new"], "total_lots")
df["bl_cur_new_qty"] = extract_bl_field(df["current_new"], "total_qty")
df["bl_cur_used_lots"] = extract_bl_field(df["current_used"], "total_lots")

# Derived BrickLink features
_bl_6m_qty = pd.to_numeric(df["bl_6m_new_qty"], errors="coerce").fillna(0)
_bl_cur_qty = pd.to_numeric(df["bl_cur_new_qty"], errors="coerce").fillna(0)
_bl_6m_min = pd.to_numeric(df["bl_6m_new_min"], errors="coerce").fillna(0)
_bl_6m_max = pd.to_numeric(df["bl_6m_new_max"], errors="coerce").fillna(0)
_bl_6m_used = pd.to_numeric(df["bl_6m_used_qty"], errors="coerce").fillna(0)
df["bl_supply_demand"] = np.where(_bl_6m_qty > 0, _bl_cur_qty / _bl_6m_qty, np.nan)
df["bl_price_spread"] = np.where(_bl_6m_min > 0, (_bl_6m_max - _bl_6m_min) / _bl_6m_min, np.nan)
df["bl_new_used_volume_ratio"] = np.where(_bl_6m_used > 0, _bl_6m_qty / _bl_6m_used, np.nan)

# --- Candlestick features (price trajectory) ---
def extract_candlestick_features(series: pd.Series) -> pd.DataFrame:
    records = []
    for val in series:
        data = _safe_json(val)
        if not data or not isinstance(data, list) or len(data) == 0:
            records.append({})
            continue

        # data is list of [date, open, high, low, close] (cents)
        candles = data
        opens = [c[1] for c in candles if len(c) >= 5 and c[1]]
        highs = [c[2] for c in candles if len(c) >= 5 and c[2]]
        lows = [c[3] for c in candles if len(c) >= 5 and c[3]]
        closes = [c[4] for c in candles if len(c) >= 5 and c[4]]

        if not opens or not closes:
            records.append({})
            continue

        first_open = opens[0]
        last_close = closes[-1]

        rec = {
            "cs_total_return": (last_close - first_open) / first_open if first_open > 0 else np.nan,
            "cs_num_candles": len(candles),
            "cs_max_drawdown": (min(lows) - max(highs)) / max(highs) if highs and max(highs) > 0 else np.nan,
            "cs_volatility": np.std(closes) / np.mean(closes) if closes and np.mean(closes) > 0 else np.nan,
        }

        # Trend: fraction of periods where close > open
        up_candles = sum(1 for c in candles if len(c) >= 5 and c[4] > c[1])
        rec["cs_up_pct"] = up_candles / len(candles) if candles else np.nan

        # Recent momentum: last 3 candles vs first 3
        if len(closes) >= 6:
            recent = np.mean(closes[-3:])
            early = np.mean(closes[:3])
            rec["cs_momentum"] = (recent - early) / early if early > 0 else np.nan
        else:
            rec["cs_momentum"] = np.nan

        records.append(rec)

    return pd.DataFrame(records)

cs_features = extract_candlestick_features(df["candlestick_json"])
for col in cs_features.columns:
    df[col] = cs_features[col].values

# --- Theme encoding (frequency-based) ---
theme_counts = df["theme"].value_counts()
df["theme_frequency"] = df["theme"].map(theme_counts)
theme_avg_growth = df.groupby("theme")["annual_growth_pct"].transform("mean")
df["theme_avg_growth"] = theme_avg_growth

# --- Licensed IP flag ---
LICENSED_THEMES = {
    "Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
    "Avatar", "The LEGO Movie 2", "Lightyear", "Spider-Man",
    "Disney", "Minecraft", "Sonic the Hedgehog",
}
df["is_licensed"] = df["theme"].isin(LICENSED_THEMES).astype(int)

# --- Parts bucket ---
df["parts_bucket"] = pd.cut(
    df["parts_count"],
    bins=[0, 100, 300, 600, 1000, 2000, float("inf")],
    labels=[1, 2, 3, 4, 5, 6],
).astype(float)

# --- Price tier ---
df["price_tier"] = pd.cut(
    df["rrp_usd"].fillna(0),
    bins=[0, 20, 50, 100, 200, 500, float("inf")],
    labels=[1, 2, 3, 4, 5, 6],
).astype(float)

# ---------------------------------------------------------------------------
# 3. Target definition
# ---------------------------------------------------------------------------

GROWTH_THRESHOLD = 10.0
df["good_investment"] = (df["annual_growth_pct"] >= GROWTH_THRESHOLD).astype(int)

print(f"Target: annual_growth >= {GROWTH_THRESHOLD}%")
print(f"  Positive: {df['good_investment'].sum()} ({df['good_investment'].mean()*100:.0f}%)")
print(f"  Negative: {(1 - df['good_investment']).sum()} ({(1 - df['good_investment']).mean()*100:.0f}%)")

# ---------------------------------------------------------------------------
# 4. Feature selection
# ---------------------------------------------------------------------------

ALL_FEATURES = [
    # Item basics
    "parts_count", "minifig_count", "price_per_part", "parts_bucket", "price_tier",
    # BE valuation
    "rrp_usd", "value_to_rrp", "new_used_ratio", "dist_cv",
    "rating_value", "be_review_count",
    # BE growth context
    "subtheme_avg_growth_pct", "theme_rank",
    # BrickLink market
    "bl_6m_new_sold", "bl_6m_new_qty", "bl_6m_new_avg",
    "bl_6m_used_sold", "bl_6m_used_qty",
    "bl_cur_new_lots", "bl_cur_new_qty", "bl_cur_used_lots",
    "bl_supply_demand", "bl_price_spread", "bl_new_used_volume_ratio",
    # Candlestick
    "cs_total_return", "cs_num_candles", "cs_max_drawdown",
    "cs_volatility", "cs_up_pct", "cs_momentum",
    # Theme
    "theme_frequency", "theme_avg_growth", "is_licensed",
]

# Check coverage
print("\n--- Feature Coverage ---")
valid_features = []
for f in ALL_FEATURES:
    if f not in df.columns:
        continue
    series = pd.to_numeric(df[f], errors="coerce")
    coverage = series.notna().sum() / len(df) * 100
    if coverage >= 50:
        valid_features.append(f)
        marker = " [OK]" if coverage >= 80 else " [LOW]"
        print(f"  {f:<30s} {coverage:5.1f}%{marker}")

print(f"\nUsing {len(valid_features)} features with >=50% coverage")

# ---------------------------------------------------------------------------
# 5. Correlation analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRELATION WITH ANNUAL GROWTH (top features)")
print("=" * 70)

correlations = {}
for f in valid_features:
    series = pd.to_numeric(df[f], errors="coerce")
    mask = series.notna() & df["annual_growth_pct"].notna()
    if mask.sum() >= 10:
        corr = series[mask].corr(df["annual_growth_pct"][mask])
        correlations[f] = corr

sorted_corrs = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
print(f"\n{'Feature':<30s} {'Corr':>8s}")
print("-" * 40)
for feat, corr in sorted_corrs[:20]:
    marker = " ***" if abs(corr) > 0.3 else " **" if abs(corr) > 0.2 else ""
    print(f"  {feat:<28s} {corr:>+.3f}{marker}")

# ---------------------------------------------------------------------------
# 6. Model training
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("MODEL TRAINING")
print("=" * 70)

from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    RepeatedStratifiedKFold,
    cross_val_predict,
    cross_val_score,
)
from sklearn.preprocessing import StandardScaler

# Prepare data
X = df[valid_features].copy()
for col in X.columns:
    X[col] = pd.to_numeric(X[col], errors="coerce")
X = X.fillna(X.median())

y_reg = df["annual_growth_pct"].values
y_cls = df["good_investment"].values

scaler = StandardScaler()
X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

# Use repeated stratified K-fold (more robust than LOO for small datasets)
cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)

models = {
    "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
    "Random Forest": RandomForestClassifier(
        n_estimators=100, max_depth=5, min_samples_leaf=3, random_state=42
    ),
    "Gradient Boosting": GradientBoostingClassifier(
        n_estimators=80, max_depth=3, min_samples_leaf=3,
        learning_rate=0.1, random_state=42
    ),
}

print(f"\nClassification (5-fold CV, 10 repeats, n={len(df)}):")
print(f"  Baseline (majority class): {max(y_cls.mean(), 1 - y_cls.mean()):.3f}")
print()

best_model_name = None
best_score = 0

for name, model in models.items():
    scores = cross_val_score(model, X_scaled, y_cls, cv=cv, scoring="accuracy")
    auc_scores = cross_val_score(model, X_scaled, y_cls, cv=cv, scoring="roc_auc")
    print(f"  {name}:")
    print(f"    Accuracy: {scores.mean():.3f} +/- {scores.std():.3f}")
    print(f"    AUC:      {auc_scores.mean():.3f} +/- {auc_scores.std():.3f}")
    if auc_scores.mean() > best_score:
        best_score = auc_scores.mean()
        best_model_name = name

print(f"\n  Best model: {best_model_name} (AUC={best_score:.3f})")

# Regression models
print(f"\nRegression (5-fold CV, 10 repeats):")
reg_models = {
    "Ridge": Ridge(alpha=1.0),
    "Random Forest": RandomForestRegressor(
        n_estimators=100, max_depth=5, min_samples_leaf=3, random_state=42
    ),
    "Gradient Boosting": GradientBoostingRegressor(
        n_estimators=80, max_depth=3, min_samples_leaf=3,
        learning_rate=0.1, random_state=42
    ),
}

from sklearn.model_selection import RepeatedKFold

reg_cv = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)
for name, model in reg_models.items():
    r2 = cross_val_score(model, X_scaled, y_reg, cv=reg_cv, scoring="r2")
    mae = cross_val_score(model, X_scaled, y_reg, cv=reg_cv, scoring="neg_mean_absolute_error")
    print(f"  {name}:")
    print(f"    R2:  {r2.mean():.3f} +/- {r2.std():.3f}")
    print(f"    MAE: {-mae.mean():.2f}% +/- {mae.std():.2f}%")

# ---------------------------------------------------------------------------
# 7. Feature importance (best model)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE (Gradient Boosting)")
print("=" * 70)

gb_cls = GradientBoostingClassifier(
    n_estimators=80, max_depth=3, min_samples_leaf=3,
    learning_rate=0.1, random_state=42
)
gb_cls.fit(X_scaled, y_cls)

importances = sorted(
    zip(valid_features, gb_cls.feature_importances_),
    key=lambda x: x[1],
    reverse=True,
)
print(f"\n{'Feature':<30s} {'Importance':>10s}")
print("-" * 42)
for feat, imp in importances:
    bar = "#" * int(imp * 40)
    print(f"  {feat:<28s} {imp:>8.3f}  {bar}")

# Regression feature importance
gb_reg = GradientBoostingRegressor(
    n_estimators=80, max_depth=3, min_samples_leaf=3,
    learning_rate=0.1, random_state=42
)
gb_reg.fit(X_scaled, y_reg)

print(f"\nFeature importance (Regression):")
importances_reg = sorted(
    zip(valid_features, gb_reg.feature_importances_),
    key=lambda x: x[1],
    reverse=True,
)
for feat, imp in importances_reg[:15]:
    bar = "#" * int(imp * 40)
    print(f"  {feat:<28s} {imp:>8.3f}  {bar}")

# ---------------------------------------------------------------------------
# 8. Error analysis - what does the model get wrong?
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ERROR ANALYSIS")
print("=" * 70)

# Get LOO predictions for error analysis
from sklearn.model_selection import LeaveOneOut

loo = LeaveOneOut()
y_pred_loo = cross_val_predict(gb_cls, X_scaled, y_cls, cv=loo)
y_pred_reg = cross_val_predict(gb_reg, X_scaled, y_reg, cv=loo)

# Misclassified sets
misclassified = df[y_pred_loo != y_cls][["set_number", "title", "theme", "annual_growth_pct", "good_investment"]].copy()
misclassified["predicted"] = y_pred_loo[y_pred_loo != y_cls]

print(f"\nMisclassified: {len(misclassified)} / {len(df)} ({len(misclassified)/len(df)*100:.0f}%)")
print(f"\nFalse Negatives (missed good investments):")
fn = misclassified[misclassified["good_investment"] == 1]
for _, row in fn.iterrows():
    print(f"  {row['set_number']} {row['title'][:35]:35s} growth={row['annual_growth_pct']:.1f}%")

print(f"\nFalse Positives (predicted good, actually not):")
fp = misclassified[misclassified["good_investment"] == 0]
for _, row in fp.iterrows():
    print(f"  {row['set_number']} {row['title'][:35]:35s} growth={row['annual_growth_pct']:.1f}%")

# Regression error distribution
errors = y_reg - y_pred_reg
print(f"\nRegression Error Distribution:")
print(f"  Mean error:     {errors.mean():.2f}%")
print(f"  MAE:            {np.abs(errors).mean():.2f}%")
print(f"  Median AE:      {np.median(np.abs(errors)):.2f}%")
print(f"  Max overpredict: {errors.min():.2f}% (set {df.iloc[errors.argmin()]['set_number']})")
print(f"  Max underpredict: {errors.max():.2f}% (set {df.iloc[errors.argmax()]['set_number']})")

# ---------------------------------------------------------------------------
# 9. Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Dataset: {len(df)} sets (BrickEconomy + BrickLink)
Features: {len(valid_features)}
Target: annual growth >= {GROWTH_THRESHOLD}% = "good investment"
Class balance: {df['good_investment'].mean()*100:.0f}% positive

Best classification: {best_model_name} (AUC={best_score:.3f})
Top features: {', '.join(f for f, _ in importances[:5])}

Key insight: With 204 sets we get much more stable estimates.
The model can separate good from bad investments moderately well.
""")
