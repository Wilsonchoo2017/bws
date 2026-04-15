"""Minifig-value-ratio features for the growth model.

For sets where the minifigs alone account for a high % of RRP, the set is
effectively a vehicle for parted-out arbitrage — Ghost Rider, Carnage,
licensed exclusives, etc. The classifier needs to see this ratio explicitly,
otherwise it relies on the long-term whole-set APR target which understates
parted-out value.

Price signal: **midpoint blend of `avg_price` and `max_price`** from
`current_new` listings. Rationale:

  - `avg_price` alone systematically understates retail for in-demand
    figs because bulk lots (cheap, damaged, or missing accessories) drag
    the mean down below what buyers of complete minifigs pay.
  - `max_price` alone overshoots — a single aspirational dreamer listing
    can dominate.
  - `(avg + max) / 2` approximates the p~65 of listings for right-skewed
    distributions typical of in-demand figs. For common figs where avg
    ≈ max, the blend collapses back to avg.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from services.ml.currency import to_usd_cents

logger = logging.getLogger(__name__)


MINIFIG_VALUE_FEATURE_NAMES: tuple[str, ...] = (
    "minifig_value_total_usd",     # sum of latest minifig prices, USD cents
    "minifig_value_to_rrp",        # ratio of minifig value to set RRP
    "minifig_count_priced",        # count of distinct priced minifigs
)

# Sets without any priced minifigs get a sentinel rather than NaN/0 so
# LightGBM can split on "no minifig data" as its own branch.
NO_MINIFIG_SENTINEL = -1.0


def load_minifig_value_features(engine: Engine) -> pd.DataFrame:
    """Compute per-set minifig-value totals and ratios.

    Returns a DataFrame keyed by set_number with the columns in
    MINIFIG_VALUE_FEATURE_NAMES.
    """
    rows = pd.read_sql(
        """
        WITH latest_prices AS (
            SELECT DISTINCT ON (minifig_id)
                minifig_id, current_new
            FROM minifig_price_history
            WHERE current_new IS NOT NULL
            ORDER BY minifig_id, scraped_at DESC
        )
        SELECT
            sm.set_number,
            sm.minifig_id,
            sm.quantity,
            lp.current_new
        FROM set_minifigures sm
        JOIN latest_prices lp ON lp.minifig_id = sm.minifig_id
        """,
        engine,
    )

    if rows.empty:
        logger.warning("No minifig price rows found")
        return pd.DataFrame(
            columns=("set_number",) + MINIFIG_VALUE_FEATURE_NAMES,
        )

    aggregated: dict[str, dict[str, float]] = {}
    current_year = pd.Timestamp.now().year

    for _, row in rows.iterrows():
        sn = row["set_number"]
        cn = row["current_new"]
        if isinstance(cn, str):
            try:
                cn = json.loads(cn)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(cn, dict):
            continue

        # Blended price: (avg + max) / 2, in native currency cents.
        # Fall back to avg-only if max is missing; skip if neither present.
        avg = cn.get("avg_price")
        mx = cn.get("max_price")
        if not isinstance(avg, dict):
            continue
        avg_amount = avg.get("amount")
        currency = avg.get("currency") or "MYR"
        if not avg_amount or avg_amount <= 0:
            continue

        if isinstance(mx, dict) and mx.get("amount") and mx["amount"] > 0:
            blended = (float(avg_amount) + float(mx["amount"])) / 2.0
        else:
            blended = float(avg_amount)

        usd_cents = to_usd_cents(blended, currency, current_year)
        if usd_cents is None or usd_cents <= 0:
            continue

        qty = float(row["quantity"] or 1)
        slot = aggregated.setdefault(
            sn, {"minifig_value_total_usd": 0.0, "minifig_count_priced": 0.0},
        )
        slot["minifig_value_total_usd"] += usd_cents * qty
        slot["minifig_count_priced"] += qty

    if not aggregated:
        return pd.DataFrame(
            columns=("set_number",) + MINIFIG_VALUE_FEATURE_NAMES,
        )

    df = pd.DataFrame.from_dict(aggregated, orient="index")
    df.index.name = "set_number"
    df = df.reset_index()
    logger.info("Minifig value features: %d sets", len(df))
    return df


def merge_minifig_value(base: pd.DataFrame, mv: pd.DataFrame) -> pd.DataFrame:
    """Left-merge minifig-value totals onto base; compute ratio vs rrp_usd_cents.

    Sets without any priced minifigs get NO_MINIFIG_SENTINEL so the model
    can split on "no minifig data" as its own branch.
    """
    if mv.empty:
        for col in MINIFIG_VALUE_FEATURE_NAMES:
            base[col] = NO_MINIFIG_SENTINEL
        return base

    merged = base.merge(mv, on="set_number", how="left")

    if "rrp_usd_cents" in merged.columns:
        rrp = pd.to_numeric(merged["rrp_usd_cents"], errors="coerce")
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = merged["minifig_value_total_usd"] / rrp
        merged["minifig_value_to_rrp"] = ratio.where(
            (rrp > 0) & ratio.notna(), other=np.nan,
        )
    else:
        merged["minifig_value_to_rrp"] = np.nan

    for col in MINIFIG_VALUE_FEATURE_NAMES:
        if col in merged.columns:
            merged[col] = merged[col].fillna(NO_MINIFIG_SENTINEL)
        else:
            merged[col] = NO_MINIFIG_SENTINEL
    return merged
