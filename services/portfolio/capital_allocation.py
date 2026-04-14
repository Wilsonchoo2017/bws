"""Assumption-based capital allocation using simplified Kelly Criterion.

Uses fixed return/loss assumptions per ML buy category and win probabilities
from historical BrickLink ground truth (FINDINGS.md Phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.kelly import (
    AVG_LOSS_PCT,
    CATEGORY_PARAMS,
    DISCOUNT_STEPS,
    HALF_KELLY_MULTIPLIER,
    MAX_POSITION_PCT,
    TARGET_APR,
)
from services.portfolio.settings import get_total_capital
from services.portfolio.repository import get_portfolio_summary


@dataclass(frozen=True)
class DiscountRow:
    discount_pct: float
    entry_price_cents: int
    effective_annual_roi: float
    effective_3yr_return: float
    meets_target: bool
    recommended_amount_cents: int | None
    target_position_cents: int | None
    remaining_amount_cents: int | None


@dataclass(frozen=True)
class CapitalAllocation:
    set_number: str
    ml_buy_category: str | None
    rrp_cents: int | None
    rrp_currency: str
    annual_roi: float
    total_return_3yr: float
    win_probability: float
    kelly_fraction: float
    half_kelly: float
    recommended_pct: float
    recommended_amount_cents: int | None
    total_capital_cents: int | None
    deployed_cents: int
    available_cents: int
    existing_quantity: int
    existing_cost_cents: int
    target_position_cents: int | None
    remaining_amount_cents: int | None
    target_value_cents: int | None
    expected_value_cents: int | None
    meets_target: bool
    discount_table: list[DiscountRow]


def _kelly_fraction(win_prob: float, avg_win: float, avg_loss: float) -> float:
    """Classic Kelly: f* = (b*p - q) / b where b = avg_win / avg_loss."""
    if avg_loss <= 0:
        return 0.0
    b = avg_win / avg_loss
    if b <= 0:
        return 0.0
    f = (b * win_prob - (1.0 - win_prob)) / b
    return max(0.0, f)


def _effective_roi(rrp_cents: int, entry_cents: int, annual_roi: float, hold_years: float) -> float:
    """Effective annual ROI when buying below RRP.

    Growth target is still RRP × (1 + annual_roi)^years, but entry is lower.
    """
    if entry_cents <= 0 or rrp_cents <= 0:
        return 0.0
    future_value = rrp_cents * ((1.0 + annual_roi) ** hold_years)
    return (future_value / entry_cents) ** (1.0 / hold_years) - 1.0


def _build_discount_table(
    rrp_cents: int,
    annual_roi: float,
    win_prob: float,
    hold_years: float,
    available_cents: int,
    total_capital_cents: int | None,
    existing_cost_cents: int,
) -> list[DiscountRow]:
    """Build a guideline table at various discount levels from RRP."""
    rows: list[DiscountRow] = []
    for discount in DISCOUNT_STEPS:
        entry_cents = max(1, round(rrp_cents * (1.0 - discount)))
        eff_roi = _effective_roi(rrp_cents, entry_cents, annual_roi, hold_years)
        eff_3yr = ((1.0 + eff_roi) ** hold_years) - 1.0
        avg_win = eff_3yr
        kelly_f = _kelly_fraction(win_prob, avg_win, AVG_LOSS_PCT)
        half_k = kelly_f * HALF_KELLY_MULTIPLIER
        capped = min(half_k, MAX_POSITION_PCT)
        rec_cents = round(available_cents * capped) if available_cents > 0 else None
        target_pos = (
            round(total_capital_cents * capped) if total_capital_cents else None
        )
        remaining = (
            max(0, min(target_pos - existing_cost_cents, available_cents))
            if target_pos is not None
            else None
        )
        rows.append(
            DiscountRow(
                discount_pct=discount,
                entry_price_cents=entry_cents,
                effective_annual_roi=eff_roi,
                effective_3yr_return=eff_3yr,
                meets_target=eff_roi >= TARGET_APR,
                recommended_amount_cents=rec_cents,
                target_position_cents=target_pos,
                remaining_amount_cents=remaining,
            )
        )
    return rows


def _existing_position(conn: Any, set_number: str) -> tuple[int, int]:
    """Return (quantity, cost_basis_cents) currently held for this set across conditions."""
    from services.portfolio.repository import _fifo_cost_basis

    rows = conn.execute(
        """
        SELECT set_number, condition, txn_type, quantity, price_cents, txn_date
        FROM portfolio_transactions
        WHERE set_number = ?
        ORDER BY condition, txn_date ASC, id ASC
        """,
        [set_number],
    ).fetchall()

    if not rows:
        return 0, 0

    groups: dict[str, list[tuple]] = {}
    for row in rows:
        groups.setdefault(row[1], []).append(tuple(row))

    total_qty = 0
    total_cost = 0
    for cond_txns in groups.values():
        cost, qty = _fifo_cost_basis(cond_txns)
        total_qty += qty
        total_cost += cost
    return total_qty, total_cost


def compute_capital_allocation(
    conn: Any,
    set_number: str,
    ml_buy_category: str | None,
    rrp_cents: int | None,
    rrp_currency: str = "MYR",
) -> CapitalAllocation:
    """Compute assumption-based capital allocation for a single item."""
    total_capital = get_total_capital(conn)
    summary = get_portfolio_summary(conn)
    deployed = summary["total_cost_cents"]
    available = max(0, (total_capital or 0) - deployed)
    existing_qty, existing_cost = _existing_position(conn, set_number)

    params = CATEGORY_PARAMS.get(ml_buy_category or "", None)

    if params is None or rrp_cents is None or rrp_cents <= 0:
        return CapitalAllocation(
            set_number=set_number,
            ml_buy_category=ml_buy_category,
            rrp_cents=rrp_cents,
            rrp_currency=rrp_currency,
            annual_roi=0.0,
            total_return_3yr=0.0,
            win_probability=0.0,
            kelly_fraction=0.0,
            half_kelly=0.0,
            recommended_pct=0.0,
            recommended_amount_cents=None,
            total_capital_cents=total_capital,
            deployed_cents=deployed,
            available_cents=available,
            existing_quantity=existing_qty,
            existing_cost_cents=existing_cost,
            target_position_cents=None,
            remaining_amount_cents=None,
            target_value_cents=round(rrp_cents * (1.0 + TARGET_APR) ** 3) if rrp_cents else None,
            expected_value_cents=None,
            meets_target=False,
            discount_table=[],
        )

    annual_roi = params["annual_roi"]
    win_prob = params["win_prob"]
    hold_years = params["hold_years"]

    total_return_3yr = ((1.0 + annual_roi) ** hold_years) - 1.0
    avg_win = total_return_3yr

    kelly_f = _kelly_fraction(win_prob, avg_win, AVG_LOSS_PCT)
    half_k = kelly_f * HALF_KELLY_MULTIPLIER
    capped = min(half_k, MAX_POSITION_PCT)

    rec_cents = round(available * capped) if available > 0 else None

    target_position = round((total_capital or 0) * capped) if total_capital else None
    remaining_amount = (
        max(0, min(target_position - existing_cost, available))
        if target_position is not None
        else None
    )

    target_value = round(rrp_cents * ((1.0 + TARGET_APR) ** hold_years))
    expected_value = round(rrp_cents * (1.0 + total_return_3yr))

    discount_table = _build_discount_table(
        rrp_cents, annual_roi, win_prob, hold_years, available, total_capital, existing_cost
    )

    return CapitalAllocation(
        set_number=set_number,
        ml_buy_category=ml_buy_category,
        rrp_cents=rrp_cents,
        rrp_currency=rrp_currency,
        annual_roi=annual_roi,
        total_return_3yr=total_return_3yr,
        win_probability=win_prob,
        kelly_fraction=kelly_f,
        half_kelly=half_k,
        recommended_pct=capped,
        recommended_amount_cents=rec_cents,
        total_capital_cents=total_capital,
        deployed_cents=deployed,
        available_cents=available,
        existing_quantity=existing_qty,
        existing_cost_cents=existing_cost,
        target_position_cents=target_position,
        remaining_amount_cents=remaining_amount,
        target_value_cents=target_value,
        expected_value_cents=expected_value,
        meets_target=annual_roi >= TARGET_APR,
        discount_table=discount_table,
    )


def allocation_to_dict(alloc: CapitalAllocation) -> dict:
    """Serialize CapitalAllocation for JSON response."""
    return {
        "set_number": alloc.set_number,
        "ml_buy_category": alloc.ml_buy_category,
        "rrp_cents": alloc.rrp_cents,
        "rrp_currency": alloc.rrp_currency,
        "annual_roi": alloc.annual_roi,
        "total_return_3yr": alloc.total_return_3yr,
        "win_probability": alloc.win_probability,
        "kelly_fraction": alloc.kelly_fraction,
        "half_kelly": alloc.half_kelly,
        "recommended_pct": alloc.recommended_pct,
        "recommended_amount_cents": alloc.recommended_amount_cents,
        "total_capital_cents": alloc.total_capital_cents,
        "deployed_cents": alloc.deployed_cents,
        "available_cents": alloc.available_cents,
        "existing_quantity": alloc.existing_quantity,
        "existing_cost_cents": alloc.existing_cost_cents,
        "target_position_cents": alloc.target_position_cents,
        "remaining_amount_cents": alloc.remaining_amount_cents,
        "target_value_cents": alloc.target_value_cents,
        "expected_value_cents": alloc.expected_value_cents,
        "meets_target": alloc.meets_target,
        "discount_table": [
            {
                "discount_pct": r.discount_pct,
                "entry_price_cents": r.entry_price_cents,
                "effective_annual_roi": r.effective_annual_roi,
                "effective_3yr_return": r.effective_3yr_return,
                "meets_target": r.meets_target,
                "recommended_amount_cents": r.recommended_amount_cents,
                "target_position_cents": r.target_position_cents,
                "remaining_amount_cents": r.remaining_amount_cents,
            }
            for r in alloc.discount_table
        ],
    }
