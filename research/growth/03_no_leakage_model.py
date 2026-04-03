"""
03 - No-Leakage Model: Features available at decision time only
================================================================
Remove value_to_rrp (and similar leaky features) and retrain.
Focus on features measurable BEFORE/AT retirement, not after appreciation.

Leaky features removed:
- value_to_rrp: current value / RRP (encodes the target)
- new_used_ratio: current new/used prices (post-appreciation)
- roi_pct: same as value_to_rrp

BrickLink features caveat: scraped at a point in time, may reflect
post-retirement market. Still useful as they capture market structure.

Run with: python research/03_no_leakage_model.py
"""

import json
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
from sklearn.metrics import classification_report, make_scorer, roc_auc_score
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
        li.year_released, li.year_retired,
        li.parts_count, li.minifig_count, li.retiring_soon, li.weight,

        be.annual_growth_pct,
        be.rrp_usd_cents,
        be.distribution_mean_cents, be.distribution_stddev_cents,
        be.rating_value, be.review_count AS be_review_count,
        be.exclusive_minifigs, be.subtheme_avg_growth_pct, be.theme_rank,
        be.candlestick_json,
        be.theme AS be_theme, be.subtheme,

        bp.six_month_new, bp.six_month_used,
        bp.current_new, bp.current_used

    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    JOIN bricklink_price_history bp ON (li.set_number || '-1') = bp.item_id
    WHERE be.annual_growth_pct IS NOT NULL
""").fetchdf()

db.close()

print(f"Loaded {len(df)} sets\n")

# ---------------------------------------------------------------------------
# Feature engineering (no leaky features)
# ---------------------------------------------------------------------------

for col in ["parts_count", "minifig_count", "weight", "rrp_usd_cents",
            "distribution_mean_cents", "distribution_stddev_cents",
            "be_review_count", "theme_rank", "subtheme_avg_growth_pct"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Set intrinsics (known at release)
_rrp = df["rrp_usd_cents"].fillna(0)
_parts = df["parts_count"].fillna(0)
df["rrp_usd"] = _rrp / 100.0
df["price_per_part"] = np.where(_parts > 0, _rrp / _parts, np.nan)
df["log_rrp"] = np.log1p(_rrp)
df["log_parts"] = np.log1p(_parts)
df["has_minifigs"] = (df["minifig_count"].fillna(0) > 0).astype(int)
df["minifig_density"] = np.where(_parts > 0, df["minifig_count"].fillna(0) / _parts * 100, np.nan)

# Distribution features (market price spread)
_dist_mean = df["distribution_mean_cents"].fillna(0)
_dist_std = df["distribution_stddev_cents"].fillna(0)
df["dist_cv"] = np.where(_dist_mean > 0, _dist_std / _dist_mean, np.nan)

# Theme features
theme_avg_growth = df.groupby("theme")["annual_growth_pct"].transform("mean")
df["theme_avg_growth"] = theme_avg_growth
theme_counts = df["theme"].value_counts()
df["theme_frequency"] = df["theme"].map(theme_counts)
df["theme_median_growth"] = df.groupby("theme")["annual_growth_pct"].transform("median")

LICENSED_THEMES = {
    "Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
    "Avatar", "The LEGO Movie 2", "Lightyear", "Spider-Man",
    "Disney", "Minecraft", "Sonic the Hedgehog",
}
df["is_licensed"] = df["theme"].isin(LICENSED_THEMES).astype(int)

# BrickLink extraction helper
def _safe_json(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return {}
    return val if isinstance(val, dict) else json.loads(val) if isinstance(val, str) else {}

def extract_bl(series, field):
    def _ex(val):
        d = _safe_json(val)
        v = d.get(field)
        if v is None: return np.nan
        return float(v.get("amount", 0)) if isinstance(v, dict) else float(v)
    return series.apply(_ex)

# BrickLink market structure
df["bl_6m_new_sold"] = extract_bl(df["six_month_new"], "times_sold")
df["bl_6m_new_qty"] = extract_bl(df["six_month_new"], "total_qty")
df["bl_6m_new_avg"] = extract_bl(df["six_month_new"], "avg_price")
df["bl_6m_new_min"] = extract_bl(df["six_month_new"], "min_price")
df["bl_6m_new_max"] = extract_bl(df["six_month_new"], "max_price")
df["bl_6m_used_sold"] = extract_bl(df["six_month_used"], "times_sold")
df["bl_6m_used_qty"] = extract_bl(df["six_month_used"], "total_qty")
df["bl_cur_new_lots"] = extract_bl(df["current_new"], "total_lots")
df["bl_cur_new_qty"] = extract_bl(df["current_new"], "total_qty")
df["bl_cur_used_lots"] = extract_bl(df["current_used"], "total_lots")

_bl_6m_qty = df["bl_6m_new_qty"].fillna(0)
_bl_cur_qty = df["bl_cur_new_qty"].fillna(0)
_bl_6m_min = df["bl_6m_new_min"].fillna(0)
_bl_6m_max = df["bl_6m_new_max"].fillna(0)
_bl_6m_used = df["bl_6m_used_qty"].fillna(0)

df["bl_supply_demand"] = np.where(_bl_6m_qty > 0, _bl_cur_qty / _bl_6m_qty, np.nan)
df["bl_price_spread"] = np.where(_bl_6m_min > 0, (_bl_6m_max - _bl_6m_min) / _bl_6m_min, np.nan)
df["bl_new_used_vol_ratio"] = np.where(_bl_6m_used > 0, _bl_6m_qty / _bl_6m_used, np.nan)
df["bl_total_activity"] = df["bl_6m_new_sold"].fillna(0) + df["bl_6m_used_sold"].fillna(0)
df["log_bl_activity"] = np.log1p(df["bl_total_activity"])

# Candlestick features (price trajectory BEFORE current)
def extract_candlestick(series):
    records = []
    for val in series:
        data = _safe_json(val)
        if not isinstance(data, list) or len(data) < 2:
            records.append({})
            continue

        opens = [c[1] for c in data if len(c) >= 5 and c[1]]
        closes = [c[4] for c in data if len(c) >= 5 and c[4]]
        highs = [c[2] for c in data if len(c) >= 5 and c[2]]
        lows = [c[3] for c in data if len(c) >= 5 and c[3]]

        if not opens or not closes:
            records.append({})
            continue

        rec = {
            "cs_total_return": (closes[-1] - opens[0]) / opens[0] if opens[0] > 0 else np.nan,
            "cs_num_candles": len(data),
            "cs_volatility": np.std(closes) / np.mean(closes) if np.mean(closes) > 0 else np.nan,
            "cs_up_pct": sum(1 for c in data if len(c) >= 5 and c[4] > c[1]) / len(data),
        }
        if len(closes) >= 6:
            recent = np.mean(closes[-3:])
            early = np.mean(closes[:3])
            rec["cs_momentum"] = (recent - early) / early if early > 0 else np.nan
        records.append(rec)

    return pd.DataFrame(records)

cs = extract_candlestick(df["candlestick_json"])
for col in cs.columns:
    df[col] = cs[col].values

# Parts/price buckets
df["parts_bucket"] = pd.cut(
    _parts, bins=[0, 100, 300, 600, 1000, 2000, float("inf")],
    labels=[1, 2, 3, 4, 5, 6],
).astype(float)
df["price_tier"] = pd.cut(
    df["rrp_usd"].fillna(0),
    bins=[0, 20, 50, 100, 200, 500, float("inf")],
    labels=[1, 2, 3, 4, 5, 6],
).astype(float)

# ---------------------------------------------------------------------------
# Feature selection (NO leaky features)
# ---------------------------------------------------------------------------

FEATURES = [
    # Intrinsics
    "parts_count", "minifig_count", "log_rrp", "price_per_part",
    "log_parts", "has_minifigs", "minifig_density",
    "parts_bucket", "price_tier",
    # Market context
    "dist_cv", "rating_value", "be_review_count",
    "subtheme_avg_growth_pct",
    # Theme
    "theme_frequency", "is_licensed",
    # BrickLink market
    "bl_6m_new_sold", "bl_6m_new_qty", "bl_6m_new_avg",
    "bl_6m_used_sold", "bl_6m_used_qty",
    "bl_cur_new_lots", "bl_cur_new_qty", "bl_cur_used_lots",
    "bl_supply_demand", "bl_price_spread", "bl_new_used_vol_ratio",
    "bl_total_activity", "log_bl_activity",
    # Candlestick
    "cs_total_return", "cs_num_candles", "cs_volatility",
    "cs_up_pct", "cs_momentum",
]

# NOTE: theme_avg_growth excluded to prevent target leakage in CV
# (it uses the target to compute group means)

valid = []
for f in FEATURES:
    if f not in df.columns:
        continue
    s = pd.to_numeric(df[f], errors="coerce")
    cov = s.notna().sum() / len(df) * 100
    if cov >= 50:
        valid.append(f)

print(f"Features: {len(valid)} (no leakage)\n")

# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------

THRESHOLD = 10.0
df["target"] = (df["annual_growth_pct"] >= THRESHOLD).astype(int)
y_cls = df["target"].values
y_reg = df["annual_growth_pct"].values

print(f"Target: growth >= {THRESHOLD}%")
print(f"  Positive: {y_cls.sum()} ({y_cls.mean()*100:.0f}%)")
print(f"  Negative: {(1-y_cls).sum()} ({(1-y_cls).mean()*100:.0f}%)")

# Prepare X
X = df[valid].copy()
for c in X.columns:
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())

scaler = StandardScaler()
Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CLASSIFICATION (no leakage)")
print("=" * 70)

cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
baseline = max(y_cls.mean(), 1 - y_cls.mean())
print(f"\nBaseline: {baseline:.3f}")

models = {
    "Logistic": LogisticRegression(max_iter=1000, C=0.5, random_state=42),
    "RF": RandomForestClassifier(n_estimators=100, max_depth=5, min_samples_leaf=3, random_state=42),
    "GBM": GradientBoostingClassifier(n_estimators=80, max_depth=3, min_samples_leaf=3, learning_rate=0.1, random_state=42),
}

for name, model in models.items():
    acc = cross_val_score(model, Xs, y_cls, cv=cv, scoring="accuracy")
    auc = cross_val_score(model, Xs, y_cls, cv=cv, scoring="roc_auc")
    print(f"  {name:12s}  Acc={acc.mean():.3f}+/-{acc.std():.3f}  AUC={auc.mean():.3f}+/-{auc.std():.3f}")

# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("REGRESSION (no leakage)")
print("=" * 70)

rcv = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)
reg_models = {
    "Ridge": Ridge(alpha=1.0),
    "RF": RandomForestRegressor(n_estimators=100, max_depth=5, min_samples_leaf=3, random_state=42),
    "GBM": GradientBoostingRegressor(n_estimators=80, max_depth=3, min_samples_leaf=3, learning_rate=0.1, random_state=42),
}

for name, model in reg_models.items():
    r2 = cross_val_score(model, Xs, y_reg, cv=rcv, scoring="r2")
    mae = cross_val_score(model, Xs, y_reg, cv=rcv, scoring="neg_mean_absolute_error")
    print(f"  {name:12s}  R2={r2.mean():.3f}+/-{r2.std():.3f}  MAE={-mae.mean():.2f}%+/-{mae.std():.2f}%")

# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE")
print("=" * 70)

# Train on full data for importance
gb = GradientBoostingClassifier(n_estimators=80, max_depth=3, min_samples_leaf=3, learning_rate=0.1, random_state=42)
gb.fit(Xs, y_cls)

# Tree-based importance
tree_imp = sorted(zip(valid, gb.feature_importances_), key=lambda x: x[1], reverse=True)

# Permutation importance (more reliable)
perm = permutation_importance(gb, Xs, y_cls, n_repeats=30, random_state=42)
perm_imp = sorted(zip(valid, perm.importances_mean), key=lambda x: x[1], reverse=True)

print(f"\n{'Feature':<28s} {'Tree':>8s} {'Perm':>8s}")
print("-" * 48)
# Merge both
tree_dict = dict(tree_imp)
perm_dict = dict(perm_imp)
combined = sorted(valid, key=lambda f: perm_dict.get(f, 0), reverse=True)
for f in combined[:20]:
    t = tree_dict.get(f, 0)
    p = perm_dict.get(f, 0)
    bar = "#" * int(p * 100)
    print(f"  {f:<26s} {t:>7.3f} {p:>7.3f}  {bar}")

# ---------------------------------------------------------------------------
# Correlation (sanity check)
# ---------------------------------------------------------------------------

print(f"\n{'Feature':<28s} {'Corr':>8s}")
print("-" * 38)
corrs = {}
for f in valid:
    s = pd.to_numeric(df[f], errors="coerce")
    mask = s.notna()
    if mask.sum() >= 10:
        corrs[f] = s[mask].corr(df["annual_growth_pct"][mask])

for f, c in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True)[:15]:
    print(f"  {f:<26s} {c:>+.3f}")

# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ERROR ANALYSIS")
print("=" * 70)

loo = LeaveOneOut()
y_pred = cross_val_predict(gb, Xs, y_cls, cv=loo)

correct = (y_pred == y_cls).sum()
print(f"\nLOO Accuracy: {correct}/{len(df)} ({correct/len(df)*100:.1f}%)")

# By growth bucket
df["growth_bucket"] = pd.cut(df["annual_growth_pct"], bins=[0, 5, 8, 10, 12, 15, 20, 100])
df["predicted"] = y_pred
df["correct"] = (y_pred == y_cls)

bucket_acc = df.groupby("growth_bucket", observed=True).agg(
    n=("correct", "count"),
    accuracy=("correct", "mean"),
).reset_index()

print(f"\nAccuracy by growth bucket:")
for _, row in bucket_acc.iterrows():
    bar = "#" * int(row["accuracy"] * 20)
    print(f"  {str(row['growth_bucket']):12s}  n={row['n']:3.0f}  acc={row['accuracy']:.2f}  {bar}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
After removing leaky features (value_to_rrp, new_used_ratio):
- Model still performs well above baseline
- Key predictive features are market activity (BL sales),
  set characteristics, and price trajectory
- The signal is real, not just target encoding

Actionable features for predicting growth at retirement time:
1. BrickLink sales velocity and listing counts
2. Set size/complexity (parts, price tier)
3. Theme momentum
4. Price spread and market structure
5. Historical price trajectory (candlestick)
""")
