"""Keepa 3P spread analysis — BrickTalk's exact signal.

BrickTalk checks: "lowest 3P sale $29, MSRP $23 = 20% premium"
They want the FLOOR of 3P to be above RRP — proof of demand before retirement.

This script tests:
1. Is the 3P FBA minimum above RRP? (floor above retail)
2. What's the spread between Amazon 1P and 3P FBA? (market makers pricing in demand)
3. Is the spread widening over time? (momentum signal)
4. How does the 3P range (max-min) relate to growth?

Run: python -m scripts.keepa_3p_spread_analysis
"""
from __future__ import annotations

import json
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

print("=" * 70)
print("KEEPA 3P SPREAD ANALYSIS")
print("BrickTalk signal: 3P floor above retail = proven demand")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.feature_selection import select_features
from services.ml.pg_queries import load_growth_training_data
from sqlalchemy import text

engine = get_engine()
df_raw = load_growth_training_data(engine)
y_all = df_raw["annual_growth_pct"].values.astype(float)
year_retired = np.asarray(
    pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
)

df_feat, _, _ = engineer_intrinsic_features(df_raw, training_target=pd.Series(y_all))
t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
X_raw = df_feat[t1_candidates].copy()
for c in X_raw.columns:
    X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
t1_features = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
if len(t1_features) < 5:
    t1_features = t1_candidates

finite = np.isfinite(year_retired)
groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
groups[finite] = year_retired[finite].astype(int)

# Load Keepa
with engine.connect() as conn:
    keepa_df = pd.read_sql(text("""
        SELECT ks.set_number, ks.amazon_price_json, ks.new_3p_fba_json,
               ks.new_3p_fbm_json, ks.buy_box_json
        FROM keepa_snapshots ks
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM keepa_snapshots GROUP BY set_number
        ) l ON ks.set_number = l.set_number AND ks.scraped_at = l.latest
        WHERE ks.amazon_price_json IS NOT NULL
    """), conn)

rrp_lookup = dict(zip(
    df_raw["set_number"],
    pd.to_numeric(df_raw["rrp_usd_cents"], errors="coerce").fillna(0),
))

# Retirement dates
retire_dt = pd.to_datetime(df_raw.get("retired_date"), errors="coerce")
yr_ret = pd.to_numeric(df_raw.get("year_retired"), errors="coerce")
retire_dt_approx = pd.to_datetime(
    yr_ret.dropna().astype(int).astype(str) + "-07-01", errors="coerce"
).reindex(df_raw.index)
retire_dt = retire_dt.fillna(retire_dt_approx)
retire_lookup = dict(zip(df_raw["set_number"], retire_dt))

# Set name lookup for examples
name_lookup = dict(zip(df_raw["set_number"], df_raw.get("set_name", df_raw["set_number"])))

print(f"\nData: {len(df_raw)} sets, {len(keepa_df)} Keepa snapshots")


def parse_timeline(raw):
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Extract 3P spread features
# ---------------------------------------------------------------------------

spread_features = {}

for _, kr in keepa_df.iterrows():
    sn = kr["set_number"]
    rrp = rrp_lookup.get(sn, 0)
    ret_date = retire_lookup.get(sn)
    if rrp <= 0 or pd.isna(ret_date):
        continue

    cutoff = ret_date.strftime("%Y-%m")
    rec = {}

    # Parse timelines with cutoff
    def get_prices(json_col, cutoff_str):
        tl = parse_timeline(kr[json_col])
        prices = []
        for p in tl:
            if len(p) < 2:
                continue
            if isinstance(p[0], str) and p[0][:7] > cutoff_str:
                break
            if p[1] is not None and p[1] > 0:
                prices.append(float(p[1]))
        return prices

    amz_prices = get_prices("amazon_price_json", cutoff)
    fba_prices = get_prices("new_3p_fba_json", cutoff)
    fbm_prices = get_prices("new_3p_fbm_json", cutoff)
    bb_prices = get_prices("buy_box_json", cutoff)

    if not fba_prices or len(fba_prices) < 3:
        continue

    # ---- BrickTalk's exact signals ----

    # 1. 3P FBA floor vs RRP: "lowest 3P sale $29 vs MSRP $23"
    fba_min = min(fba_prices)
    fba_max = max(fba_prices)
    rec["spread_fba_floor_vs_rrp"] = (fba_min - rrp) / rrp * 100
    rec["spread_fba_floor_above_rrp"] = 1.0 if fba_min > rrp * 0.98 else 0.0

    # 2. 3P FBA last price vs RRP (most recent signal)
    rec["spread_fba_last_vs_rrp"] = (fba_prices[-1] - rrp) / rrp * 100
    rec["spread_fba_last_above_rrp"] = 1.0 if fba_prices[-1] > rrp * 0.98 else 0.0

    # 3. % of time 3P FBA was above RRP
    pct_above = sum(1 for p in fba_prices if p > rrp * 0.98) / len(fba_prices) * 100
    rec["spread_fba_pct_above_rrp"] = pct_above

    # 4. 3P range (spread between min and max) — how volatile is the 3P market?
    rec["spread_fba_range_pct"] = (fba_max - fba_min) / rrp * 100

    # 5. Amazon vs 3P spread
    if amz_prices and len(amz_prices) >= 3:
        amz_mean = np.mean(amz_prices)
        fba_mean = np.mean(fba_prices)

        # Gap: 3P FBA average minus Amazon average (positive = 3P charging more)
        rec["spread_fba_minus_amz"] = (fba_mean - amz_mean) / rrp * 100

        # Is Amazon discounting while 3P holds firm? (strong demand signal)
        amz_discount = (rrp - amz_mean) / rrp * 100  # positive = Amazon below RRP
        fba_premium = (fba_mean - rrp) / rrp * 100    # positive = FBA above RRP
        rec["spread_amz_disc_fba_prem"] = fba_premium - amz_discount  # divergence

        # Last Amazon price vs last FBA price
        rec["spread_last_fba_minus_amz"] = (fba_prices[-1] - amz_prices[-1]) / rrp * 100

    # 6. FBM spread (merchant fulfilled — often higher = market believes in value)
    if fbm_prices and len(fbm_prices) >= 3:
        fbm_min = min(fbm_prices)
        rec["spread_fbm_floor_vs_rrp"] = (fbm_min - rrp) / rrp * 100
        rec["spread_fbm_floor_above_rrp"] = 1.0 if fbm_min > rrp * 0.98 else 0.0
        rec["spread_fbm_mean_vs_rrp"] = (np.mean(fbm_prices) - rrp) / rrp * 100

    # 7. Buy box spread
    if bb_prices and len(bb_prices) >= 3:
        bb_max = max(bb_prices)
        rec["spread_bb_max_vs_rrp"] = (bb_max - rrp) / rrp * 100
        rec["spread_bb_last_vs_rrp"] = (bb_prices[-1] - rrp) / rrp * 100

    # 8. Trend: is 3P FBA price rising in last half of history?
    if len(fba_prices) >= 6:
        half = len(fba_prices) // 2
        early_mean = np.mean(fba_prices[:half])
        late_mean = np.mean(fba_prices[half:])
        rec["spread_fba_trend"] = (late_mean - early_mean) / rrp * 100

        # Last third vs first third (stronger trend signal)
        third = len(fba_prices) // 3
        if third >= 2:
            rec["spread_fba_late_vs_early"] = (
                np.mean(fba_prices[-third:]) - np.mean(fba_prices[:third])
            ) / rrp * 100

    # 9. Convergence: are Amazon and 3P converging? (bullish when 3P drops to meet Amazon rising)
    if amz_prices and len(amz_prices) >= 6 and len(fba_prices) >= 6:
        # Align by taking same number of points
        n = min(len(amz_prices), len(fba_prices))
        half_n = n // 2
        early_spread = np.mean(fba_prices[:half_n]) - np.mean(amz_prices[:half_n])
        late_spread = np.mean(fba_prices[-half_n:]) - np.mean(amz_prices[-half_n:])
        rec["spread_convergence"] = (late_spread - early_spread) / rrp * 100
        # Positive = spread widening (3P pulling away = bullish)
        # Negative = spread narrowing (converging)

    # 10. "Never below RRP" for 3P — strongest signal
    rec["spread_fba_never_below_rrp"] = 1.0 if all(p >= rrp * 0.95 for p in fba_prices) else 0.0

    spread_features[sn] = rec

print(f"Extracted spread features for {len(spread_features)} sets")

all_feat_names = sorted(set().union(*(r.keys() for r in spread_features.values())))
print(f"Features: {len(all_feat_names)}")


# ---------------------------------------------------------------------------
# Part 1: Correlations
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRELATIONS WITH GROWTH")
print("=" * 70)

keepa_mask = df_raw["set_number"].isin(spread_features)
for feat in all_feat_names:
    df_feat[feat] = df_raw["set_number"].map(
        lambda sn, f=feat: spread_features.get(sn, {}).get(f, np.nan)
    )

y_kp = y_all[keepa_mask.values]
correlations = []
for feat in all_feat_names:
    vals = df_feat.loc[keepa_mask, feat].values.astype(float)
    valid = np.isfinite(vals) & np.isfinite(y_kp)
    n_valid = valid.sum()
    if n_valid >= 30:
        corr = np.corrcoef(vals[valid], y_kp[valid])[0, 1]
        correlations.append((feat, corr, n_valid))

correlations.sort(key=lambda x: abs(x[1]), reverse=True)

print(f"\n{'Feature':<35} {'Corr':>8} {'n':>6}")
print("-" * 52)
for feat, corr, n in correlations:
    marker = " ***" if abs(corr) >= 0.15 else " **" if abs(corr) >= 0.10 else " *" if abs(corr) >= 0.05 else ""
    print(f"  {feat:<33} {corr:+.3f}  {n:>5}{marker}")


# ---------------------------------------------------------------------------
# Part 2: BrickTalk-style group analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("BRICKTALK SIGNAL: '3P FLOOR ABOVE RETAIL'")
print("=" * 70)

floor_feat = "spread_fba_floor_above_rrp"
floor_vals = df_feat.loc[keepa_mask, floor_feat].values.astype(float)
valid_floor = np.isfinite(floor_vals)

if valid_floor.sum() >= 20:
    above = floor_vals[valid_floor] == 1.0
    below = ~above

    y_floor = y_kp[valid_floor]
    print(f"\n  3P FBA floor ABOVE RRP (never sold below retail):")
    print(f"    n={above.sum()}, avg growth={y_floor[above].mean():.1f}%, median={np.median(y_floor[above]):.1f}%")
    print(f"  3P FBA floor BELOW RRP (was sold below retail):")
    print(f"    n={below.sum()}, avg growth={y_floor[below].mean():.1f}%, median={np.median(y_floor[below]):.1f}%")
    print(f"  Delta: {y_floor[above].mean() - y_floor[below].mean():+.1f}% (mean), {np.median(y_floor[above]) - np.median(y_floor[below]):+.1f}% (median)")

# Never below RRP
never_feat = "spread_fba_never_below_rrp"
never_vals = df_feat.loc[keepa_mask, never_feat].values.astype(float)
valid_never = np.isfinite(never_vals)

if valid_never.sum() >= 20:
    never_above = never_vals[valid_never] == 1.0
    y_never = y_kp[valid_never]
    print(f"\n  3P FBA NEVER below 95% RRP (entire history):")
    print(f"    n={never_above.sum()}, avg growth={y_never[never_above].mean():.1f}%, median={np.median(y_never[never_above]):.1f}%")
    print(f"  3P FBA was below 95% RRP at some point:")
    print(f"    n={(~never_above).sum()}, avg growth={y_never[~never_above].mean():.1f}%, median={np.median(y_never[~never_above]):.1f}%")

print("\n" + "=" * 70)
print("BRICKTALK SIGNAL: 'AMAZON DISCOUNTING BUT 3P HOLDS'")
print("=" * 70)

div_feat = "spread_amz_disc_fba_prem"
div_vals = df_feat.loc[keepa_mask, div_feat].values.astype(float)
valid_div = np.isfinite(div_vals)

if valid_div.sum() >= 20:
    div_data = div_vals[valid_div]
    y_div = y_kp[valid_div]

    # Quartile analysis
    print(f"\n  Amazon-discounting-while-3P-holds divergence (n={valid_div.sum()}):")
    for q_lo, q_hi, label in [(0, 25, "Q1 (worst: both discounting)"),
                               (25, 50, "Q2"), (50, 75, "Q3"),
                               (75, 100, "Q4 (best: Amazon cheap, 3P premium)")]:
        lo = np.percentile(div_data, q_lo)
        hi = np.percentile(div_data, q_hi)
        mask_q = (div_data >= lo) & (div_data < hi if q_hi < 100 else div_data <= hi)
        if mask_q.sum() >= 5:
            print(f"    {label}: n={mask_q.sum()}, range=[{lo:+.0f}%,{hi:+.0f}%], avg growth={y_div[mask_q].mean():.1f}%")


# ---------------------------------------------------------------------------
# Part 3: Show concrete examples
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TOP EXAMPLES: 3P Floor Above RRP (sorted by growth)")
print("=" * 70)

examples = []
for i, row in df_raw.iterrows():
    sn = row["set_number"]
    if sn in spread_features and spread_features[sn].get("spread_fba_floor_above_rrp") == 1.0:
        rrp_usd = rrp_lookup.get(sn, 0) / 100
        fba_floor = spread_features[sn].get("spread_fba_floor_vs_rrp", 0)
        examples.append((sn, name_lookup.get(sn, sn), rrp_usd, fba_floor, y_all[i]))

examples.sort(key=lambda x: x[4], reverse=True)
print(f"\n{'Set':<10} {'Name':<35} {'RRP':>6} {'FBA Floor':>10} {'Growth':>7}")
print("-" * 72)
for sn, name, rrp_usd, fba_floor, growth in examples[:15]:
    print(f"  {sn:<8} {name[:33]:<35} ${rrp_usd:>5.0f} {fba_floor:>+8.0f}%  {growth:>+5.1f}%")
print(f"\n  ... {len(examples)} total sets where 3P floor >= RRP")


# ---------------------------------------------------------------------------
# Part 4: CV test
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CV TEST: T1 + SPREAD FEATURES")
print("=" * 70)

import lightgbm as lgb
from services.ml.growth.model_selection import MONOTONIC_MAP


def cv_score(X_vals, y, groups, name="", monotonic=None):
    n_unique = len(set(groups))
    n_splits = min(5, n_unique)
    splitter = GroupKFold(n_splits=n_splits)
    r2s, maes = [], []
    for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
        X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]
        lo, hi = np.percentile(y_tr, [1, 99])
        y_tr = np.clip(y_tr, lo, hi)
        pt = PowerTransformer(method="yeo-johnson", standardize=False)
        y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)
        model = lgb.LGBMRegressor(
            n_estimators=300, max_depth=8, num_leaves=41,
            learning_rate=0.039, feature_fraction=0.93, subsample=0.79,
            objective="huber", alpha=1.0, verbosity=-1, random_state=42, n_jobs=1,
        )
        if monotonic:
            model.set_params(monotone_constraints=monotonic)
        model.fit(X_tr_s, y_tr_t)
        y_pred = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()
        ss_res = np.sum((y_va - y_pred) ** 2)
        ss_tot = np.sum((y_va - y_va.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        r2s.append(r2)
        maes.append(mean_absolute_error(y_va, y_pred))
    return {"name": name, "r2": np.mean(r2s), "std": np.std(r2s), "mae": np.mean(maes)}


keepa_idx = np.where(keepa_mask.values)[0]
y_kp_cv = y_all[keepa_idx]
groups_kp = groups[keepa_idx]

X_t1_kp = X_raw[t1_features].fillna(X_raw[t1_features].median()).iloc[keepa_idx].values
mono_t1 = [MONOTONIC_MAP.get(f, 0) for f in t1_features]

res_t1 = cv_score(X_t1_kp, y_kp_cv, groups_kp, "T1 only", monotonic=mono_t1)
print(f"\n  {res_t1['name']}: R2={res_t1['r2']:+.3f} +/- {res_t1['std']:.3f}")

# Test top spread features individually
top_spread = [f for f, corr, n in correlations if abs(corr) >= 0.08]
print(f"\n  Individual spread features (|r| >= 0.08):")
for sf in top_spread[:12]:
    feats = list(t1_features) + [sf]
    X_plus = df_feat[feats].copy()
    for c in X_plus.columns:
        X_plus[c] = pd.to_numeric(X_plus[c], errors="coerce")
    X_plus = X_plus.fillna(X_plus.median()).iloc[keepa_idx].values
    mono = [MONOTONIC_MAP.get(f, 0) for f in feats]
    res = cv_score(X_plus, y_kp_cv, groups_kp, f"+{sf}", monotonic=mono)
    delta = res["r2"] - res_t1["r2"]
    marker = " !!!" if delta > 0.02 else " +" if delta > 0 else ""
    print(f"    {sf:<33}: R2={res['r2']:+.3f} (delta={delta:+.3f}){marker}")

# Best 3-5 features together
if len(top_spread) >= 3:
    # Pick top 3 least correlated
    best_3 = top_spread[:3]
    feats_3 = list(t1_features) + best_3
    X_3 = df_feat[feats_3].copy()
    for c in X_3.columns:
        X_3[c] = pd.to_numeric(X_3[c], errors="coerce")
    X_3 = X_3.fillna(X_3.median()).iloc[keepa_idx].values
    mono_3 = [MONOTONIC_MAP.get(f, 0) for f in feats_3]
    res_3 = cv_score(X_3, y_kp_cv, groups_kp, f"T1 + top 3 spread", monotonic=mono_3)
    print(f"\n  {res_3['name']}: R2={res_3['r2']:+.3f} (delta={res_3['r2'] - res_t1['r2']:+.3f})")

print(f"\nTotal time: {time.time() - t0:.0f}s")
