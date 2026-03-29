"""Kelly Criterion position sizing for LEGO set investments.

Computes optimal position sizes by analyzing historical backtest returns
stratified by composite signal score bins.
"""

import logging
import threading
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pandas as pd

from config.kelly import (
    CONFIDENCE_HIGH_SAMPLES,
    CONFIDENCE_MODERATE_SAMPLES,
    FLIP_HORIZONS,
    HOLD_HORIZONS,
    KELLY_FRACTION,
    MAX_POSITION_PCT,
    MIN_SAMPLE_COUNT,
    SCORE_BIN_LABELS,
    SCORE_BINS,
)
from services.backtesting.analysis import trades_to_dataframe
from services.backtesting.types import SIGNAL_NAMES, TradeResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

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


@dataclass(frozen=True)
class PositionSizing:
    """Recommended position size for one item."""

    set_number: str
    composite_score: float | None
    score_bin: str
    entry_price_cents: int
    flip: KellyParams | None
    hold: KellyParams | None
    recommended_pct: float
    recommended_amount_cents: int | None
    confidence: str  # "high", "moderate", "low", "insufficient"
    warnings: tuple[str, ...] = ()


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

    # Compute composite score per trade (avg of non-null signals)
    signal_cols = [c for c in SIGNAL_NAMES if c in df.columns]
    df["composite_score"] = df[signal_cols].mean(axis=1, skipna=True)

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


def _pick_best_horizon(
    horizons: dict[str, KellyParams],
    candidates: tuple[str, ...],
) -> KellyParams | None:
    """Pick the horizon with the highest positive half-Kelly from candidates."""
    best: KellyParams | None = None
    for horizon_key in candidates:
        params = horizons.get(horizon_key)
        if params is None:
            continue
        if params.half_kelly > 0 and (
            best is None or params.half_kelly > best.half_kelly
        ):
            best = params
    return best


def _assess_confidence(
    flip: KellyParams | None,
    hold: KellyParams | None,
) -> str:
    """Assess confidence level based on sample counts."""
    samples = max(
        flip.sample_count if flip else 0,
        hold.sample_count if hold else 0,
    )
    if samples >= CONFIDENCE_HIGH_SAMPLES:
        return "high"
    if samples >= CONFIDENCE_MODERATE_SAMPLES:
        return "moderate"
    if samples >= MIN_SAMPLE_COUNT:
        return "low"
    return "insufficient"


def size_position(
    item_signals: dict[str, Any],
    kelly_table: dict[str, dict[str, KellyParams]],
    budget_cents: int | None = None,
) -> PositionSizing:
    """Compute position sizing for an item given its signals and the Kelly table."""
    composite = item_signals.get("composite_score")
    score_bin = _bin_composite_score(composite)
    set_number = item_signals.get("set_number", "")
    entry_price = item_signals.get("entry_price_cents", 0)

    warnings: list[str] = []

    # Look up the bin in the Kelly table
    bin_horizons = kelly_table.get(score_bin, {})

    if not bin_horizons:
        return PositionSizing(
            set_number=set_number,
            composite_score=composite,
            score_bin=score_bin,
            entry_price_cents=entry_price,
            flip=None,
            hold=None,
            recommended_pct=0.0,
            recommended_amount_cents=None,
            confidence="insufficient",
            warnings=("No backtest data for this score range",),
        )

    flip = _pick_best_horizon(bin_horizons, FLIP_HORIZONS)
    hold = _pick_best_horizon(bin_horizons, HOLD_HORIZONS)

    confidence = _assess_confidence(flip, hold)

    # Pick the strategy with higher half-Kelly
    flip_hk = flip.half_kelly if flip else 0.0
    hold_hk = hold.half_kelly if hold else 0.0
    raw_pct = max(flip_hk, hold_hk)

    # Apply confidence adjustment for small samples
    best_samples = max(
        flip.sample_count if flip else 0,
        hold.sample_count if hold else 0,
    )
    confidence_factor = min(1.0, best_samples / CONFIDENCE_MODERATE_SAMPLES)
    adjusted_pct = raw_pct * confidence_factor

    # Cap at max position
    final_pct = min(adjusted_pct, MAX_POSITION_PCT)
    final_pct = round(final_pct, 4)

    if adjusted_pct > MAX_POSITION_PCT:
        warnings.append(
            f"Position capped at {MAX_POSITION_PCT:.0%} (Kelly suggested {adjusted_pct:.1%})"
        )

    if confidence == "low":
        warnings.append(
            f"Low confidence: only {best_samples} historical samples"
        )

    if flip and hold:
        strategy = "hold" if hold_hk >= flip_hk else "flip"
        warnings.append(f"Recommended strategy: {strategy}")

    recommended_amount = None
    if budget_cents is not None and budget_cents > 0:
        recommended_amount = int(budget_cents * final_pct)

    return PositionSizing(
        set_number=set_number,
        composite_score=composite,
        score_bin=score_bin,
        entry_price_cents=entry_price,
        flip=flip,
        hold=hold,
        recommended_pct=final_pct,
        recommended_amount_cents=recommended_amount,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def _get_kelly_table(conn: "DuckDBPyConnection") -> dict[str, dict[str, KellyParams]]:
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


def compute_position_sizing(
    conn: "DuckDBPyConnection",
    set_number: str,
    budget_cents: int | None = None,
    condition: str = "new",
) -> PositionSizing | None:
    """Compute position sizing for a single item.

    Orchestrates: backtest -> Kelly table -> item signals -> sizing.
    """
    from services.backtesting.screener import compute_item_signals

    item_signals = compute_item_signals(conn, set_number, condition=condition)
    if item_signals is None:
        return None

    kelly_table = _get_kelly_table(conn)
    return size_position(item_signals, kelly_table, budget_cents=budget_cents)


def kelly_to_dict(sizing: PositionSizing) -> dict[str, Any]:
    """Serialize a PositionSizing to a JSON-friendly dict."""

    def _params_dict(params: KellyParams | None) -> dict[str, Any] | None:
        if params is None:
            return None
        return {
            "horizon": params.horizon,
            "win_rate": params.win_rate,
            "avg_win": params.avg_win,
            "avg_loss": params.avg_loss,
            "mean_return": params.mean_return,
            "return_variance": params.return_variance,
            "sample_count": params.sample_count,
            "kelly_fraction": params.kelly_fraction,
            "half_kelly": params.half_kelly,
        }

    return {
        "set_number": sizing.set_number,
        "composite_score": sizing.composite_score,
        "score_bin": sizing.score_bin,
        "entry_price_cents": sizing.entry_price_cents,
        "flip": _params_dict(sizing.flip),
        "hold": _params_dict(sizing.hold),
        "recommended_pct": sizing.recommended_pct,
        "recommended_amount_cents": sizing.recommended_amount_cents,
        "confidence": sizing.confidence,
        "warnings": list(sizing.warnings),
    }
