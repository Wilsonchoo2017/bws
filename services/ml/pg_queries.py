"""PostgreSQL data access for the ML pipeline.

Primary data layer for model training.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _read(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


def load_current_market_prices(engine: Engine) -> dict[str, tuple[float, float]]:
    """Return {set_number: (current_usd_cents, rrp_usd_cents)} for retired sets.

    Uses the same trailing-6-month volume-weighted BL sold-price computation
    as the effective-APR ground truth so entry-price gates match the target
    the classifier was trained against.

    Only returns sets with both a current sold price and a known RRP —
    we can't compute the ratio otherwise.
    """
    from datetime import date

    from services.ml.currency import to_usd_cents

    current_year = date.today().year
    sql = """
        WITH recent_sales AS (
            SELECT
                ms.set_number,
                ms.avg_price,
                ms.times_sold
            FROM bricklink_monthly_sales ms
            WHERE ms.condition = 'new'
              AND ms.avg_price IS NOT NULL
              AND ms.avg_price > 0
              AND ms.times_sold IS NOT NULL
              AND ms.times_sold > 0
              AND (ms.year * 12 + ms.month)
                  >= (EXTRACT(YEAR FROM CURRENT_DATE)::INT * 12
                      + EXTRACT(MONTH FROM CURRENT_DATE)::INT - 6)
        ),
        weighted AS (
            SELECT
                set_number,
                SUM(avg_price::BIGINT * times_sold) AS sum_price_x_qty,
                SUM(times_sold) AS total_qty
            FROM recent_sales
            GROUP BY set_number
        )
        SELECT
            w.set_number,
            (w.sum_price_x_qty::FLOAT / w.total_qty) AS weighted_avg_myr_cents,
            be.rrp_usd_cents
        FROM weighted w
        JOIN (
            SELECT DISTINCT ON (set_number) set_number, rrp_usd_cents
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents > 0
            ORDER BY set_number, scraped_at DESC
        ) be ON be.set_number = w.set_number
    """
    df = _read(engine, sql)
    result: dict[str, tuple[float, float]] = {}
    for _, row in df.iterrows():
        myr = float(row["weighted_avg_myr_cents"])
        rrp = float(row["rrp_usd_cents"])
        if myr <= 0 or rrp <= 0:
            continue
        usd = to_usd_cents(myr, "MYR", current_year)
        if usd is None or usd <= 0:
            continue
        result[str(row["set_number"])] = (float(usd), rrp)
    return result


def load_growth_training_data(engine: Engine) -> pd.DataFrame:
    """Load all sets with BrickEconomy growth data for training."""
    return _read(engine, """
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            be.annual_growth_pct, be.rrp_usd_cents, be.rating_value,
            be.review_count, be.pieces, be.minifigs,
            be.rrp_gbp_cents, be.rrp_eur_cents, be.rrp_cad_cents, be.rrp_aud_cents,
            be.subtheme,
            be.distribution_mean_cents, be.distribution_stddev_cents,
            be.minifig_value_cents, be.exclusive_minifigs,
            be.designer,
            COALESCE(li.year_released, be.year_released) AS year_released,
            COALESCE(
                li.year_retired,
                be.year_retired,
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date,
            CAST(COALESCE(li.retired_date, be.retired_date) AS TEXT) AS retired_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
    """)


def load_keepa_bl_training_data(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Load training data for the Keepa+BL model.

    Returns:
        (base_df, keepa_df, target_series)
        - base_df: Factual metadata (theme, pieces, RRP, etc.)
        - keepa_df: Keepa timelines
        - target_series: BL current new price / RRP ratio, indexed by set_number
    """
    base_df = _read(engine, """
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            be.subtheme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            be.rrp_usd_cents,
            be.rrp_gbp_cents, be.rrp_eur_cents,
            be.rrp_cad_cents, be.rrp_aud_cents,
            be.minifig_value_cents,
            be.exclusive_minifigs,
            COALESCE(li.year_released, be.year_released) AS year_released,
            COALESCE(
                li.year_retired,
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(
                li.retired_date,
                be.retired_date,
                CASE WHEN li.year_retired IS NOT NULL
                     THEN (li.year_retired::TEXT || '-07-01')::DATE
                END
            ) AS TEXT) AS retired_date,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """)

    keepa_df = _read(engine, """
        SELECT set_number, amazon_price_json, new_3p_fba_json,
               new_3p_fbm_json, buy_box_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) sub
    """)

    # BL current new price as target
    bl_df = _read(engine, """
        SELECT
            DISTINCT ON (set_number) set_number, current_new
        FROM bricklink_price_history
        ORDER BY set_number, scraped_at DESC
    """)

    # Extract price and compute ratio
    import numpy as np

    from datetime import date as _date
    from services.ml.currency import to_usd_cents

    target_data: dict[str, float] = {}
    rrp_lookup = dict(zip(base_df["set_number"], base_df["rrp_usd_cents"]))
    current_year = _date.today().year

    for _, row in bl_df.iterrows():
        sn = str(row["set_number"])
        rrp = rrp_lookup.get(sn)
        if not rrp or rrp <= 0:
            continue
        cn = row.get("current_new")
        if not isinstance(cn, dict):
            continue
        for key in ("qty_avg_price", "avg_price"):
            val = cn.get(key)
            if isinstance(val, dict) and val.get("amount") and val["amount"] > 0:
                currency = val.get("currency") or "MYR"
                usd_cents = to_usd_cents(float(val["amount"]), currency, current_year)
                if usd_cents is None:
                    continue
                target_data[sn] = float(usd_cents) / float(rrp)
                break

    target_series = pd.Series(target_data, name="bl_vs_rrp")
    return base_df, keepa_df, target_series


# Effective-APR tuning constants.
#
# The raw whole-set APR understates returns for two Malaysia-specific
# realities the pre-Exp-40 target ignored:
#
#   1. Parted-out fallback. For sets like 76173 (Ghost Rider/Carnage) where
#      minifigs alone carry >40% of RRP, parting out IS the exit strategy
#      when the whole-set doesn't move. Floor the APR by the minifig-only
#      APR, discounted for BL fees + shipping + effort.
#
#   2. Time-to-exit. A 6% APR set that clears in 2 weeks beats a 12% set
#      that sits for 18 months (compounding + opportunity cost). Apply a
#      pct-point penalty tiered on trailing-12m sales velocity.
#
# These are domain-reasoned defaults. Calibrate on the 2024 fold later.
_PARTED_OUT_FEE_FACTOR = 0.85    # BL 3% fees + modest handling/packaging
_PARTED_OUT_MIN_RATIO = 0.40     # only floor when minifigs ≥40% of RRP

# Freshness gate: a set needs at least this many years of post-retirement
# history before its APR is honest. Sets retired within the last year have
# a tiny denominator in the annualization formula, producing enormous
# ((1+r)^(1/0.25) - 1) figures even on small raw moves. The 0-0.5y bucket
# had p99 APR = 521% vs the 3-5y bucket's 42% — that's the artifact, not
# signal. Sets under this gate get NO effective APR (excluded from training
# and evaluation, not zeroed).
_MIN_YEARS_SINCE_RETIREMENT = 1.0

# Hard cap on effective APR in both directions. Catches residual outliers
# from data quirks (wrong retired_date, currency conversion glitch, etc).
_APR_CAP_UPPER = 200.0
_APR_CAP_LOWER = -100.0
_LIQUIDITY_PENALTY_TIERS: tuple[tuple[float, float], ...] = (
    # (min sales/month, pct-point penalty on APR)
    (2.0, 0.0),    # ≥2/mo: liquid
    (0.5, 1.5),    # ≥0.5/mo: slow
    (0.1, 4.0),    # ≥0.1/mo: illiquid
    (0.0, 7.0),    # <0.1/mo: dead stock
)


def _liquidity_penalty_pct(sales_per_month: float | None) -> float:
    """Return APR penalty (pct points) for a given sales velocity.

    Returns 0 for missing data (we don't double-penalize sets that merely
    lack monthly-sales coverage — missingness is already handled by the
    classifier features).
    """
    if sales_per_month is None or sales_per_month < 0:
        return 0.0
    for threshold, penalty in _LIQUIDITY_PENALTY_TIERS:
        if sales_per_month >= threshold:
            return penalty
    return _LIQUIDITY_PENALTY_TIERS[-1][1]


def _parted_out_apr(
    minifig_total_usd_cents: float,
    rrp_usd_cents: float,
    years: float,
) -> float | None:
    """Annualized return if the set were fully parted out, fees included."""
    if rrp_usd_cents <= 0 or minifig_total_usd_cents <= 0 or years <= 0:
        return None
    adjusted = minifig_total_usd_cents * _PARTED_OUT_FEE_FACTOR
    raw = adjusted / rrp_usd_cents - 1.0
    if raw <= -1.0:
        return -100.0
    return ((1.0 + raw) ** (1.0 / years) - 1.0) * 100.0


def _load_minifig_totals(engine: Engine) -> dict[str, float]:
    """Return {set_number: sum of latest minifig prices, USD cents}."""
    from services.ml.growth.minifig_value_features import load_minifig_value_features

    df = load_minifig_value_features(engine)
    if df.empty or "minifig_value_total_usd" not in df.columns:
        return {}
    return {
        str(sn): float(val)
        for sn, val in zip(df["set_number"], df["minifig_value_total_usd"])
        if val is not None and float(val) > 0
    }


def _load_velocity_per_month(engine: Engine) -> dict[str, float]:
    """Return {set_number: trailing-12m sales per month}."""
    from services.ml.growth.sales_velocity_features import load_sales_velocity_features

    df = load_sales_velocity_features(engine)
    if df.empty or "bl_sales_per_month_12m" not in df.columns:
        return {}
    return {
        str(sn): float(val)
        for sn, val in zip(df["set_number"], df["bl_sales_per_month_12m"])
        if val is not None
    }


def load_bl_ground_truth(engine: Engine) -> dict[str, float]:
    """Compute effective Malaysia-exit annualized returns for retired sets.

    The return for each set is:

        effective_apr = max(whole_set_apr, parted_out_apr) - liquidity_penalty

    Where:
      - whole_set_apr comes from BL sold prices (primary), BL listings
        (fallback 1), or Keepa 3P FBA (fallback 2).
      - parted_out_apr is floored in only when minifig_value / RRP ≥ 40%
        and the parted-out path (after fees) beats the whole-set path.
      - liquidity_penalty is a pct-point drag tied to trailing-12m sales
        velocity (0 if ≥2/mo, up to 7 if <0.1/mo).

    This is the industry-standard "align label with business objective"
    move — the classifier still learns a single APR target, but the target
    encodes Malaysia-exit reality (can-I-sell, how-fast, and salvage-via-
    parting-out) instead of headline whole-set returns only.

    Only includes sets with a known retired_date so the return can be
    annualized: ((price/rrp)^(1/years) - 1) * 100.

    Returns:
        dict mapping set_number -> effective annualized return (pct).
    """
    import json
    from datetime import date

    from services.ml.currency import to_usd_cents

    today = date.today()
    current_year = today.year
    # Trailing window for sold-price average. Volume-weighted so fat months
    # dominate thin ones — reduces noise from the occasional 1-copy month.
    SALES_MONTHS = 6

    # Primary: bricklink_monthly_sales — volume-weighted trailing-window avg
    # of condition='new' sold prices, joined to BE RRP + retired_date.
    sales_df = _read(engine, f"""
        WITH recent_sales AS (
            SELECT
                ms.set_number,
                ms.avg_price,
                ms.times_sold,
                (ms.year * 12 + ms.month) AS period_key
            FROM bricklink_monthly_sales ms
            WHERE ms.condition = 'new'
              AND ms.avg_price IS NOT NULL
              AND ms.avg_price > 0
              AND ms.times_sold IS NOT NULL
              AND ms.times_sold > 0
              AND (ms.year * 12 + ms.month)
                  >= (EXTRACT(YEAR FROM CURRENT_DATE)::INT * 12
                      + EXTRACT(MONTH FROM CURRENT_DATE)::INT - {SALES_MONTHS})
        ),
        weighted AS (
            SELECT
                set_number,
                SUM(avg_price::BIGINT * times_sold) AS sum_price_x_qty,
                SUM(times_sold) AS total_qty
            FROM recent_sales
            GROUP BY set_number
        )
        SELECT
            w.set_number,
            (w.sum_price_x_qty::FLOAT / w.total_qty) AS weighted_avg_myr_cents,
            w.total_qty AS trailing_qty,
            be.rrp_usd_cents,
            CAST(COALESCE(
                be.retired_date,
                li.retired_date,
                CASE WHEN li.year_retired IS NOT NULL
                     THEN (li.year_retired::TEXT || '-07-01')::DATE
                END,
                CASE WHEN be.year_retired IS NOT NULL
                     THEN (be.year_retired::TEXT || '-07-01')::DATE
                END
            ) AS TEXT) AS retired_date
        FROM weighted w
        JOIN (
            SELECT DISTINCT ON (set_number) set_number, rrp_usd_cents,
                   retired_date, year_retired
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents > 0
            ORDER BY set_number, scraped_at DESC
        ) be ON be.set_number = w.set_number
        LEFT JOIN lego_items li ON li.set_number = w.set_number
        WHERE COALESCE(
            be.retired_date, li.retired_date,
            CASE WHEN li.year_retired IS NOT NULL
                 THEN (li.year_retired::TEXT || '-07-01')::DATE END,
            CASE WHEN be.year_retired IS NOT NULL
                 THEN (be.year_retired::TEXT || '-07-01')::DATE END
        ) IS NOT NULL
    """)

    result: dict[str, float] = {}
    # Per-set (years, rrp_usd_cents) — needed for the effective-APR pass
    # below so we can compute parted-out APR with the same time horizon.
    meta: dict[str, tuple[float, float]] = {}

    for _, row in sales_df.iterrows():
        price_myr = float(row["weighted_avg_myr_cents"])
        rrp = float(row["rrp_usd_cents"])
        if rrp <= 0 or price_myr <= 0:
            continue

        usd_cents = to_usd_cents(price_myr, "MYR", current_year)
        if usd_cents is None or usd_cents <= 0:
            continue
        raw_return = float(usd_cents) / rrp - 1.0

        try:
            rd = pd.to_datetime(row["retired_date"]).date()
        except Exception:
            continue
        # Freshness gate + annualization-stability floor.
        raw_years = (today - rd).days / 365.25
        if raw_years < _MIN_YEARS_SINCE_RETIREMENT:
            continue
        # Floor years at 1.0 so the annualization denominator is never tiny
        # (the 0-0.5y bucket had p99 APR = 521% before this floor).
        years = max(raw_years, 1.0)

        if raw_return > -1.0:
            ann = ((1.0 + raw_return) ** (1.0 / years) - 1.0) * 100.0
        else:
            ann = -100.0
        # Clamp to sane range — residual outliers from data quirks (wrong
        # retired_date, FX glitches) can still produce 500%+ figures.
        ann = max(_APR_CAP_LOWER, min(_APR_CAP_UPPER, ann))

        sn = row["set_number"]
        result[sn] = ann
        meta[sn] = (years, rrp)

    n_sales = len(result)

    # Fallback 1: BL current_new listings — covers sets without trailing-6m sales.
    bl_df = _read(engine, """
        SELECT
            bl.set_number,
            bl.current_new,
            be.rrp_usd_cents,
            CAST(COALESCE(
                be.retired_date,
                li.retired_date,
                CASE WHEN li.year_retired IS NOT NULL
                     THEN (li.year_retired::TEXT || '-07-01')::DATE
                END,
                CASE WHEN be.year_retired IS NOT NULL
                     THEN (be.year_retired::TEXT || '-07-01')::DATE
                END
            ) AS TEXT) AS retired_date
        FROM (
            SELECT DISTINCT ON (set_number) set_number, current_new
            FROM bricklink_price_history
            ORDER BY set_number, scraped_at DESC
        ) bl
        JOIN (
            SELECT DISTINCT ON (set_number) set_number, rrp_usd_cents, retired_date, year_retired
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents > 0
            ORDER BY set_number, scraped_at DESC
        ) be ON be.set_number = bl.set_number
        LEFT JOIN lego_items li ON li.set_number = bl.set_number
        WHERE COALESCE(
            be.retired_date, li.retired_date,
            CASE WHEN li.year_retired IS NOT NULL
                 THEN (li.year_retired::TEXT || '-07-01')::DATE END,
            CASE WHEN be.year_retired IS NOT NULL
                 THEN (be.year_retired::TEXT || '-07-01')::DATE END
        ) IS NOT NULL
    """)

    for _, row in bl_df.iterrows():
        sn = row["set_number"]
        if sn in result:
            continue  # monthly sales wins

        cn = row["current_new"]
        if isinstance(cn, str):
            try:
                cn = json.loads(cn)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(cn, dict):
            continue

        price_amt = None
        price_currency = "MYR"
        for key in ("qty_avg_price", "avg_price"):
            val = cn.get(key, {})
            if isinstance(val, dict) and val.get("amount") and val["amount"] > 0:
                price_amt = float(val["amount"])
                price_currency = val.get("currency") or "MYR"
                break
        if price_amt is None:
            continue

        usd_cents = to_usd_cents(price_amt, price_currency, current_year)
        if usd_cents is None or usd_cents <= 0:
            continue
        rrp = float(row["rrp_usd_cents"])
        if rrp <= 0:
            continue

        raw_return = float(usd_cents) / rrp - 1.0

        try:
            rd = pd.to_datetime(row["retired_date"]).date()
        except Exception:
            continue
        # Freshness gate + annualization-stability floor.
        raw_years = (today - rd).days / 365.25
        if raw_years < _MIN_YEARS_SINCE_RETIREMENT:
            continue
        # Floor years at 1.0 so the annualization denominator is never tiny
        # (the 0-0.5y bucket had p99 APR = 521% before this floor).
        years = max(raw_years, 1.0)

        if raw_return > -1.0:
            ann = ((1.0 + raw_return) ** (1.0 / years) - 1.0) * 100.0
        else:
            ann = -100.0
        # Clamp to sane range — residual outliers from data quirks (wrong
        # retired_date, FX glitches) can still produce 500%+ figures.
        ann = max(_APR_CAP_LOWER, min(_APR_CAP_UPPER, ann))

        result[sn] = ann
        meta[sn] = (years, rrp)

    bl_set_numbers = set(result.keys())
    n_listings = len(result) - n_sales

    # Keepa 3P FBA fallback for retired sets not in BL
    kp_df = _read(engine, """
        SELECT
            ks.set_number,
            ks.new_3p_fba_json,
            be.rrp_usd_cents,
            CAST(COALESCE(
                be.retired_date,
                li.retired_date,
                CASE WHEN li.year_retired IS NOT NULL
                     THEN (li.year_retired::TEXT || '-07-01')::DATE
                END,
                CASE WHEN be.year_retired IS NOT NULL
                     THEN (be.year_retired::TEXT || '-07-01')::DATE
                END
            ) AS TEXT) AS retired_date
        FROM (
            SELECT DISTINCT ON (set_number) set_number, new_3p_fba_json
            FROM keepa_snapshots
            WHERE new_3p_fba_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) ks
        JOIN (
            SELECT DISTINCT ON (set_number) set_number, rrp_usd_cents, retired_date, year_retired
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents > 0
            ORDER BY set_number, scraped_at DESC
        ) be ON be.set_number = ks.set_number
        LEFT JOIN lego_items li ON li.set_number = ks.set_number
        WHERE COALESCE(
            be.retired_date, li.retired_date,
            CASE WHEN li.year_retired IS NOT NULL
                 THEN (li.year_retired::TEXT || '-07-01')::DATE END,
            CASE WHEN be.year_retired IS NOT NULL
                 THEN (be.year_retired::TEXT || '-07-01')::DATE END
        ) IS NOT NULL
    """)

    for _, row in kp_df.iterrows():
        sn = row["set_number"]
        if sn in bl_set_numbers:
            continue  # BL is primary

        fba_json = row["new_3p_fba_json"]
        if isinstance(fba_json, str):
            try:
                fba_json = json.loads(fba_json)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(fba_json, list) or len(fba_json) == 0:
            continue

        # Latest non-null 3P FBA price (already in USD cents from Keepa)
        latest_price = None
        for entry in reversed(fba_json):
            if isinstance(entry, list) and len(entry) >= 2 and entry[1] is not None:
                latest_price = float(entry[1])
                break
        if latest_price is None or latest_price <= 0:
            continue

        rrp = float(row["rrp_usd_cents"])
        if rrp <= 0:
            continue

        raw_return = latest_price / rrp - 1.0

        try:
            rd = pd.to_datetime(row["retired_date"]).date()
        except Exception:
            continue
        # Freshness gate + annualization-stability floor.
        raw_years = (today - rd).days / 365.25
        if raw_years < _MIN_YEARS_SINCE_RETIREMENT:
            continue
        # Floor years at 1.0 so the annualization denominator is never tiny
        # (the 0-0.5y bucket had p99 APR = 521% before this floor).
        years = max(raw_years, 1.0)

        if raw_return > -1.0:
            ann = ((1.0 + raw_return) ** (1.0 / years) - 1.0) * 100.0
        else:
            ann = -100.0
        # Clamp to sane range — residual outliers from data quirks (wrong
        # retired_date, FX glitches) can still produce 500%+ figures.
        ann = max(_APR_CAP_LOWER, min(_APR_CAP_UPPER, ann))

        result[sn] = ann
        meta[sn] = (years, rrp)

    logger.info(
        "BL ground truth (raw whole-set APR): %d sets "
        "(%d sold, %d listings, %d Keepa fallback)",
        len(result), n_sales, n_listings,
        len(result) - len(bl_set_numbers),
    )

    # ------------------------------------------------------------------
    # Effective-APR pass: parted-out floor + liquidity penalty.
    # ------------------------------------------------------------------
    minifig_totals = _load_minifig_totals(engine)
    velocity_map = _load_velocity_per_month(engine)

    effective: dict[str, float] = {}
    n_floored = 0
    n_penalized = 0
    raw_mean = sum(result.values()) / len(result) if result else 0.0
    for sn, base_apr in result.items():
        years, rrp = meta[sn]
        adjusted_apr = base_apr

        # Parted-out floor: only kicks in when minifigs carry serious value
        # (≥40% of RRP) AND the parted-out APR strictly beats the whole-set.
        mf_total = minifig_totals.get(sn, 0.0)
        mf_ratio = (mf_total / rrp) if rrp > 0 else 0.0
        if mf_ratio >= _PARTED_OUT_MIN_RATIO:
            parted_apr = _parted_out_apr(mf_total, rrp, years)
            if parted_apr is not None and parted_apr > adjusted_apr:
                adjusted_apr = parted_apr
                n_floored += 1

        # Liquidity penalty: tiered pct-point drag on APR. Neutral (0) for
        # sets with no monthly-sales coverage — missingness is already a
        # first-class feature in the classifier.
        velocity = velocity_map.get(sn)
        penalty = _liquidity_penalty_pct(velocity)
        if penalty > 0:
            n_penalized += 1
            adjusted_apr -= penalty

        # Final clamp — the parted-out floor can overshoot the cap above
        # (minifig-heavy fresh retirees), and the penalty can push beyond
        # the lower bound for already-negative sets.
        effective[sn] = max(_APR_CAP_LOWER, min(_APR_CAP_UPPER, adjusted_apr))

    eff_mean = sum(effective.values()) / len(effective) if effective else 0.0
    eff_avoid_rate = (
        sum(1 for v in effective.values() if v < 10.0) / len(effective)
        if effective else 0.0
    )
    logger.info(
        "Effective APR: %d sets | parted-out floor: %d | liquidity-penalized: %d | "
        "mean %.2f%% -> %.2f%% | avoid rate (<10%%): %.1f%%",
        len(effective), n_floored, n_penalized,
        raw_mean, eff_mean, eff_avoid_rate * 100.0,
    )
    return effective


def load_google_trends_data(engine: Engine) -> pd.DataFrame:
    """Load Google Trends snapshots (YouTube search property).

    Returns DataFrame with set_number, interest_json, peak_value, average_value.
    One row per set (latest snapshot).
    """
    return _read(engine, """
        SELECT set_number, interest_json, peak_value, average_value
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM google_trends_snapshots
            WHERE search_property = 'youtube'
            ORDER BY set_number, scraped_at DESC
        ) sub
    """)


def load_keepa_timelines(engine: Engine) -> pd.DataFrame:
    """Load Keepa historical price timeline data."""
    return _read(engine, """
        SELECT set_number, amazon_price_json, buy_box_json,
               new_3p_fba_json, new_3p_fbm_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) sub
    """)


def load_growth_candidate_sets(engine: Engine) -> pd.DataFrame:
    """Load sets eligible for growth prediction."""
    return _read(engine, """
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            COALESCE(li.retiring_soon, be.retiring_soon) AS retiring_soon,
            be.rrp_usd_cents, be.rating_value, be.review_count,
            be.pieces, be.minifigs,
            be.rrp_gbp_cents, be.rrp_eur_cents, be.rrp_cad_cents, be.rrp_aud_cents,
            be.subtheme,
            be.distribution_mean_cents, be.distribution_stddev_cents,
            be.minifig_value_cents, be.exclusive_minifigs,
            be.designer,
            COALESCE(li.year_released, be.year_released) AS year_released,
            COALESCE(
                li.year_retired,
                be.year_retired,
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(li.release_date, be.release_date) AS TEXT) AS release_date,
            CAST(COALESCE(li.retired_date, be.retired_date) AS TEXT) AS retired_date
        FROM lego_items li
        JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """)


def load_base_metadata(
    engine: Engine,
    set_numbers: list[str] | None = None,
) -> pd.DataFrame:
    """Load core set metadata needed for feature extraction."""
    where_clause = ""
    if set_numbers:
        placeholders = ", ".join(f"'{s}'" for s in set_numbers)
        where_clause = f"WHERE li.set_number IN ({placeholders})"

    return _read(engine, f"""
        SELECT
            li.set_number,
            COALESCE(NULLIF(li.title, ''), be.title) AS title,
            COALESCE(li.theme, be.theme) AS theme,
            CASE
                WHEN li.year_released IS NOT NULL AND li.year_released <= 2026
                    THEN li.year_released
                WHEN be.year_released IS NOT NULL
                    THEN be.year_released
                ELSE li.year_released
            END AS year_released,
            COALESCE(
                li.year_retired,
                be.year_retired,
                EXTRACT(YEAR FROM COALESCE(li.retired_date, be.retired_date))::INTEGER
            ) AS year_retired,
            CAST(COALESCE(li.retired_date, be.retired_date) AS TEXT) AS retired_date,
            COALESCE(be.pieces, li.parts_count) AS parts_count,
            COALESCE(be.minifigs, li.minifig_count) AS minifig_count,
            COALESCE(li.retiring_soon, be.retiring_soon) AS retiring_soon
        FROM lego_items li
        LEFT JOIN (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) be ON li.set_number = be.set_number
        {where_clause}
        ORDER BY li.set_number
    """)
