"""Position sizing using Kelly Criterion parameters.

Translates Kelly table lookups into concrete position recommendations
with confidence assessment and neighbor-bin fallback.
"""

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pandas as pd

from config.kelly import (
    CONFIDENCE_HIGH_SAMPLES,
    CONFIDENCE_MODERATE_SAMPLES,
    FLIP_HORIZONS,
    HOLD_HORIZONS,
    MAX_POSITION_PCT,
    MIN_SAMPLE_COUNT,
    NEIGHBOR_FALLBACK_DISCOUNT,
    SCORE_BIN_LABELS,
    SCORE_BINS,
)
from services.backtesting.kelly import KellyParams

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


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


def bin_composite_score(score: float | None) -> str:
    """Map a composite score to its bin label."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return SCORE_BIN_LABELS[SCORE_BINS[0]]
    for low, high in SCORE_BINS:
        if low <= score < high:
            return SCORE_BIN_LABELS[(low, high)]
    return SCORE_BIN_LABELS[SCORE_BINS[-1]]


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


def find_neighbor_bin(
    score_bin: str,
    kelly_table: dict[str, dict[str, KellyParams]],
) -> tuple[str, dict[str, KellyParams]] | None:
    """Find the nearest populated neighbor bin by distance in the ordered bin list.

    Returns (neighbor_label, neighbor_horizons) or None if no neighbor has data.
    """
    ordered_labels = [SCORE_BIN_LABELS[b] for b in SCORE_BINS]
    try:
        idx = ordered_labels.index(score_bin)
    except ValueError:
        return None

    for distance in range(1, len(ordered_labels)):
        for neighbor_idx in (idx - distance, idx + distance):
            if 0 <= neighbor_idx < len(ordered_labels):
                label = ordered_labels[neighbor_idx]
                if label in kelly_table:
                    return (label, kelly_table[label])
    return None


def discount_kelly_params(
    params: KellyParams,
    discount: float,
) -> KellyParams:
    """Return a new KellyParams with half_kelly scaled by the discount factor."""
    return replace(
        params,
        half_kelly=round(params.half_kelly * discount, 4),
    )


def size_position(
    item_signals: dict[str, Any],
    kelly_table: dict[str, dict[str, KellyParams]],
    budget_cents: int | None = None,
) -> PositionSizing:
    """Compute position sizing for an item given its signals and the Kelly table."""
    composite = item_signals.get("composite_score")
    score_bin = bin_composite_score(composite)
    set_number = item_signals.get("set_number", "")
    entry_price = item_signals.get("entry_price_cents", 0)

    warnings: list[str] = []

    # Look up the bin in the Kelly table
    bin_horizons = kelly_table.get(score_bin, {})

    is_fallback = False
    neighbor_label: str | None = None

    if not bin_horizons:
        neighbor = find_neighbor_bin(score_bin, kelly_table)
        if neighbor is None:
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
                warnings=(
                    "No backtest data for this score range or any adjacent range",
                ),
            )
        neighbor_label, bin_horizons = neighbor
        is_fallback = True

    flip = _pick_best_horizon(bin_horizons, FLIP_HORIZONS)
    hold = _pick_best_horizon(bin_horizons, HOLD_HORIZONS)

    if is_fallback:
        if flip is not None:
            flip = discount_kelly_params(flip, NEIGHBOR_FALLBACK_DISCOUNT)
        if hold is not None:
            hold = discount_kelly_params(hold, NEIGHBOR_FALLBACK_DISCOUNT)

    confidence = _assess_confidence(flip, hold)

    if is_fallback and confidence in ("high", "moderate"):
        confidence = "low"

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

    if is_fallback and neighbor_label is not None:
        warnings.append(
            f"Extrapolated from {neighbor_label} data "
            f"(no historical trades in {score_bin})"
        )
        warnings.append(
            f"Recommendation discounted by "
            f"{1 - NEIGHBOR_FALLBACK_DISCOUNT:.0%} due to score range mismatch"
        )

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


def compute_position_sizing(
    conn: "DuckDBPyConnection",
    set_number: str,
    budget_cents: int | None = None,
    condition: str = "new",
) -> PositionSizing | None:
    """Compute position sizing for a single item.

    Orchestrates: backtest -> Kelly table -> item signals -> sizing.
    """
    from services.backtesting.kelly import get_kelly_table
    from services.backtesting.screener import compute_item_signals

    item_signals = compute_item_signals(conn, set_number, condition=condition)
    if item_signals is None:
        return None

    kelly_table = get_kelly_table(conn)
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
