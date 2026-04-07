"""Test Keepa separated price signals: 3P FBA/FBM premium, sales rank, stock-out, discount trajectory.

We have rich Keepa data (amazon, buy_box, 3p_fba, 3p_fbm, sales_rank) in DB
but only use amazon_price_json in the ML pipeline. This script tests whether
the separated signals are predictive of post-retirement growth.

Run: python -m scripts.keepa_signals_scan
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
print("KEEPA SEPARATED SIGNALS SCAN")
print("Testing: 3P premium, sales rank, stock-out, discount trajectory")
print("=" * 70)

t0 = time.time()

# ---------------------------------------------------------------------------
# Load base ML data
# ---------------------------------------------------------------------------

from db.pg.engine import get_engine
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.feature_selection import select_features
from services.ml.pg_queries import load_growth_training_data

engine = get_engine()
df_raw = load_growth_training_data(engine)
y_all = df_raw["annual_growth_pct"].values.astype(float)
year_retired = np.asarray(
    pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
)

# Build T1 features
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

# Groups
finite = np.isfinite(year_retired)
groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
groups[finite] = year_retired[finite].astype(int)

print(f"\nBase: {len(y_all)} sets, {len(t1_features)} T1 features")

# ---------------------------------------------------------------------------
# Load ALL Keepa timelines from DB
# ---------------------------------------------------------------------------

from sqlalchemy import text

with engine.connect() as conn:
    keepa_df = pd.read_sql(text("""
        SELECT
            ks.set_number,
            ks.amazon_price_json,
            ks.buy_box_json,
            ks.new_3p_fba_json,
            ks.new_3p_fbm_json,
            ks.sales_rank_json,
            ks.new_price_json,
            ks.tracking_users
        FROM keepa_snapshots ks
        INNER JOIN (
            SELECT set_number, MAX(scraped_at) AS latest
            FROM keepa_snapshots
            GROUP BY set_number
        ) l ON ks.set_number = l.set_number AND ks.scraped_at = l.latest
        WHERE ks.amazon_price_json IS NOT NULL
    """), conn)

print(f"Keepa snapshots: {len(keepa_df)} sets")

# Check coverage of each JSON column
for col in ["amazon_price_json", "buy_box_json", "new_3p_fba_json",
            "new_3p_fbm_json", "sales_rank_json", "new_price_json"]:
    non_null = keepa_df[col].notna().sum()
    print(f"  {col}: {non_null}/{len(keepa_df)} ({non_null/len(keepa_df)*100:.0f}%)")


# ---------------------------------------------------------------------------
# Extract separated Keepa features
# ---------------------------------------------------------------------------

def parse_timeline(raw):
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []

def extract_prices(timeline):
    return [float(p[1]) for p in timeline if len(p) >= 2 and p[1] is not None and p[1] > 0]


# RRP lookup from training data
rrp_lookup = dict(zip(
    df_raw["set_number"],
    pd.to_numeric(df_raw["rrp_usd_cents"], errors="coerce").fillna(0),
))

# Retirement date lookup for cutoff
retire_date_lookup = {}
for _, row in df_raw.iterrows():
    rd = pd.to_datetime(row.get("retired_date"), errors="coerce")
    if pd.isna(rd):
        yr = row.get("year_retired")
        if pd.notna(yr):
            rd = pd.Timestamp(f"{int(yr)}-07-01")
    if pd.notna(rd):
        retire_date_lookup[row["set_number"]] = rd.strftime("%Y-%m")

keepa_features = {}

for _, kr in keepa_df.iterrows():
    sn = kr["set_number"]
    rrp = rrp_lookup.get(sn, 0)
    if rrp <= 0:
        continue

    cutoff = retire_date_lookup.get(sn)
    rec = {}

    # --- Amazon prices (pre-cutoff only) ---
    amz_tl = parse_timeline(kr["amazon_price_json"])
    if cutoff:
        amz_tl = [p for p in amz_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
    amz_prices = extract_prices(amz_tl)

    if len(amz_prices) >= 3:
        amz_mean = np.mean(amz_prices)

        # Basic Amazon features (what we already use)
        rec["kp_amz_avg_discount"] = (rrp - amz_mean) / rrp * 100
        rec["kp_amz_max_discount"] = (rrp - min(amz_prices)) / rrp * 100
        rec["kp_amz_price_cv"] = np.std(amz_prices) / amz_mean if amz_mean > 0 else 0

        # Discount trajectory: is discount deepening or recovering?
        if len(amz_prices) >= 6:
            q = len(amz_prices) // 3
            early_disc = (rrp - np.mean(amz_prices[:q])) / rrp * 100
            late_disc = (rrp - np.mean(amz_prices[-q:])) / rrp * 100
            rec["kp_discount_trajectory"] = late_disc - early_disc  # positive = deepening, negative = recovering

        # Stock-out analysis
        stockout_count = 0
        in_stockout = False
        in_stock_pts = 0
        total_pts = 0
        for point in amz_tl:
            if len(point) < 2:
                continue
            total_pts += 1
            if point[1] is not None and point[1] > 0:
                in_stock_pts += 1
                in_stockout = False
            elif not in_stockout:
                stockout_count += 1
                in_stockout = True

        rec["kp_stockout_count"] = stockout_count
        rec["kp_stockout_pct"] = (1 - in_stock_pts / total_pts) * 100 if total_pts > 0 else 0

        # Months of stock-out pre-retirement
        if amz_tl:
            dates = [p[0] for p in amz_tl if len(p) >= 2 and isinstance(p[0], str)]
            if len(dates) >= 2:
                try:
                    d_first = pd.to_datetime(dates[0])
                    d_last = pd.to_datetime(dates[-1])
                    total_months = max(1, (d_last - d_first).days / 30)
                    rec["kp_months_in_stock"] = total_months * (in_stock_pts / total_pts) if total_pts > 0 else 0
                except (ValueError, TypeError):
                    pass

    # --- 3P FBA prices (pre-cutoff) ---
    fba_tl = parse_timeline(kr["new_3p_fba_json"])
    if cutoff:
        fba_tl = [p for p in fba_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
    fba_prices = extract_prices(fba_tl)

    if fba_prices and rrp > 0:
        fba_mean = np.mean(fba_prices)
        rec["kp_3p_fba_vs_rrp"] = (fba_mean - rrp) / rrp * 100  # BrickTalk's key signal!
        rec["kp_3p_fba_min_vs_rrp"] = (min(fba_prices) - rrp) / rrp * 100
        rec["kp_3p_fba_max_vs_rrp"] = (max(fba_prices) - rrp) / rrp * 100
        rec["kp_3p_fba_cv"] = np.std(fba_prices) / fba_mean if fba_mean > 0 else 0
        if amz_prices:
            rec["kp_3p_premium_vs_amz"] = (fba_mean - np.mean(amz_prices)) / np.mean(amz_prices) * 100

    # --- 3P FBM prices (pre-cutoff) ---
    fbm_tl = parse_timeline(kr["new_3p_fbm_json"])
    if cutoff:
        fbm_tl = [p for p in fbm_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
    fbm_prices = extract_prices(fbm_tl)

    if fbm_prices and rrp > 0:
        fbm_mean = np.mean(fbm_prices)
        rec["kp_3p_fbm_vs_rrp"] = (fbm_mean - rrp) / rrp * 100
        rec["kp_3p_fbm_min_vs_rrp"] = (min(fbm_prices) - rrp) / rrp * 100

    # --- Buy box (pre-cutoff) ---
    bb_tl = parse_timeline(kr["buy_box_json"])
    if cutoff:
        bb_tl = [p for p in bb_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
    bb_prices = extract_prices(bb_tl)

    if bb_prices and rrp > 0:
        bb_mean = np.mean(bb_prices)
        rec["kp_bb_avg_vs_rrp"] = (bb_mean - rrp) / rrp * 100
        rec["kp_bb_max_premium"] = (max(bb_prices) - rrp) / rrp * 100

    # --- Sales rank (pre-cutoff) ---
    rank_tl = parse_timeline(kr["sales_rank_json"])
    if cutoff:
        rank_tl = [p for p in rank_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
    rank_vals = extract_prices(rank_tl)

    if len(rank_vals) >= 3:
        rec["kp_rank_median"] = np.median(rank_vals)
        rec["kp_rank_mean"] = np.mean(rank_vals)
        rec["kp_rank_cv"] = np.std(rank_vals) / np.mean(rank_vals) if np.mean(rank_vals) > 0 else 0
        rec["kp_log_rank"] = np.log1p(np.median(rank_vals))
        if len(rank_vals) >= 6:
            q = len(rank_vals) // 3
            early_rank = np.mean(rank_vals[:q])
            late_rank = np.mean(rank_vals[-q:])
            if early_rank > 0:
                rec["kp_rank_trend"] = (late_rank - early_rank) / early_rank * 100  # negative = improving

    # --- Tracking users ---
    if pd.notna(kr.get("tracking_users")) and kr["tracking_users"] and kr["tracking_users"] > 0:
        rec["kp_tracking_users"] = int(kr["tracking_users"])
        rec["kp_log_tracking"] = np.log1p(int(kr["tracking_users"]))

    keepa_features[sn] = rec

print(f"\nExtracted Keepa features for {len(keepa_features)} sets")


# ---------------------------------------------------------------------------
# Build feature matrix for Keepa subset
# ---------------------------------------------------------------------------

# Map Keepa features to training data
keepa_feat_names = set()
for rec in keepa_features.values():
    keepa_feat_names.update(rec.keys())
keepa_feat_names = sorted(keepa_feat_names)

print(f"Keepa features available: {len(keepa_feat_names)}")

# Match to training set
keepa_mask = df_raw["set_number"].isin(keepa_features)
n_matched = keepa_mask.sum()
print(f"Matched to training data: {n_matched}/{len(df_raw)} ({n_matched/len(df_raw)*100:.0f}%)")

# Build Keepa feature columns
for feat in keepa_feat_names:
    df_feat[feat] = df_raw["set_number"].map(
        lambda sn, f=feat: keepa_features.get(sn, {}).get(f, np.nan)
    )


# ---------------------------------------------------------------------------
# Part 1: Correlation analysis on Keepa subset
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PART 1: CORRELATION WITH GROWTH (Keepa subset only)")
print("=" * 70)

y_keepa = y_all[keepa_mask.values]
n_keepa = len(y_keepa)

correlations = []
for feat in keepa_feat_names:
    vals = df_feat.loc[keepa_mask, feat].values.astype(float)
    valid = np.isfinite(vals) & np.isfinite(y_keepa)
    n_valid = valid.sum()
    if n_valid >= 20:
        corr = np.corrcoef(vals[valid], y_keepa[valid])[0, 1]
        coverage = n_valid / n_keepa * 100
        correlations.append((feat, corr, n_valid, coverage))

correlations.sort(key=lambda x: abs(x[1]), reverse=True)

print(f"\n{'Feature':<30} {'Corr':>8} {'n':>6} {'Coverage':>8}")
print("-" * 55)
for feat, corr, n, cov in correlations:
    marker = " ***" if abs(corr) >= 0.10 else " *" if abs(corr) >= 0.05 else ""
    print(f"  {feat:<28} {corr:+.3f}  {n:>5}  {cov:>6.0f}%{marker}")


# ---------------------------------------------------------------------------
# Part 2: Group analysis — 3P FBA premium signal
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PART 2: 3P FBA PREMIUM SIGNAL (BrickTalk's key signal)")
print("=" * 70)

fba_feat = "kp_3p_fba_vs_rrp"
fba_vals = df_feat.loc[keepa_mask, fba_feat].values.astype(float)
valid_fba = np.isfinite(fba_vals)

if valid_fba.sum() >= 20:
    fba_data = fba_vals[valid_fba]
    y_fba = y_keepa[valid_fba]

    # Split into premium vs discount
    above_rrp = fba_data > 0
    below_rrp = fba_data <= 0

    if above_rrp.sum() >= 5 and below_rrp.sum() >= 5:
        print(f"\n3P FBA above RRP (premium): n={above_rrp.sum()}, avg growth={y_fba[above_rrp].mean():.1f}%")
        print(f"3P FBA below RRP (discount): n={below_rrp.sum()}, avg growth={y_fba[below_rrp].mean():.1f}%")
        print(f"Delta: {y_fba[above_rrp].mean() - y_fba[below_rrp].mean():+.1f}%")

    # Quartile analysis
    print("\n3P FBA premium quartile analysis:")
    for q_lo, q_hi, label in [(0, 25, "Q1 (deepest discount)"), (25, 50, "Q2"),
                               (50, 75, "Q3"), (75, 100, "Q4 (highest premium)")]:
        lo = np.percentile(fba_data, q_lo)
        hi = np.percentile(fba_data, q_hi)
        mask_q = (fba_data >= lo) & (fba_data < hi if q_hi < 100 else fba_data <= hi)
        if mask_q.sum() >= 5:
            print(f"  {label}: n={mask_q.sum()}, range=[{lo:+.0f}%,{hi:+.0f}%], avg growth={y_fba[mask_q].mean():.1f}%")
else:
    print(f"\nInsufficient 3P FBA data: {valid_fba.sum()} valid")


# ---------------------------------------------------------------------------
# Part 3: Sales rank signal
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PART 3: SALES RANK SIGNAL (demand proxy)")
print("=" * 70)

rank_feat = "kp_log_rank"
if rank_feat not in df_feat.columns:
    print(f"\n  {rank_feat} not in feature set -- no sales rank data extracted")
    print("  Checking raw sales_rank_json...")
    # Sample check
    sample = keepa_df["sales_rank_json"].dropna().head(3)
    for i, raw in enumerate(sample):
        tl = parse_timeline(raw)
        vals = extract_prices(tl)
        print(f"  Sample {i}: {len(tl)} points, {len(vals)} valid values, first 3: {tl[:3]}")
    valid_rank = np.array([False])
else:
    rank_vals = df_feat.loc[keepa_mask, rank_feat].values.astype(float)
    valid_rank = np.isfinite(rank_vals)

if valid_rank.sum() >= 20:
    rank_data = rank_vals[valid_rank]
    y_rank = y_keepa[valid_rank]

    # Quartile analysis
    print(f"\nSales rank (log) quartile analysis (n={valid_rank.sum()}):")
    for q_lo, q_hi, label in [(0, 25, "Q1 (most popular)"), (25, 50, "Q2"),
                               (50, 75, "Q3"), (75, 100, "Q4 (least popular)")]:
        lo = np.percentile(rank_data, q_lo)
        hi = np.percentile(rank_data, q_hi)
        mask_q = (rank_data >= lo) & (rank_data < hi if q_hi < 100 else rank_data <= hi)
        if mask_q.sum() >= 5:
            raw_rank_lo = np.exp(lo) - 1
            raw_rank_hi = np.exp(hi) - 1
            print(f"  {label}: n={mask_q.sum()}, rank=[{raw_rank_lo:.0f},{raw_rank_hi:.0f}], avg growth={y_rank[mask_q].mean():.1f}%")


# ---------------------------------------------------------------------------
# Part 4: CV test — do Keepa features improve T1?
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PART 4: CV TEST — T1 vs T1+Keepa signals (Keepa subset)")
print("=" * 70)

import lightgbm as lgb
from services.ml.growth.model_selection import MONOTONIC_MAP


def cv_score(X_vals, y, groups, name="", monotonic=None):
    """5-fold GroupKFold CV."""
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


# Keepa subset indices
keepa_idx = np.where(keepa_mask.values)[0]
y_kp = y_all[keepa_idx]
groups_kp = groups[keepa_idx]

# T1-only on Keepa subset (baseline)
X_t1_kp = X_raw[t1_features].fillna(X_raw[t1_features].median()).iloc[keepa_idx].values
mono_t1 = [MONOTONIC_MAP.get(f, 0) for f in t1_features]

res_t1 = cv_score(X_t1_kp, y_kp, groups_kp, "T1 only (Keepa subset)", monotonic=mono_t1)
print(f"\n  {res_t1['name']}: R2={res_t1['r2']:+.3f} +/- {res_t1['std']:.3f}  MAE={res_t1['mae']:.1f}%")

# Top Keepa signals by |correlation| > 0.05 with good coverage
promising_keepa = [f for f, corr, n, cov in correlations if abs(corr) >= 0.05 and cov >= 40]
print(f"\nPromising Keepa features (|r| >= 0.05, coverage >= 40%): {promising_keepa}")

if promising_keepa:
    # T1 + promising Keepa features
    all_feats = list(t1_features) + promising_keepa
    X_combined = df_feat[all_feats].copy()
    for c in X_combined.columns:
        X_combined[c] = pd.to_numeric(X_combined[c], errors="coerce")
    X_combined = X_combined.fillna(X_combined.median())
    X_combined_kp = X_combined.iloc[keepa_idx].values

    mono_combined = [MONOTONIC_MAP.get(f, 0) for f in all_feats]

    res_combined = cv_score(X_combined_kp, y_kp, groups_kp, f"T1 + {len(promising_keepa)} Keepa signals", monotonic=mono_combined)
    print(f"  {res_combined['name']}: R2={res_combined['r2']:+.3f} +/- {res_combined['std']:.3f}  MAE={res_combined['mae']:.1f}%")
    print(f"  Delta vs T1: {res_combined['r2'] - res_t1['r2']:+.3f}")

    # Try individual top features one at a time
    print("\n  Individual feature contribution (T1 + 1 Keepa feature):")
    for kf in promising_keepa[:8]:
        feats_single = list(t1_features) + [kf]
        X_single = df_feat[feats_single].copy()
        for c in X_single.columns:
            X_single[c] = pd.to_numeric(X_single[c], errors="coerce")
        X_single = X_single.fillna(X_single.median())
        X_single_kp = X_single.iloc[keepa_idx].values
        mono_s = [MONOTONIC_MAP.get(f, 0) for f in feats_single]

        res_s = cv_score(X_single_kp, y_kp, groups_kp, f"+{kf}", monotonic=mono_s)
        delta = res_s["r2"] - res_t1["r2"]
        marker = " !!!" if delta > 0.02 else " +" if delta > 0 else ""
        print(f"    {kf:<30}: R2={res_s['r2']:+.3f} (delta={delta:+.3f}){marker}")


# ---------------------------------------------------------------------------
# Part 5: New feature ideas from gap analysis 2
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PART 5: GAP ANALYSIS 2 FEATURE IDEAS")
print("=" * 70)

# high_price_barrier: >$300 sets benefit from reduced investor competition
rrp_usd = pd.to_numeric(df_raw["rrp_usd_cents"], errors="coerce") / 100
high_price = rrp_usd > 300
if high_price.sum() >= 10:
    y_high = y_all[high_price.values]
    y_low = y_all[~high_price.values]
    print(f"\nhigh_price_barrier (>$300):")
    print(f"  >$300: n={high_price.sum()}, avg growth={y_high.mean():.1f}%")
    print(f"  <=$300: n=(~high_price).sum(), avg growth={y_low.mean():.1f}%")
    print(f"  Delta: {y_high.mean() - y_low.mean():+.1f}%")

# has_electronics proxy: check if "powered" or "electronic" or "sound" in set name
if "set_name" in df_raw.columns:
    name_lower = df_raw["set_name"].str.lower().fillna("")
    has_electronic = name_lower.str.contains("powered|electronic|sound|motorized|bluetooth", regex=True)
    if has_electronic.sum() >= 5:
        print(f"\nhas_electronics (name contains powered/electronic/sound/motorized):")
        print(f"  Electronic: n={has_electronic.sum()}, avg growth={y_all[has_electronic.values].mean():.1f}%")
        print(f"  Standard: n=(~has_electronic).sum(), avg growth={y_all[~has_electronic.values].mean():.1f}%")

# UCS/D2C detection from subtheme
if "subtheme" in df_raw.columns:
    sub_lower = df_raw["subtheme"].str.lower().fillna("")
    is_ucs = sub_lower.str.contains("ucs|ultimate collector|master builder|d2c", regex=True)
    if is_ucs.sum() >= 5:
        print(f"\nis_ucs (subtheme contains UCS/Ultimate Collector/D2C):")
        print(f"  UCS/D2C: n={is_ucs.sum()}, avg growth={y_all[is_ucs.values].mean():.1f}%")
        print(f"  Regular: n={(~is_ucs).sum()}, avg growth={y_all[~is_ucs.values].mean():.1f}%")
        print(f"  Delta: {y_all[is_ucs.values].mean() - y_all[~is_ucs.values].mean():+.1f}%")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"\nTotal time: {time.time() - t0:.0f}s")
print("\nKey questions answered:")
print("1. Are separated Keepa prices (3P FBA/FBM/buy box) predictive?")
print("2. Is sales rank a demand proxy?")
print("3. Do Keepa features help when cherry-picked (not all-at-once)?")
print("4. Any gap analysis 2 features worth adding?")
