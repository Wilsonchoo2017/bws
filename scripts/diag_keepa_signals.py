"""Diagnostic: Do unused Keepa signals (3P FBA, sales rank, buy box) help?

Loads full Keepa timelines, extracts kpt_* features via KeepaTimelineExtractor
logic, and tests their individual + combined impact on the regressor.

Run: python -m scripts.diag_keepa_signals
"""
from __future__ import annotations

import json
import logging
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_all():
    """Load training data + full Keepa timelines from Postgres."""
    from db.pg.engine import get_engine
    from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
    from services.ml.growth.feature_selection import select_features

    engine = get_engine()
    from services.ml.pg_queries import load_growth_training_data
    df_raw = load_growth_training_data(engine)

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
    )

    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y_all)
    )

    # Feature selection for T1
    t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X_raw = df_feat[t1_candidates].copy()
    for c in X_raw.columns:
        X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
    t1_features = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(t1_features) < 5:
        t1_features = t1_candidates

    X_t1 = X_raw[t1_features].fillna(X_raw[t1_features].median())

    groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
    finite = np.isfinite(year_retired)
    groups[finite] = year_retired[finite].astype(int)

    # Load FULL Keepa timelines (not just amazon_price_json)
    with engine.connect() as conn:
        keepa_full = pd.read_sql("""
            SELECT set_number, amazon_price_json, buy_box_json,
                   new_3p_fba_json, sales_rank_json, tracking_users
            FROM (
                SELECT DISTINCT ON (set_number) *
                FROM keepa_snapshots
                WHERE amazon_price_json IS NOT NULL
                ORDER BY set_number, scraped_at DESC
            ) sub
        """, conn)

    logger.info("Keepa full timelines: %d sets", len(keepa_full))
    logger.info("  amazon_price_json: %d non-null", keepa_full["amazon_price_json"].notna().sum())
    logger.info("  buy_box_json: %d non-null", keepa_full["buy_box_json"].notna().sum())
    logger.info("  new_3p_fba_json: %d non-null", keepa_full["new_3p_fba_json"].notna().sum())
    logger.info("  sales_rank_json: %d non-null", keepa_full["sales_rank_json"].notna().sum())

    return df_raw, df_feat, X_t1, y_all, groups, t1_features, keepa_full


# ---------------------------------------------------------------------------
# Feature extraction (inline, mirrors KeepaTimelineExtractor)
# ---------------------------------------------------------------------------

def _parse_json(raw: object) -> list[list]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _prices(timeline: list[list]) -> list[float]:
    return [float(p[1]) for p in timeline if len(p) >= 2 and p[1] is not None and p[1] > 0]


def extract_keepa_full_features(
    keepa_df: pd.DataFrame,
    rrp_lookup: dict[str, float],
    cutoff_lookup: dict[str, str | None],
) -> pd.DataFrame:
    """Extract all Keepa timeline features including 3P FBA, sales rank, buy box."""
    rows: list[dict] = []

    for _, kr in keepa_df.iterrows():
        sn = kr["set_number"]
        rrp = rrp_lookup.get(sn)
        if not rrp or rrp <= 0:
            continue

        rec: dict[str, object] = {"set_number": sn}
        cutoff = cutoff_lookup.get(sn)

        # --- Amazon price ---
        amz_tl = _parse_json(kr.get("amazon_price_json"))
        if cutoff:
            amz_tl = [p for p in amz_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
        amz_prices = _prices(amz_tl)

        if len(amz_prices) >= 3:
            amz_mean = float(np.mean(amz_prices))
            rec["kpt_price_cv"] = float(np.std(amz_prices) / amz_mean) if amz_mean > 0 else None
            rec["kpt_below_rrp_pct"] = sum(1 for p in amz_prices if p < rrp * 0.98) / len(amz_prices) * 100
            rec["kpt_avg_discount"] = (rrp - amz_mean) / rrp * 100
            rec["kpt_max_discount"] = (rrp - min(amz_prices)) / rrp * 100
            rec["kpt_median_discount"] = (rrp - float(np.median(amz_prices))) / rrp * 100

            if len(amz_prices) >= 6:
                q = max(1, len(amz_prices) // 4)
                early = float(np.mean(amz_prices[:q]))
                late = float(np.mean(amz_prices[-q:]))
                rec["kpt_price_trend"] = (late - early) / early * 100 if early > 0 else None
                rec["kpt_price_momentum"] = late / early if early > 0 else None

            # Stock-outs
            oos_count = 0
            in_oos = False
            in_stock_pts = 0
            total_pts = 0
            last_oos_date = None
            for point in amz_tl:
                if len(point) < 2:
                    continue
                total_pts += 1
                if point[1] is not None and point[1] > 0:
                    in_stock_pts += 1
                    in_oos = False
                elif not in_oos:
                    oos_count += 1
                    in_oos = True
                    last_oos_date = point[0] if isinstance(point[0], str) else None

            rec["kpt_stockout_count"] = float(oos_count)
            rec["kpt_stockout_pct"] = (1.0 - in_stock_pts / total_pts) * 100 if total_pts > 0 else None

            # Data extent
            dates = [p[0] for p in amz_tl if len(p) >= 2 and isinstance(p[0], str)]
            if len(dates) >= 2:
                try:
                    d1 = pd.to_datetime(dates[0])
                    d2 = pd.to_datetime(dates[-1])
                    rec["kpt_data_months"] = max(1.0, (d2 - d1).days / 30.0)
                    rec["kpt_months_in_stock"] = rec["kpt_data_months"] * (in_stock_pts / total_pts) if total_pts > 0 else None
                except (ValueError, TypeError):
                    pass

        # --- Buy box ---
        bb_tl = _parse_json(kr.get("buy_box_json"))
        if cutoff:
            bb_tl = [p for p in bb_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
        bb_prices = _prices(bb_tl)
        if bb_prices and rrp > 0:
            rec["kpt_bb_max_premium"] = (max(bb_prices) - rrp) / rrp * 100
            # Pre-retirement buy box vs RRP
            rec["kpt_bb_avg_vs_rrp"] = (float(np.mean(bb_prices)) - rrp) / rrp * 100
            rec["kpt_bb_cv"] = float(np.std(bb_prices) / np.mean(bb_prices)) if np.mean(bb_prices) > 0 else None

        # --- 3P FBA ---
        fba_tl = _parse_json(kr.get("new_3p_fba_json"))
        if cutoff:
            fba_tl = [p for p in fba_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
        fba_prices = _prices(fba_tl)
        if fba_prices:
            fba_mean = float(np.mean(fba_prices))
            rec["kpt_3p_fba_vs_rrp"] = (fba_mean - rrp) / rrp * 100
            rec["kpt_3p_price_cv"] = float(np.std(fba_prices) / fba_mean) if fba_mean > 0 else None
            if amz_prices:
                rec["kpt_3p_premium_pct"] = (fba_mean - float(np.mean(amz_prices))) / float(np.mean(amz_prices)) * 100
            # FBA above RRP = seller confidence
            rec["kpt_3p_above_rrp_pct"] = sum(1 for p in fba_prices if p > rrp * 1.02) / len(fba_prices) * 100

        # --- Sales rank ---
        rank_tl = _parse_json(kr.get("sales_rank_json"))
        if cutoff:
            rank_tl = [p for p in rank_tl if len(p) >= 2 and (not isinstance(p[0], str) or p[0][:7] <= cutoff)]
        ranks = _prices(rank_tl)
        if len(ranks) >= 3:
            rec["kpt_rank_median"] = float(np.median(ranks))
            rec["kpt_log_rank_median"] = float(np.log1p(np.median(ranks)))
            rank_mean = float(np.mean(ranks))
            rec["kpt_rank_cv"] = float(np.std(ranks) / rank_mean) if rank_mean > 0 else None
            if len(ranks) >= 6:
                q = max(1, len(ranks) // 4)
                early_r = float(np.mean(ranks[:q]))
                late_r = float(np.mean(ranks[-q:]))
                rec["kpt_rank_trend"] = (late_r - early_r) / early_r * 100 if early_r > 0 else None

        # Tracking users
        tu = kr.get("tracking_users")
        if pd.notna(tu) and tu and float(tu) > 0:
            rec["kpt_tracking_users"] = float(tu)
            rec["kpt_log_tracking"] = float(np.log1p(float(tu)))

        rows.append(rec)

    if not rows:
        return pd.DataFrame(columns=["set_number"])
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CV evaluation
# ---------------------------------------------------------------------------

def _cv_score(X_vals, y, groups, mono, name):
    from services.ml.growth.model_selection import build_model
    n_splits = min(5, len(set(groups)))
    splitter = GroupKFold(n_splits=n_splits)
    r2s, maes = [], []

    for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
        X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        lo, hi = np.percentile(y_tr, [1, 99])
        y_tr = np.clip(y_tr, lo, hi)

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        pt = PowerTransformer(method="yeo-johnson", standardize=False)
        y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()

        model = build_model()
        if mono:
            model.set_params(monotone_constraints=mono)
        model.fit(X_tr_s, y_tr_t)
        preds = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

        ss_res = np.sum((y_va - preds) ** 2)
        ss_tot = np.sum((y_va - y_va.mean()) ** 2)
        r2s.append(1 - ss_res / ss_tot if ss_tot > 0 else 0)
        maes.append(float(np.mean(np.abs(y_va - preds))))

    r2_mean = float(np.mean(r2s))
    r2_std = float(np.std(r2s))
    mae_mean = float(np.mean(maes))
    logger.info("  %-40s R2=%.3f +/-%.3f  MAE=%.1f%%  (n=%d)", name, r2_mean, r2_std, mae_mean, len(y))
    return r2_mean


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def diag_coverage_and_correlations(kpt_df, y_map):
    """Check coverage and raw correlations of Keepa features."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("1. KEEPA FEATURE COVERAGE & CORRELATIONS WITH GROWTH")
    logger.info("=" * 70)

    feat_cols = [c for c in kpt_df.columns if c != "set_number"]
    for col in sorted(feat_cols):
        valid = kpt_df[col].notna()
        n_valid = valid.sum()
        pct = n_valid / len(kpt_df) * 100

        # Correlation with growth
        matched = kpt_df[valid].merge(y_map, on="set_number", how="inner")
        if len(matched) > 10:
            r = float(np.corrcoef(matched[col].values, matched["y"].values)[0, 1])
        else:
            r = float("nan")

        logger.info("  %-30s n=%4d (%5.1f%%)  r=% .3f", col, n_valid, pct, r)


def diag_keepa_regressor_impact(
    X_t1, y_all, groups, t1_features, kpt_df, df_raw,
):
    """Test Keepa features on the subset with Keepa data."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("2. REGRESSOR IMPACT (Keepa subset only)")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import _get_monotonic_constraints

    # Merge Keepa features with training data
    sn_to_idx = {sn: i for i, sn in enumerate(df_raw["set_number"])}
    keepa_sns = set(kpt_df["set_number"])
    keepa_idx = [sn_to_idx[sn] for sn in df_raw["set_number"] if sn in keepa_sns]

    if len(keepa_idx) < 50:
        logger.info("  Too few Keepa sets (%d), skipping", len(keepa_idx))
        return

    keepa_idx = np.array(keepa_idx)
    y_kp = y_all[keepa_idx]
    groups_kp = groups[keepa_idx]
    X_t1_kp = X_t1.iloc[keepa_idx].values

    logger.info("  Keepa subset: %d sets (of %d total)", len(keepa_idx), len(y_all))

    # Baseline: T1 only on Keepa subset
    mono_t1 = _get_monotonic_constraints(t1_features)
    r2_base = _cv_score(X_t1_kp, y_kp, groups_kp, mono_t1, "T1 only (Keepa subset)")

    # Cherry-pick promising Keepa features (coverage >= 40%, |r| >= 0.03)
    y_map = pd.DataFrame({"set_number": df_raw["set_number"].values, "y": y_all})
    feat_cols = [c for c in kpt_df.columns if c != "set_number"]

    promising = []
    for col in feat_cols:
        valid = kpt_df[col].notna()
        coverage = valid.sum() / len(kpt_df)
        if coverage < 0.40:
            continue
        matched = kpt_df[valid].merge(y_map, on="set_number", how="inner")
        if len(matched) < 20:
            continue
        r = abs(float(np.corrcoef(matched[col].values, matched["y"].values)[0, 1]))
        if r >= 0.03:
            promising.append((col, r, coverage))

    promising.sort(key=lambda x: -x[1])
    logger.info("")
    logger.info("  Promising Keepa features (coverage>=40%%, |r|>=0.03):")
    for col, r, cov in promising:
        logger.info("    %-30s r=%.3f  coverage=%.0f%%", col, r, cov * 100)

    if not promising:
        logger.info("  No promising features found!")
        return

    # Test individual features
    logger.info("")
    logger.info("  --- Individual feature impact ---")
    kpt_merged = kpt_df.set_index("set_number")
    sns_ordered = df_raw["set_number"].values[keepa_idx]

    for col, r, cov in promising[:8]:
        kpt_vals = kpt_merged.reindex(sns_ordered)[col].values.astype(float)
        fill = float(np.nanmedian(kpt_vals))
        kpt_vals = np.where(np.isnan(kpt_vals), fill, kpt_vals)

        X_plus = np.column_stack([X_t1_kp, kpt_vals])
        feat_list = t1_features + [col]
        mono_plus = _get_monotonic_constraints(feat_list)
        _cv_score(X_plus, y_kp, groups_kp, mono_plus, f"T1 + {col}")

    # Test all promising combined
    logger.info("")
    logger.info("  --- All promising combined ---")
    extra_cols = []
    for col, r, cov in promising:
        kpt_vals = kpt_merged.reindex(sns_ordered)[col].values.astype(float)
        fill = float(np.nanmedian(kpt_vals))
        extra_cols.append(np.where(np.isnan(kpt_vals), fill, kpt_vals))

    X_combined = np.column_stack([X_t1_kp] + extra_cols)
    combined_feats = t1_features + [c for c, _, _ in promising]
    mono_combined = _get_monotonic_constraints(combined_feats)
    r2_combined = _cv_score(X_combined, y_kp, groups_kp, mono_combined, "T1 + all promising Keepa")

    logger.info("")
    logger.info("  Delta R2 (combined vs T1-only): %+.4f", r2_combined - r2_base)


def diag_feature_importance_with_keepa(
    X_t1, y_all, groups, t1_features, kpt_df, df_raw,
):
    """Feature importance when Keepa features are included."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("3. FEATURE IMPORTANCE WITH KEEPA")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints

    sn_to_idx = {sn: i for i, sn in enumerate(df_raw["set_number"])}
    keepa_sns = set(kpt_df["set_number"])
    keepa_idx = np.array([sn_to_idx[sn] for sn in df_raw["set_number"] if sn in keepa_sns])

    if len(keepa_idx) < 50:
        return

    y_kp = y_all[keepa_idx]
    X_t1_kp = X_t1.iloc[keepa_idx].values
    sns_ordered = df_raw["set_number"].values[keepa_idx]

    # Add all Keepa features with decent coverage
    kpt_merged = kpt_df.set_index("set_number")
    feat_cols = [c for c in kpt_df.columns if c != "set_number"]
    added_cols = []
    added_names = []
    for col in feat_cols:
        vals = kpt_merged.reindex(sns_ordered)[col].values.astype(float)
        if np.isnan(vals).sum() / len(vals) > 0.70:
            continue
        fill = float(np.nanmedian(vals))
        added_cols.append(np.where(np.isnan(vals), fill, vals))
        added_names.append(col)

    if not added_cols:
        logger.info("  No Keepa features with sufficient coverage")
        return

    X_all = np.column_stack([X_t1_kp] + added_cols)
    all_feats = t1_features + added_names

    lo, hi = np.percentile(y_kp, [1, 99])
    y_w = np.clip(y_kp, lo, hi)

    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_all)
    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_t = pt.fit_transform(y_w.reshape(-1, 1)).ravel()

    mono = _get_monotonic_constraints(all_feats)
    model = build_model()
    if mono:
        model.set_params(monotone_constraints=mono)
    model.fit(X_s, y_t)

    importances = model.feature_importances_
    pairs = sorted(zip(all_feats, importances), key=lambda x: -x[1])

    for feat, imp in pairs[:25]:
        marker = " <-- KEEPA" if feat.startswith("kpt_") else ""
        logger.info("  %-30s %6.1f%s", feat, imp, marker)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    logger.info("Keepa Signals Diagnostic: 3P FBA, Sales Rank, Buy Box")
    logger.info("=" * 70)

    df_raw, df_feat, X_t1, y_all, groups, t1_features, keepa_full = _load_all()
    logger.info("Training data: %d sets, T1 features: %d", len(y_all), len(t1_features))

    # Build RRP and cutoff lookups
    rrp_lookup = dict(zip(
        df_raw["set_number"],
        pd.to_numeric(df_raw["rrp_usd_cents"], errors="coerce").fillna(0),
    ))

    # Cutoff: use retirement date - 1 month to prevent leakage
    cutoff_lookup: dict[str, str | None] = {}
    for _, row in df_raw.iterrows():
        rd = row.get("retired_date")
        if pd.notna(rd):
            try:
                dt = pd.to_datetime(rd)
                cutoff_lookup[row["set_number"]] = f"{dt.year:04d}-{dt.month:02d}"
            except (ValueError, TypeError):
                cutoff_lookup[row["set_number"]] = None
        else:
            yr = row.get("year_retired")
            if pd.notna(yr):
                cutoff_lookup[row["set_number"]] = f"{int(yr):04d}-06"
            else:
                cutoff_lookup[row["set_number"]] = None

    # Extract full Keepa features
    kpt_df = extract_keepa_full_features(keepa_full, rrp_lookup, cutoff_lookup)
    logger.info("Keepa features extracted for %d sets", len(kpt_df))

    # Build growth lookup
    y_map = pd.DataFrame({"set_number": df_raw["set_number"].values, "y": y_all})

    diag_coverage_and_correlations(kpt_df, y_map)
    diag_keepa_regressor_impact(X_t1, y_all, groups, t1_features, kpt_df, df_raw)
    diag_feature_importance_with_keepa(X_t1, y_all, groups, t1_features, kpt_df, df_raw)

    elapsed = time.time() - t0
    logger.info("")
    logger.info("=" * 70)
    logger.info("DONE in %.0f seconds", elapsed)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
