"""Deep investigation: Are Keepa 3P/BB features truly leaky or just noisy?

Tests:
1. Temporal analysis: when do 3P premiums appear relative to retirement?
2. Does early 3P premium (>12mo before retirement) still correlate?
3. Feature leakage test: train on early sets, predict later -- does Keepa help?
4. Keepa features for ONLY sets >6mo from retirement cutoff
5. Is the 3P premium correlated with theme_bayes? (confounding)

Run: python -m scripts.keepa_leakage_investigation
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
print("KEEPA LEAKAGE DEEP INVESTIGATION")
print("=" * 70)

t0 = time.time()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

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

df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
    df_raw, training_target=pd.Series(y_all)
)

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
        SELECT ks.set_number, ks.amazon_price_json, ks.buy_box_json,
               ks.new_3p_fba_json, ks.new_3p_fbm_json, ks.scraped_at
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

print(f"Data: {len(df_raw)} sets, {len(keepa_df)} Keepa snapshots")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_timeline(raw):
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# TEST 1: When does 3P premium appear relative to retirement?
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 1: TEMPORAL ANALYSIS — When do 3P premiums appear?")
print("=" * 70)

months_before_premium = []
first_premium_data = []

for _, kr in keepa_df.iterrows():
    sn = kr["set_number"]
    rrp = rrp_lookup.get(sn, 0)
    ret_date = retire_lookup.get(sn)
    if rrp <= 0 or pd.isna(ret_date):
        continue

    fba_tl = parse_timeline(kr["new_3p_fba_json"])
    if not fba_tl:
        continue

    # Find first time 3P FBA > RRP
    first_premium_date = None
    for point in fba_tl:
        if len(point) >= 2 and point[1] is not None and point[1] > rrp * 1.05:
            try:
                dt = pd.to_datetime(point[0])
                months_before = (ret_date - dt).days / 30
                if months_before > 0:  # only pre-retirement
                    first_premium_date = dt
                    months_before_premium.append(months_before)
                    break
            except (ValueError, TypeError):
                continue

if months_before_premium:
    arr = np.array(months_before_premium)
    print(f"\nSets where 3P FBA exceeded RRP pre-retirement: {len(arr)}")
    print(f"Months before retirement when premium first appeared:")
    print(f"  Mean: {arr.mean():.1f} months")
    print(f"  Median: {np.median(arr):.1f} months")
    print(f"  P25: {np.percentile(arr, 25):.1f} months")
    print(f"  P75: {np.percentile(arr, 75):.1f} months")
    print(f"  >12 months: {(arr > 12).sum()} ({(arr > 12).mean()*100:.0f}%)")
    print(f"  >6 months: {(arr > 6).sum()} ({(arr > 6).mean()*100:.0f}%)")
    print(f"  <3 months: {(arr < 3).sum()} ({(arr < 3).mean()*100:.0f}%)")


# ---------------------------------------------------------------------------
# TEST 2: Early-only 3P premium (>12mo before retirement)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 2: EARLY-ONLY 3P FBA PREMIUM (>12mo before retirement)")
print("=" * 70)

early_features = {}

for _, kr in keepa_df.iterrows():
    sn = kr["set_number"]
    rrp = rrp_lookup.get(sn, 0)
    ret_date = retire_lookup.get(sn)
    if rrp <= 0 or pd.isna(ret_date):
        continue

    # Cutoff = 12 months before retirement
    early_cutoff = ret_date - pd.Timedelta(days=365)
    cutoff_str = early_cutoff.strftime("%Y-%m")

    # 3P FBA with early cutoff
    fba_tl = parse_timeline(kr["new_3p_fba_json"])
    fba_early = [p for p in fba_tl if len(p) >= 2 and isinstance(p[0], str) and p[0][:7] <= cutoff_str]
    fba_prices = [float(p[1]) for p in fba_early if p[1] is not None and p[1] > 0]

    if fba_prices:
        fba_mean = np.mean(fba_prices)
        early_features[sn] = {
            "kp_early_3p_fba_vs_rrp": (fba_mean - rrp) / rrp * 100,
            "kp_early_3p_fba_max_vs_rrp": (max(fba_prices) - rrp) / rrp * 100,
        }

    # Also 6-month cutoff
    mid_cutoff = ret_date - pd.Timedelta(days=183)
    cutoff_6m = mid_cutoff.strftime("%Y-%m")
    fba_mid = [p for p in fba_tl if len(p) >= 2 and isinstance(p[0], str) and p[0][:7] <= cutoff_6m]
    fba_prices_mid = [float(p[1]) for p in fba_mid if p[1] is not None and p[1] > 0]

    if fba_prices_mid:
        fba_mean_mid = np.mean(fba_prices_mid)
        if sn not in early_features:
            early_features[sn] = {}
        early_features[sn]["kp_6m_3p_fba_vs_rrp"] = (fba_mean_mid - rrp) / rrp * 100

print(f"\nSets with early (>12mo) FBA data: {sum(1 for v in early_features.values() if 'kp_early_3p_fba_vs_rrp' in v)}")
print(f"Sets with mid (>6mo) FBA data: {sum(1 for v in early_features.values() if 'kp_6m_3p_fba_vs_rrp' in v)}")

# Correlations for early-only
for feat_name in ["kp_early_3p_fba_vs_rrp", "kp_early_3p_fba_max_vs_rrp", "kp_6m_3p_fba_vs_rrp"]:
    vals = []
    growth = []
    for i, row in df_raw.iterrows():
        sn = row["set_number"]
        if sn in early_features and feat_name in early_features[sn]:
            vals.append(early_features[sn][feat_name])
            growth.append(y_all[i])

    if len(vals) >= 20:
        corr = np.corrcoef(vals, growth)[0, 1]
        print(f"  {feat_name}: r={corr:+.3f} (n={len(vals)})")


# ---------------------------------------------------------------------------
# TEST 3: Confounding test — is 3P premium just proxying for theme?
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 3: CONFOUNDING — Is 3P premium just proxying for theme?")
print("=" * 70)

# Check correlation between 3P FBA premium and theme_bayes
fba_rrp_vals = []
theme_bayes_vals = []
growth_vals = []

for i, row in df_raw.iterrows():
    sn = row["set_number"]
    if sn in early_features and "kp_6m_3p_fba_vs_rrp" in early_features[sn]:
        fba_rrp_vals.append(early_features[sn]["kp_6m_3p_fba_vs_rrp"])
        if "theme_bayes" in df_feat.columns:
            theme_bayes_vals.append(float(df_feat.loc[i, "theme_bayes"]) if pd.notna(df_feat.loc[i, "theme_bayes"]) else np.nan)
        growth_vals.append(y_all[i])

if len(fba_rrp_vals) >= 20:
    fba_arr = np.array(fba_rrp_vals)
    growth_arr = np.array(growth_vals)
    theme_arr = np.array(theme_bayes_vals)

    valid = np.isfinite(fba_arr) & np.isfinite(theme_arr) & np.isfinite(growth_arr)
    if valid.sum() >= 20:
        # Partial correlation: FBA premium → growth, controlling for theme
        from numpy.linalg import lstsq

        # Residualize: remove theme effect from both FBA and growth
        A_theme = np.column_stack([theme_arr[valid], np.ones(valid.sum())])
        fba_resid = fba_arr[valid] - A_theme @ lstsq(A_theme, fba_arr[valid], rcond=None)[0]
        growth_resid = growth_arr[valid] - A_theme @ lstsq(A_theme, growth_arr[valid], rcond=None)[0]

        raw_corr = np.corrcoef(fba_arr[valid], growth_arr[valid])[0, 1]
        partial_corr = np.corrcoef(fba_resid, growth_resid)[0, 1]
        theme_fba_corr = np.corrcoef(theme_arr[valid], fba_arr[valid])[0, 1]

        print(f"\n  3P FBA vs growth (raw): r={raw_corr:+.3f}")
        print(f"  3P FBA vs growth (partial, controlling for theme): r={partial_corr:+.3f}")
        print(f"  3P FBA vs theme_bayes: r={theme_fba_corr:+.3f}")

        if abs(partial_corr) < abs(raw_corr) * 0.5:
            print("  VERDICT: 3P premium is largely proxying for theme -- confounded")
        elif abs(partial_corr) > abs(raw_corr) * 0.7:
            print("  VERDICT: 3P premium has independent signal beyond theme")
        else:
            print("  VERDICT: 3P premium partially confounded by theme, some independent signal")


# ---------------------------------------------------------------------------
# TEST 4: CV with early-only features (non-leaky version)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 4: CV WITH EARLY-ONLY KEEPA FEATURES (>6mo cutoff)")
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

    return {"name": name, "r2": np.mean(r2s), "std": np.std(r2s),
            "mae": np.mean(maes), "folds": r2s}


# Map early features to training data
for feat in ["kp_early_3p_fba_vs_rrp", "kp_early_3p_fba_max_vs_rrp", "kp_6m_3p_fba_vs_rrp"]:
    df_feat[feat] = df_raw["set_number"].map(
        lambda sn, f=feat: early_features.get(sn, {}).get(f, np.nan)
    )

# Keepa-matched subset
keepa_6m_mask = df_feat["kp_6m_3p_fba_vs_rrp"].notna()
n_6m = keepa_6m_mask.sum()
print(f"\nSets with >6mo FBA data matched to training: {n_6m}")

if n_6m >= 100:
    keepa_6m_idx = np.where(keepa_6m_mask.values)[0]
    y_6m = y_all[keepa_6m_idx]
    groups_6m = groups[keepa_6m_idx]

    # T1-only baseline on this subset
    X_t1_6m = X_raw[t1_features].fillna(X_raw[t1_features].median()).iloc[keepa_6m_idx].values
    mono_t1 = [MONOTONIC_MAP.get(f, 0) for f in t1_features]
    res_t1 = cv_score(X_t1_6m, y_6m, groups_6m, "T1 only", monotonic=mono_t1)
    print(f"  {res_t1['name']}: R2={res_t1['r2']:+.3f} +/- {res_t1['std']:.3f}")

    # T1 + early 3P FBA
    for extra in ["kp_6m_3p_fba_vs_rrp", "kp_early_3p_fba_vs_rrp"]:
        n_valid = df_feat.loc[keepa_6m_mask, extra].notna().sum()
        if n_valid >= 50:
            feats = list(t1_features) + [extra]
            X_plus = df_feat[feats].copy()
            for c in X_plus.columns:
                X_plus[c] = pd.to_numeric(X_plus[c], errors="coerce")
            X_plus = X_plus.fillna(X_plus.median()).iloc[keepa_6m_idx].values
            mono = [MONOTONIC_MAP.get(f, 0) for f in feats]
            res = cv_score(X_plus, y_6m, groups_6m, f"T1 + {extra}", monotonic=mono)
            delta = res["r2"] - res_t1["r2"]
            print(f"  {res['name']}: R2={res['r2']:+.3f} (delta={delta:+.3f})")


# ---------------------------------------------------------------------------
# TEST 5: What about Keepa on just "never-discounted-on-Amazon" sets?
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TEST 5: SUBSET ANALYSIS — Never-discounted-on-Amazon sets")
print("=" * 70)

# For each set, check if Amazon price was always >= 98% RRP
never_disc = {}
for _, kr in keepa_df.iterrows():
    sn = kr["set_number"]
    rrp = rrp_lookup.get(sn, 0)
    ret_date = retire_lookup.get(sn)
    if rrp <= 0 or pd.isna(ret_date):
        continue

    cutoff_str = ret_date.strftime("%Y-%m")
    amz_tl = parse_timeline(kr["amazon_price_json"])
    amz_pre = [p for p in amz_tl if len(p) >= 2 and isinstance(p[0], str) and p[0][:7] <= cutoff_str]
    amz_prices = [float(p[1]) for p in amz_pre if p[1] is not None and p[1] > 0]

    if len(amz_prices) >= 5:
        max_disc = (rrp - min(amz_prices)) / rrp * 100
        never_disc[sn] = max_disc < 5  # never more than 5% below RRP

# Check growth
nd_growth = []
disc_growth = []
for i, row in df_raw.iterrows():
    sn = row["set_number"]
    if sn in never_disc:
        if never_disc[sn]:
            nd_growth.append(y_all[i])
        else:
            disc_growth.append(y_all[i])

if len(nd_growth) >= 10 and len(disc_growth) >= 10:
    print(f"\n  Never discounted (max_disc < 5%): n={len(nd_growth)}, avg growth={np.mean(nd_growth):.1f}%, median={np.median(nd_growth):.1f}%")
    print(f"  Discounted: n={len(disc_growth)}, avg growth={np.mean(disc_growth):.1f}%, median={np.median(disc_growth):.1f}%")
    print(f"  Delta (mean): {np.mean(nd_growth) - np.mean(disc_growth):+.1f}%")
    print(f"  Delta (median): {np.median(nd_growth) - np.median(disc_growth):+.1f}%")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"\nTotal time: {time.time() - t0:.0f}s")
print("\nThis investigation determines whether Keepa 3P/BB signals are:")
print("  a) Truly leaky (measuring the outcome)")
print("  b) Confounded by theme (just proxying for theme_bayes)")
print("  c) Valid but too noisy for small datasets")
print("  d) Non-leaky when using early-only cutoff (>6mo or >12mo before retirement)")
