"""Kelly Criterion math and table construction.

Computes Kelly parameters from backtest return distributions,
stratified by composite signal score bins.
"""

import logging
import threading
import time
from dataclasses import dataclass, replace

import pandas as pd

from config.kelly import (
    APPLY_MODIFIERS,
    DEFAULT_SIGNAL_WEIGHT,
    FLIP_HORIZONS,
    HOLD_HORIZONS,
    KELLY_FRACTION,
    MIN_SAMPLE_COUNT,
    SCORE_BIN_LABELS,
    SCORE_BINS,
    SIGNAL_WEIGHTS,
)
from services.backtesting.analysis import trades_to_dataframe
from services.backtesting.types import SIGNAL_NAMES, TradeResult
from typing import Any


logger = logging.getLogger(__name__)

# Module-level cache for the Kelly table
_kelly_lock = threading.Lock()
_kelly_cache: dict | None = None
_kelly_cache_time: float = 0.0
_CACHE_TTL_SECONDS: float = 86400.0  # 24 hours


@dataclass(frozen=True)
class KellyParams:
    """Kelly parameters for one score bin + one return horizon."""

    score_bin: str
    horizon: str
    win_rate: float
    avg_win: float
    avg_loss: float
    mean_return: float
    return_variance: float
    sample_count: int
    kelly_fraction: float
    half_kelly: float


def _bin_composite_score(score: float | None) -> str:
    """Map a composite score to its bin label."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return SCORE_BIN_LABELS[SCORE_BINS[0]]
    for low, high in SCORE_BINS:
        if low <= score < high:
            return SCORE_BIN_LABELS[(low, high)]
    return SCORE_BIN_LABELS[SCORE_BINS[-1]]


def _compute_kelly_for_returns(returns: pd.Series) -> KellyParams | None:
    """Compute Kelly parameters from a series of returns.

    Returns None if insufficient data.
    """
    valid = returns.dropna()
    if len(valid) < MIN_SAMPLE_COUNT:
        return None

    winners = valid[valid > 0]
    losers = valid[valid < 0]

    win_rate = len(winners) / len(valid) if len(valid) > 0 else 0.0
    avg_win = float(winners.mean()) if len(winners) > 0 else 0.0
    avg_loss = float(abs(losers.mean())) if len(losers) > 0 else 0.0
    mean_return = float(valid.mean())
    return_variance = float(valid.var()) if len(valid) > 1 else 0.0

    # Classic Kelly: f* = (b*p - q) / b where b = avg_win/avg_loss
    if avg_loss > 0 and avg_win > 0:
        b = avg_win / avg_loss
        q = 1.0 - win_rate
        kelly = (b * win_rate - q) / b
    elif avg_win > 0 and avg_loss == 0:
        # All trades are winners - full allocation (capped later)
        kelly = 1.0
    else:
        kelly = 0.0

    kelly = max(0.0, kelly)  # No negative (no shorting)
    half = kelly * KELLY_FRACTION

    return KellyParams(
        score_bin="",
        horizon="",
        win_rate=round(win_rate, 4),
        avg_win=round(avg_win, 4),
        avg_loss=round(avg_loss, 4),
        mean_return=round(mean_return, 4),
        return_variance=round(return_variance, 6),
        sample_count=len(valid),
        kelly_fraction=round(kelly, 4),
        half_kelly=round(half, 4),
    )


def compute_kelly_table(
    trades: list[TradeResult],
) -> dict[str, dict[str, KellyParams]]:
    """Build Kelly parameter lookup table from backtest results.

    Returns nested dict: kelly_table[bin_label][horizon] = KellyParams
    """
    df = trades_to_dataframe(trades)
    if df.empty:
        return {}

    # Compute weighted composite score per trade
    signal_cols = [c for c in SIGNAL_NAMES if c in df.columns]
    weights = pd.Series(
        {c: SIGNAL_WEIGHTS.get(c, DEFAULT_SIGNAL_WEIGHT) for c in signal_cols}
    )
    values = df[signal_cols]
    mask = values.notna()
    weighted_sum = values.where(mask, 0.0).mul(weights, axis=1).sum(axis=1)
    weight_sum = mask.astype(float).mul(weights, axis=1).sum(axis=1)
    df["composite_score"] = (weighted_sum / weight_sum).where(weight_sum > 0)

    # Apply modifiers as multipliers if enabled
    if APPLY_MODIFIERS:
        mod_cols = [
            c for c in ("mod_shelf_life", "mod_subtheme", "mod_niche")
            if c in df.columns
        ]
        if mod_cols:
            modifier_product = df[mod_cols].prod(axis=1)
            df["composite_score"] = (
                df["composite_score"] * modifier_product
            ).clip(0, 100)

    # Assign bins using the shared function
    df["score_bin"] = df["composite_score"].apply(_bin_composite_score)

    # Use explicitly defined horizons only
    return_cols = [c for c in (*FLIP_HORIZONS, *HOLD_HORIZONS) if c in df.columns]

    table: dict[str, dict[str, KellyParams]] = {}

    for bin_label in SCORE_BIN_LABELS.values():
        bin_df = df[df["score_bin"] == bin_label]
        if bin_df.empty:
            continue

        horizons: dict[str, KellyParams] = {}
        for ret_col in return_cols:
            params = _compute_kelly_for_returns(bin_df[ret_col])
            if params is not None:
                horizons[ret_col] = replace(
                    params,
                    score_bin=bin_label,
                    horizon=ret_col.replace("return_", ""),
                )

        if horizons:
            table[bin_label] = horizons

    return table


def get_kelly_table(conn: Any) -> dict[str, dict[str, KellyParams]]:
    """Get or compute the cached Kelly table."""
    global _kelly_cache, _kelly_cache_time

    now = time.time()
    with _kelly_lock:
        if _kelly_cache is not None and (now - _kelly_cache_time) < _CACHE_TTL_SECONDS:
            return _kelly_cache

        from services.backtesting.engine import run_backtest

        logger.info("Computing Kelly table from backtest data...")
        trades = run_backtest(conn)
        table = compute_kelly_table(trades)
        logger.info(
            "Kelly table computed: %d bins, %d total horizons",
            len(table),
            sum(len(h) for h in table.values()),
        )

        _kelly_cache = table
        _kelly_cache_time = now
        return table
