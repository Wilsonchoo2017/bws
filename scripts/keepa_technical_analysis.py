"""Technical analysis indicators on Keepa price timelines.

Treat Amazon/3P price history like stock charts. Extract SMA, EMA, RSI,
MACD, Bollinger Bands, momentum, trend strength, support/resistance, etc.
Test which (if any) predict post-retirement growth.

Run: python -m scripts.keepa_technical_analysis
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
print("KEEPA TECHNICAL ANALYSIS SCAN")
print("SMA, EMA, RSI, MACD, Bollinger, Momentum, Support/Resistance")
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
               ks.new_3p_fba_json, ks.new_3p_fbm_json
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

# Retirement dates for cutoff
retire_dt = pd.to_datetime(df_raw.get("retired_date"), errors="coerce")
yr_ret = pd.to_numeric(df_raw.get("year_retired"), errors="coerce")
retire_dt_approx = pd.to_datetime(
    yr_ret.dropna().astype(int).astype(str) + "-07-01", errors="coerce"
).reindex(df_raw.index)
retire_dt = retire_dt.fillna(retire_dt_approx)
retire_lookup = dict(zip(df_raw["set_number"], retire_dt))

print(f"\nData: {len(df_raw)} training sets, {len(keepa_df)} Keepa snapshots")


# ---------------------------------------------------------------------------
# Technical Analysis Functions
# ---------------------------------------------------------------------------

def parse_timeline(raw):
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def to_daily_series(timeline: list, cutoff_str: str | None = None) -> pd.Series:
    """Convert irregular Keepa timeline to daily price series (forward-filled)."""
    points = []
    for p in timeline:
        if len(p) < 2 or not isinstance(p[0], str):
            continue
        if cutoff_str and p[0][:7] > cutoff_str:
            break
        try:
            dt = pd.to_datetime(p[0])
            val = float(p[1]) if p[1] is not None and p[1] > 0 else np.nan
            points.append((dt, val))
        except (ValueError, TypeError):
            continue

    if len(points) < 2:
        return pd.Series(dtype=float)

    df = pd.DataFrame(points, columns=["date", "price"]).set_index("date")
    df = df[~df.index.duplicated(keep="last")]
    daily = df.resample("D").last().ffill()
    return daily["price"].dropna()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line.dropna(), signal).reindex(macd_line.index)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    """Returns (upper, middle, lower, %B, bandwidth)."""
    middle = sma(series, window)
    std = series.rolling(window, min_periods=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    pct_b = (series - lower) / (upper - lower)
    bandwidth = (upper - lower) / middle
    return upper, middle, lower, pct_b, bandwidth


def rate_of_change(series: pd.Series, period: int) -> pd.Series:
    """Price rate of change (%)."""
    return (series / series.shift(period) - 1) * 100


def donchian_channel(series: pd.Series, window: int = 20):
    """Donchian channel: high, low, position within channel."""
    high = series.rolling(window, min_periods=window).max()
    low = series.rolling(window, min_periods=window).min()
    position = (series - low) / (high - low)
    return high, low, position


def avg_directional_index(series: pd.Series, period: int = 14) -> float:
    """Simplified ADX-like trend strength (0-100)."""
    if len(series) < period * 2:
        return np.nan
    changes = series.diff().dropna()
    if len(changes) < period:
        return np.nan
    # Compute directional movement
    pos_dm = changes.clip(lower=0)
    neg_dm = (-changes).clip(lower=0)
    pos_avg = pos_dm.rolling(period).mean()
    neg_avg = neg_dm.rolling(period).mean()
    total = pos_avg + neg_avg
    total = total.replace(0, np.nan)
    dx = abs(pos_avg - neg_avg) / total * 100
    adx = dx.rolling(period).mean()
    last_val = adx.dropna()
    return float(last_val.iloc[-1]) if len(last_val) > 0 else np.nan


def support_resistance(series: pd.Series, rrp: float):
    """Price relative to key levels."""
    if len(series) < 10:
        return {}
    prices = series.values
    current = prices[-1]
    all_time_low = np.min(prices)
    all_time_high = np.max(prices)

    # Distance from support (ATL) and resistance (ATH)
    price_range = all_time_high - all_time_low
    if price_range <= 0:
        return {}

    return {
        "ta_support_distance_pct": (current - all_time_low) / rrp * 100,
        "ta_resistance_distance_pct": (all_time_high - current) / rrp * 100,
        "ta_price_position": (current - all_time_low) / price_range,  # 0=at low, 1=at high
        "ta_ath_vs_rrp": (all_time_high - rrp) / rrp * 100,
        "ta_atl_vs_rrp": (all_time_low - rrp) / rrp * 100,
    }


# ---------------------------------------------------------------------------
# Extract TA features for each set
# ---------------------------------------------------------------------------

print("\nExtracting technical analysis features...")

ta_features = {}
skipped = {"short": 0, "no_rrp": 0, "no_retire": 0}

for _, kr in keepa_df.iterrows():
    sn = kr["set_number"]
    rrp = rrp_lookup.get(sn, 0)
    ret_date = retire_lookup.get(sn)

    if rrp <= 0:
        skipped["no_rrp"] += 1
        continue
    if pd.isna(ret_date):
        skipped["no_retire"] += 1
        continue

    cutoff_str = ret_date.strftime("%Y-%m")

    # Convert to daily series (Amazon 1P prices)
    amz_daily = to_daily_series(parse_timeline(kr["amazon_price_json"]), cutoff_str)
    if len(amz_daily) < 30:
        skipped["short"] += 1
        continue

    rec = {}
    n_days = len(amz_daily)
    current = float(amz_daily.iloc[-1])

    # --- Moving Averages ---
    for w in [7, 14, 30, 60, 90]:
        if n_days >= w:
            ma = float(sma(amz_daily, w).iloc[-1])
            rec[f"ta_sma{w}_vs_rrp"] = (ma - rrp) / rrp * 100
            rec[f"ta_price_vs_sma{w}"] = (current - ma) / rrp * 100

    for s in [7, 14, 30, 60]:
        if n_days >= s * 2:
            em = float(ema(amz_daily, s).iloc[-1])
            rec[f"ta_ema{s}_vs_rrp"] = (em - rrp) / rrp * 100

    # Golden/Death cross: SMA7 vs SMA30
    if n_days >= 30:
        sma7 = sma(amz_daily, 7)
        sma30 = sma(amz_daily, 30)
        both = pd.DataFrame({"s7": sma7, "s30": sma30}).dropna()
        if len(both) >= 5:
            rec["ta_golden_cross"] = float(both["s7"].iloc[-1] > both["s30"].iloc[-1])
            # Count crossovers in last 90 days
            tail = both.tail(min(90, len(both)))
            cross = ((tail["s7"] > tail["s30"]) != (tail["s7"].shift(1) > tail["s30"].shift(1)))
            rec["ta_cross_count_90d"] = float(cross.sum())

    # --- RSI ---
    for period in [14, 30]:
        if n_days >= period * 2:
            rsi_series = rsi(amz_daily, period)
            last_rsi = rsi_series.dropna()
            if len(last_rsi) > 0:
                rec[f"ta_rsi{period}"] = float(last_rsi.iloc[-1])
                rec[f"ta_rsi{period}_mean"] = float(last_rsi.mean())

    # --- MACD ---
    if n_days >= 60:
        # Use shorter windows for LEGO (not stock-market 12/26/9)
        macd_line, signal_line, histogram = macd(amz_daily, fast=7, slow=21, signal=5)
        hist_vals = histogram.dropna()
        if len(hist_vals) > 0:
            rec["ta_macd_histogram"] = float(hist_vals.iloc[-1]) / rrp * 100
            rec["ta_macd_signal_above"] = float(macd_line.iloc[-1] > signal_line.iloc[-1]) if pd.notna(signal_line.iloc[-1]) else np.nan
            # MACD trend direction
            if len(hist_vals) >= 10:
                rec["ta_macd_trend"] = float(hist_vals.iloc[-5:].mean() - hist_vals.iloc[-10:-5].mean()) / rrp * 100

    # --- Bollinger Bands ---
    for w in [20, 60]:
        if n_days >= w * 2:
            upper, middle, lower, pct_b, bandwidth = bollinger_bands(amz_daily, w)
            pct_b_clean = pct_b.dropna()
            bw_clean = bandwidth.dropna()
            if len(pct_b_clean) > 0:
                rec[f"ta_bb{w}_pct_b"] = float(pct_b_clean.iloc[-1])  # 0=at lower, 1=at upper
                rec[f"ta_bb{w}_pct_b_mean"] = float(pct_b_clean.mean())
            if len(bw_clean) > 0:
                rec[f"ta_bb{w}_bandwidth"] = float(bw_clean.iloc[-1])
                rec[f"ta_bb{w}_bandwidth_mean"] = float(bw_clean.mean())
                # Bandwidth squeeze: current vs average (low = potential breakout)
                bw_mean = float(bw_clean.mean())
                if bw_mean > 0:
                    rec[f"ta_bb{w}_squeeze"] = float(bw_clean.iloc[-1]) / bw_mean

    # --- Rate of Change / Momentum ---
    for period in [7, 14, 30, 60, 90]:
        if n_days >= period + 1:
            roc = rate_of_change(amz_daily, period)
            roc_clean = roc.dropna()
            if len(roc_clean) > 0:
                rec[f"ta_roc{period}"] = float(roc_clean.iloc[-1])

    # Momentum: average ROC over different windows
    if n_days >= 30:
        rec["ta_momentum_short"] = float((amz_daily.iloc[-1] / amz_daily.iloc[-min(7, n_days)] - 1) * 100)
    if n_days >= 90:
        rec["ta_momentum_long"] = float((amz_daily.iloc[-1] / amz_daily.iloc[-min(30, n_days)] - 1) * 100)

    # --- Trend Strength (ADX-like) ---
    for period in [14, 30]:
        if n_days >= period * 3:
            adx_val = avg_directional_index(amz_daily, period)
            if not np.isnan(adx_val):
                rec[f"ta_adx{period}"] = adx_val

    # --- Donchian Channel ---
    for w in [20, 60]:
        if n_days >= w:
            high, low, position = donchian_channel(amz_daily, w)
            pos_clean = position.dropna()
            if len(pos_clean) > 0:
                rec[f"ta_donchian{w}_position"] = float(pos_clean.iloc[-1])

    # --- Support / Resistance ---
    sr = support_resistance(amz_daily, rrp)
    rec.update(sr)

    # --- Volatility ---
    if n_days >= 14:
        daily_returns = amz_daily.pct_change().dropna()
        if len(daily_returns) >= 7:
            rec["ta_volatility_7d"] = float(daily_returns.tail(7).std() * np.sqrt(252) * 100)
            rec["ta_volatility_30d"] = float(daily_returns.tail(min(30, len(daily_returns))).std() * np.sqrt(252) * 100)
            rec["ta_volatility_all"] = float(daily_returns.std() * np.sqrt(252) * 100)
            # Volatility ratio: recent vs historical
            if len(daily_returns) >= 60:
                recent_vol = daily_returns.tail(30).std()
                hist_vol = daily_returns.std()
                if hist_vol > 0:
                    rec["ta_vol_ratio"] = float(recent_vol / hist_vol)

    # --- Price Distribution ---
    if n_days >= 30:
        prices = amz_daily.values
        rec["ta_skewness"] = float(pd.Series(prices).skew())
        rec["ta_kurtosis"] = float(pd.Series(prices).kurtosis())
        # % of time at/near RRP (within 2%)
        near_rrp = np.sum(np.abs(prices - rrp) / rrp < 0.02) / len(prices) * 100
        rec["ta_pct_at_rrp"] = near_rrp
        # % of time above RRP
        rec["ta_pct_above_rrp"] = float(np.sum(prices > rrp * 1.02) / len(prices) * 100)
        # % of time deeply discounted (>20% off)
        rec["ta_pct_deep_discount"] = float(np.sum(prices < rrp * 0.80) / len(prices) * 100)

    # --- Trend metrics ---
    if n_days >= 30:
        # Linear regression slope (normalized by RRP)
        x = np.arange(n_days)
        slope, intercept = np.polyfit(x, amz_daily.values, 1)
        rec["ta_trend_slope"] = float(slope / rrp * 30 * 100)  # % change per month
        # R-squared of trend (how "trendy" is the price?)
        y_fit = slope * x + intercept
        ss_res = np.sum((amz_daily.values - y_fit) ** 2)
        ss_tot = np.sum((amz_daily.values - np.mean(amz_daily.values)) ** 2)
        rec["ta_trend_r2"] = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0

    # --- Final price level ---
    rec["ta_final_vs_rrp"] = (current - rrp) / rrp * 100
    rec["ta_n_days"] = float(n_days)

    # --- 3P FBA TA (if available) ---
    fba_daily = to_daily_series(parse_timeline(kr["new_3p_fba_json"]), cutoff_str)
    if len(fba_daily) >= 30:
        fba_current = float(fba_daily.iloc[-1])
        rec["ta_fba_final_vs_rrp"] = (fba_current - rrp) / rrp * 100

        # FBA trend slope
        x_fba = np.arange(len(fba_daily))
        fba_slope, _ = np.polyfit(x_fba, fba_daily.values, 1)
        rec["ta_fba_trend_slope"] = float(fba_slope / rrp * 30 * 100)

        # FBA vs Amazon spread
        if len(amz_daily) >= 30:
            # Align dates
            common_idx = amz_daily.index.intersection(fba_daily.index)
            if len(common_idx) >= 10:
                amz_common = amz_daily[common_idx]
                fba_common = fba_daily[common_idx]
                spread = (fba_common - amz_common) / rrp * 100
                rec["ta_fba_amz_spread_mean"] = float(spread.mean())
                rec["ta_fba_amz_spread_trend"] = float(spread.iloc[-10:].mean() - spread.iloc[:10].mean())
                # Is spread widening? (bullish -- 3P pulling away from Amazon)
                if len(spread) >= 60:
                    rec["ta_fba_amz_spread_expanding"] = float(
                        spread.tail(30).mean() > spread.head(30).mean()
                    )

    ta_features[sn] = rec

print(f"Extracted TA features for {len(ta_features)} sets")
print(f"Skipped: {skipped}")

# Count features
all_feat_names = set()
for rec in ta_features.values():
    all_feat_names.update(rec.keys())
all_feat_names = sorted(all_feat_names)
print(f"Total TA features: {len(all_feat_names)}")


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRELATION WITH GROWTH (sorted by |r|)")
print("=" * 70)

# Match to training data
keepa_mask = df_raw["set_number"].isin(ta_features)
n_matched = keepa_mask.sum()
print(f"\nMatched to training: {n_matched}")

for feat in all_feat_names:
    df_feat[feat] = df_raw["set_number"].map(
        lambda sn, f=feat: ta_features.get(sn, {}).get(f, np.nan)
    )

y_kp = y_all[keepa_mask.values]
correlations = []
for feat in all_feat_names:
    vals = df_feat.loc[keepa_mask, feat].values.astype(float)
    valid = np.isfinite(vals) & np.isfinite(y_kp)
    n_valid = valid.sum()
    if n_valid >= 30:
        corr = np.corrcoef(vals[valid], y_kp[valid])[0, 1]
        coverage = n_valid / n_matched * 100
        correlations.append((feat, corr, n_valid, coverage))

correlations.sort(key=lambda x: abs(x[1]), reverse=True)

print(f"\n{'Feature':<35} {'Corr':>8} {'n':>6} {'Cov%':>6}")
print("-" * 60)
for feat, corr, n, cov in correlations[:40]:
    marker = " ***" if abs(corr) >= 0.10 else " *" if abs(corr) >= 0.05 else ""
    print(f"  {feat:<33} {corr:+.3f}  {n:>5}  {cov:>5.0f}%{marker}")

if len(correlations) > 40:
    weak = [c for c in correlations[40:] if abs(c[1]) < 0.05]
    print(f"\n  ... {len(weak)} more features with |r| < 0.05 (not shown)")


# ---------------------------------------------------------------------------
# CV test: T1 + best TA features
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CV TEST: T1 + TOP TA FEATURES")
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

    return {"name": name, "r2": np.mean(r2s), "std": np.std(r2s), "mae": np.mean(maes), "folds": r2s}


keepa_idx = np.where(keepa_mask.values)[0]
y_kp_cv = y_all[keepa_idx]
groups_kp = groups[keepa_idx]

# T1 baseline on Keepa subset
X_t1_kp = X_raw[t1_features].fillna(X_raw[t1_features].median()).iloc[keepa_idx].values
mono_t1 = [MONOTONIC_MAP.get(f, 0) for f in t1_features]

res_t1 = cv_score(X_t1_kp, y_kp_cv, groups_kp, "T1 only (Keepa subset)", monotonic=mono_t1)
print(f"\n  {res_t1['name']}: R2={res_t1['r2']:+.3f} +/- {res_t1['std']:.3f}  MAE={res_t1['mae']:.1f}%")

# Top TA features by |corr| > 0.08 with decent coverage
top_ta = [f for f, corr, n, cov in correlations if abs(corr) >= 0.08 and cov >= 60]
print(f"\nTop TA features (|r| >= 0.08, coverage >= 60%): {len(top_ta)}")

# Individual feature test (top 15)
print("\n  Individual feature contribution:")
individual_results = []
for ta_feat in top_ta[:15]:
    feats = list(t1_features) + [ta_feat]
    X_plus = df_feat[feats].copy()
    for c in X_plus.columns:
        X_plus[c] = pd.to_numeric(X_plus[c], errors="coerce")
    X_plus = X_plus.fillna(X_plus.median()).iloc[keepa_idx].values
    mono = [MONOTONIC_MAP.get(f, 0) for f in feats]
    res = cv_score(X_plus, y_kp_cv, groups_kp, f"+{ta_feat}", monotonic=mono)
    delta = res["r2"] - res_t1["r2"]
    marker = " !!!" if delta > 0.02 else " +" if delta > 0 else ""
    individual_results.append((ta_feat, res["r2"], delta))
    print(f"    {ta_feat:<33}: R2={res['r2']:+.3f} (delta={delta:+.3f}){marker}")

# Bucket test: all top features at once
if len(top_ta) >= 3:
    feats_all = list(t1_features) + top_ta
    X_all = df_feat[feats_all].copy()
    for c in X_all.columns:
        X_all[c] = pd.to_numeric(X_all[c], errors="coerce")
    X_all = X_all.fillna(X_all.median()).iloc[keepa_idx].values
    mono_all = [MONOTONIC_MAP.get(f, 0) for f in feats_all]
    res_all = cv_score(X_all, y_kp_cv, groups_kp, f"T1 + {len(top_ta)} TA features", monotonic=mono_all)
    print(f"\n  {res_all['name']}: R2={res_all['r2']:+.3f} (delta={res_all['r2'] - res_t1['r2']:+.3f})")

# Try ONLY features that improved individually
winners = [f for f, r2, d in individual_results if d > 0]
if winners:
    feats_win = list(t1_features) + winners
    X_win = df_feat[feats_win].copy()
    for c in X_win.columns:
        X_win[c] = pd.to_numeric(X_win[c], errors="coerce")
    X_win = X_win.fillna(X_win.median()).iloc[keepa_idx].values
    mono_win = [MONOTONIC_MAP.get(f, 0) for f in feats_win]
    res_win = cv_score(X_win, y_kp_cv, groups_kp, f"T1 + {len(winners)} winners only", monotonic=mono_win)
    print(f"  {res_win['name']}: R2={res_win['r2']:+.3f} (delta={res_win['r2'] - res_t1['r2']:+.3f})")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Categorize features by type
categories = {
    "Moving Averages": [c for c in correlations if c[0].startswith(("ta_sma", "ta_ema", "ta_price_vs_sma", "ta_golden", "ta_cross"))],
    "RSI": [c for c in correlations if "rsi" in c[0]],
    "MACD": [c for c in correlations if "macd" in c[0]],
    "Bollinger": [c for c in correlations if "bb" in c[0]],
    "Momentum/ROC": [c for c in correlations if c[0].startswith(("ta_roc", "ta_momentum"))],
    "Trend": [c for c in correlations if c[0].startswith(("ta_trend", "ta_adx"))],
    "Volatility": [c for c in correlations if "vol" in c[0]],
    "Support/Resistance": [c for c in correlations if c[0].startswith(("ta_support", "ta_resistance", "ta_price_position", "ta_at"))],
    "Price Distribution": [c for c in correlations if c[0].startswith(("ta_skew", "ta_kurt", "ta_pct_"))],
    "3P FBA TA": [c for c in correlations if "fba" in c[0]],
    "Donchian": [c for c in correlations if "donchian" in c[0]],
}

print(f"\n{'Category':<25} {'Best Feature':<33} {'Best |r|':>8}")
print("-" * 70)
for cat, feats in categories.items():
    if feats:
        best = max(feats, key=lambda x: abs(x[1]))
        print(f"  {cat:<23} {best[0]:<33} {abs(best[1]):.3f}")
    else:
        print(f"  {cat:<23} {'(no features)':33}")

print(f"\nTotal time: {time.time() - t0:.0f}s")
