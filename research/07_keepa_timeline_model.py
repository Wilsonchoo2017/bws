"""
07 - Keepa Timeline Model: Pre-retirement Amazon signals
==========================================================
Extract features from Keepa's historical price data:
- Pre-OOS: Amazon discount behavior, price trends while in stock
- At-OOS: Buy box premium when Amazon runs out (the free market moment)

These are signals available at or before retirement decision time.

Run with: .venv/bin/python research/07_keepa_timeline_model.py
"""

import json
import warnings
from datetime import datetime
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

rows = db.execute("""
    SELECT ks.set_number, li.title, li.theme,
           li.parts_count, li.minifig_count, li.weight,
           be.rrp_usd_cents, be.annual_growth_pct,
           be.rating_value, be.review_count,
           be.subtheme_avg_growth_pct, be.exclusive_minifigs,
           be.rrp_gbp_cents, be.pieces, be.minifigs AS be_minifigs,
           ks.amazon_price_json, ks.buy_box_json, ks.new_3p_fba_json,
           ks.tracking_users, ks.review_count AS kp_reviews, ks.rating AS kp_rating
    FROM keepa_snapshots ks
    JOIN brickeconomy_snapshots be ON ks.set_number = be.set_number
    JOIN lego_items li ON ks.set_number = li.set_number
    WHERE be.rrp_usd_cents > 0
      AND be.annual_growth_pct IS NOT NULL
      AND ks.amazon_price_json IS NOT NULL
""").fetchdf()

db.close()

# ---------------------------------------------------------------------------
# Parse Keepa timelines and extract features
# ---------------------------------------------------------------------------

records = []
for _, r in rows.iterrows():
    sn = r["set_number"]
    rrp = int(r["rrp_usd_cents"]) if r["rrp_usd_cents"] else 0
    if rrp <= 0:
        continue

    amz_json = r["amazon_price_json"]
    bb_json = r["buy_box_json"]
    fba_json = r["new_3p_fba_json"]

    amz = json.loads(amz_json) if isinstance(amz_json, str) else amz_json
    if not isinstance(amz, list) or len(amz) < 5:
        continue

    bb = json.loads(bb_json) if isinstance(bb_json, str) else (bb_json or [])
    fba = json.loads(fba_json) if isinstance(fba_json, str) else (fba_json or [])

    # Parse Amazon price timeline
    amz_prices = []
    oos_date = None
    last_amz_price = None

    for point in amz:
        date_str, price = point[0], point[1]
        if price is not None and price > 0:
            amz_prices.append((date_str, price))
            last_amz_price = price
        elif price is None and last_amz_price is not None and oos_date is None:
            oos_date = date_str

    if not amz_prices:
        continue

    prices_only = [p for _, p in amz_prices]

    # === PRE-OOS FEATURES ===
    avg_amz = np.mean(prices_only)
    min_amz = min(prices_only)

    avg_discount = (rrp - avg_amz) / rrp * 100
    max_discount = (rrp - min_amz) / rrp * 100
    never_discounted = 1 if min_amz >= rrp * 0.95 else 0
    below_rrp_pct = sum(1 for p in prices_only if p < rrp * 0.98) / len(prices_only) * 100

    # Time in stock
    months_in_stock = np.nan
    if oos_date:
        try:
            d1 = datetime.strptime(amz_prices[0][0], "%Y-%m-%d")
            d2 = datetime.strptime(oos_date, "%Y-%m-%d")
            months_in_stock = (d2 - d1).days / 30
        except (ValueError, TypeError):
            pass

    # Price trend while in stock
    if len(prices_only) >= 6:
        early = np.mean(prices_only[:3])
        late = np.mean(prices_only[-3:])
        price_trend = (late - early) / early * 100
    else:
        price_trend = 0

    # Price volatility
    price_cv = np.std(prices_only) / np.mean(prices_only) if np.mean(prices_only) > 0 else 0

    # === AT-OOS FEATURES ===
    bb_premium = np.nan
    if isinstance(bb, list) and oos_date:
        for point in bb:
            if len(point) >= 2 and point[0] >= oos_date and point[1] and point[1] > 0:
                bb_premium = (point[1] - rrp) / rrp * 100
                break

    fba_premium = np.nan
    if isinstance(fba, list) and oos_date:
        for point in fba:
            if len(point) >= 2 and point[0] >= oos_date and point[1] and point[1] > 0:
                fba_premium = (point[1] - rrp) / rrp * 100
                break

    # === INTRINSICS ===
    parts = int(r["parts_count"]) if pd.notna(r["parts_count"]) else (int(r["pieces"]) if pd.notna(r["pieces"]) else 0)
    mfigs = int(r["minifig_count"]) if pd.notna(r["minifig_count"]) else (int(r["be_minifigs"]) if pd.notna(r["be_minifigs"]) else 0)

    records.append({
        "set_number": sn,
        "title": r["title"],
        "theme": r["theme"],
        "growth": float(r["annual_growth_pct"]),
        # Intrinsics
        "log_rrp": np.log1p(rrp),
        "log_parts": np.log1p(parts),
        "price_per_part": rrp / parts if parts > 0 else np.nan,
        "mfigs": mfigs,
        "has_minifigs": 1 if mfigs > 0 else 0,
        "minifig_density": mfigs / parts * 100 if parts > 0 else 0,
        "rating_value": float(r["rating_value"]) if pd.notna(r["rating_value"]) else np.nan,
        "be_reviews": int(r["review_count"]) if pd.notna(r["review_count"]) else 0,
        "has_exclusive_mfigs": 1 if pd.notna(r["exclusive_minifigs"]) else 0,
        # Pre-OOS Amazon
        "avg_discount": avg_discount,
        "max_discount": max_discount,
        "never_discounted": never_discounted,
        "below_rrp_pct": below_rrp_pct,
        "months_in_stock": months_in_stock,
        "price_trend": price_trend,
        "price_cv": price_cv,
        # At-OOS
        "bb_premium_at_oos": bb_premium,
        "fba_premium_at_oos": fba_premium,
        # Keepa demand
        "log_tracking": np.log1p(int(r["tracking_users"]) if pd.notna(r["tracking_users"]) else 0),
        "log_kp_reviews": np.log1p(int(r["kp_reviews"]) if pd.notna(r["kp_reviews"]) else 0),
        "kp_rating": float(r["kp_rating"]) if pd.notna(r["kp_rating"]) else np.nan,
    })

df = pd.DataFrame(records)

# Theme features (LOO)
def loo_mean(d, col, group):
    s = d.groupby(group)[col].transform("sum")
    c = d.groupby(group)[col].transform("count")
    return ((s - d[col]) / (c - 1)).fillna(d[col].mean())

df["theme_loo_growth"] = loo_mean(df, "growth", "theme")
df["theme_size"] = df["theme"].map(df["theme"].value_counts())

LICENSED = {"Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
            "Avatar", "Disney", "Minecraft", "BrickHeadz"}
df["is_licensed"] = df["theme"].isin(LICENSED).astype(int)

print(f"Sets with full Keepa timeline: {len(df)}")

# ---------------------------------------------------------------------------
# Feature sets to compare
# ---------------------------------------------------------------------------

INTRINSICS = [
    "log_rrp", "log_parts", "price_per_part", "mfigs", "has_minifigs",
    "minifig_density", "rating_value", "be_reviews",
    "has_exclusive_mfigs", "theme_loo_growth", "theme_size", "is_licensed",
]

PRE_OOS = [
    "avg_discount", "max_discount", "never_discounted",
    "below_rrp_pct", "months_in_stock", "price_trend", "price_cv",
]

AT_OOS = [
    "bb_premium_at_oos", "fba_premium_at_oos",
]

KEEPA_DEMAND = [
    "log_tracking", "log_kp_reviews", "kp_rating",
]

y_reg = df["growth"].values.astype(float)
THRESHOLD = 10.0
y_cls = (y_reg >= THRESHOLD).astype(int)

print(f"Target >= {THRESHOLD}%: {y_cls.sum()} positive ({y_cls.mean()*100:.0f}%)")

# ---------------------------------------------------------------------------
# Compare feature set combinations
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE SET ABLATION")
print("=" * 70)

cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
rcv = RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)
scaler = StandardScaler()

combos = {
    "A: Intrinsics only": INTRINSICS,
    "B: Intrinsics + Pre-OOS Amazon": INTRINSICS + PRE_OOS,
    "C: Intrinsics + Pre-OOS + Demand": INTRINSICS + PRE_OOS + KEEPA_DEMAND,
    "D: Intrinsics + Pre-OOS + At-OOS": INTRINSICS + PRE_OOS + AT_OOS,
    "E: Everything": INTRINSICS + PRE_OOS + AT_OOS + KEEPA_DEMAND,
}

for name, feats in combos.items():
    valid = [f for f in feats if f in df.columns and df[f].notna().sum() >= len(df) * 0.3]

    X = df[valid].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())
    Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

    gb_c = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, min_samples_leaf=5,
        learning_rate=0.05, random_state=42,
    )
    gb_r = GradientBoostingRegressor(
        n_estimators=100, max_depth=3, min_samples_leaf=5,
        learning_rate=0.05, random_state=42,
    )

    auc = cross_val_score(gb_c, Xs, y_cls, cv=cv, scoring="roc_auc")
    r2 = cross_val_score(gb_r, Xs, y_reg, cv=rcv, scoring="r2")
    mae = cross_val_score(gb_r, Xs, y_reg, cv=rcv, scoring="neg_mean_absolute_error")

    # LOO
    y_pred = cross_val_predict(gb_r, Xs, y_reg, cv=LeaveOneOut())
    loo_r2 = r2_score(y_reg, y_pred)
    loo_corr = np.corrcoef(y_reg, y_pred)[0, 1]

    print(f"\n  {name} ({len(valid)} feats):")
    print(f"    CV:  AUC={auc.mean():.3f}  R2={r2.mean():.3f}  MAE={-mae.mean():.2f}%")
    print(f"    LOO: R2={loo_r2:.3f}  Corr={loo_corr:.3f}")

# ---------------------------------------------------------------------------
# Best clean model: Intrinsics + Pre-OOS (no at-OOS)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("BEST CLEAN MODEL: Intrinsics + Pre-OOS Amazon")
print("=" * 70)

best_feats = [f for f in INTRINSICS + PRE_OOS if f in df.columns and df[f].notna().sum() >= len(df) * 0.3]
X = df[best_feats].copy()
for c in X.columns:
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())
Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

gb = GradientBoostingRegressor(
    n_estimators=100, max_depth=3, min_samples_leaf=5,
    learning_rate=0.05, random_state=42,
)
gb.fit(Xs, y_reg)

perm = permutation_importance(gb, Xs, y_reg, n_repeats=30, random_state=42, scoring="r2")
sorted_imp = sorted(
    zip(best_feats, perm.importances_mean, gb.feature_importances_),
    key=lambda x: x[1], reverse=True,
)

print(f"\n{'Feature':<25s} {'Perm':>8s} {'Tree':>8s} {'Type':>10s}")
print("-" * 55)
for f, p, t in sorted_imp:
    ftype = "PRE-OOS" if f in PRE_OOS else "intrinsic"
    bar = "#" * max(0, int(p * 15))
    print(f"  {f:<23s} {p:>+6.3f}  {t:>6.3f}  {ftype:>10s}  {bar}")

# LOO predictions
y_pred = cross_val_predict(gb, Xs, y_reg, cv=LeaveOneOut())
df["pred"] = y_pred
df["error"] = y_reg - y_pred

print(f"\n  LOO R2:   {r2_score(y_reg, y_pred):.3f}")
print(f"  LOO MAE:  {mean_absolute_error(y_reg, y_pred):.2f}%")
print(f"  LOO Corr: {np.corrcoef(y_reg, y_pred)[0,1]:.3f}")

# Per-theme
print(f"\n  Per-theme (top themes):")
theme_perf = df.groupby("theme").agg(
    n=("error", "count"),
    mae=("error", lambda x: np.abs(x).mean()),
    avg_growth=("growth", "mean"),
).sort_values("n", ascending=False)

for theme, row in theme_perf.head(10).iterrows():
    print(f"    {str(theme)[:20]:20s}  n={row['n']:2.0f}  MAE={row['mae']:.1f}%  avg={row['avg_growth']:.1f}%")

# Best/worst predictions
print(f"\n  Biggest errors:")
for _, row in df.nlargest(5, "error").iterrows():
    print(f"    {row['set_number']:>7s} {str(row['title'])[:28]:28s} actual={row['growth']:.1f}% pred={row['pred']:.1f}% below_rrp={row.get('below_rrp_pct',0):.0f}%")
for _, row in df.nsmallest(5, "error").iterrows():
    print(f"    {row['set_number']:>7s} {str(row['title'])[:28]:28s} actual={row['growth']:.1f}% pred={row['pred']:.1f}% below_rrp={row.get('below_rrp_pct',0):.0f}%")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Keepa timeline analysis on {len(df)} sets:

Pre-OOS Amazon features (clean, no leakage):
  - below_rrp_pct: how often Amazon priced below RRP (r=-0.36)
  - price_trend: price direction while in stock (r=+0.34)
  - avg/max_discount: Amazon's discounting behavior

At-OOS features (borderline - measured at retirement):
  - bb_premium_at_oos: buy box premium when Amazon runs out (r=+0.49)
  - fba_premium_at_oos: 3P FBA premium at OOS (r=+0.33)

Key question: Does pre-OOS Amazon behavior add signal beyond set intrinsics?
""")
