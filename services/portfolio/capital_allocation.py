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
    MAX_SET_PCT,
    MAX_THEME_PCT,
    MAX_YEAR_PCT,
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
    theme: str | None
    year_retired: int | None
    theme_exposure_cents: int
    year_exposure_cents: int
    theme_cap_cents: int | None
    year_cap_cents: int | None
    set_cap_cents: int | None
    concentration_limited_by: str | None


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
    concentration_cap_cents: int | None,
) -> list[DiscountRow]:
    """Build a guideline table at various discount levels from RRP.

    `concentration_cap_cents` is the hard ceiling on target_position after
    applying the diversification caps (set/theme/year). None if no total
    capital is configured.
    """
    rows: list[DiscountRow] = []
    for discount in DISCOUNT_STEPS:
        entry_cents = max(1, round(rrp_cents * (1.0 - discount)))
        eff_roi = _effective_roi(rrp_cents, entry_cents, annual_roi, hold_years)
        eff_3yr = ((1.0 + eff_roi) ** hold_years) - 1.0
        avg_win = eff_3yr
        kelly_f = _kelly_fraction(win_prob, avg_win, AVG_LOSS_PCT)
        half_k = kelly_f * HALF_KELLY_MULTIPLIER
        capped = min(half_k, MAX_SET_PCT)
        raw_target = (
            round(total_capital_cents * capped) if total_capital_cents else None
        )
        target_pos = (
            min(raw_target, concentration_cap_cents)
            if raw_target is not None and concentration_cap_cents is not None
            else raw_target
        )
        raw_rec = round(available_cents * capped) if available_cents > 0 else None
        if raw_rec is not None and concentration_cap_cents is not None:
            rec_cents: int | None = max(
                0, min(raw_rec, concentration_cap_cents - existing_cost_cents)
            )
        else:
            rec_cents = raw_rec
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


def _load_concentration(conn: Any) -> tuple[dict[str, int], dict[int, int]]:
    """Aggregate FIFO remaining cost basis by theme and by year_retired.

    Both dicts map to total cost_cents currently invested in that bucket.
    Holdings missing theme/year in `lego_items` are silently dropped from
    that dimension (they still count toward the set-level cap).
    """
    from services.portfolio.repository import _fifo_cost_basis

    rows = conn.execute(
        """
        SELECT pt.set_number, pt.condition, pt.txn_type, pt.quantity,
               pt.price_cents, pt.txn_date,
               li.theme, li.year_retired
        FROM portfolio_transactions pt
        LEFT JOIN lego_items li ON li.set_number = pt.set_number
        ORDER BY pt.set_number, pt.condition, pt.txn_date ASC, pt.id ASC
        """
    ).fetchall()

    groups: dict[tuple[str, str], list[tuple]] = {}
    meta: dict[str, tuple[str | None, int | None]] = {}
    for row in rows:
        sn, cond = row[0], row[1]
        groups.setdefault((sn, cond), []).append(
            (sn, cond, row[2], row[3], row[4], row[5])
        )
        meta[sn] = (row[6], row[7])

    theme_costs: dict[str, int] = {}
    year_costs: dict[int, int] = {}
    for (sn, _cond), txns in groups.items():
        cost, qty = _fifo_cost_basis(txns)
        if qty <= 0 or cost <= 0:
            continue
        theme, year_retired = meta.get(sn, (None, None))
        if theme:
            theme_costs[theme] = theme_costs.get(theme, 0) + cost
        if year_retired is not None:
            year_costs[int(year_retired)] = year_costs.get(int(year_retired), 0) + cost
    return theme_costs, year_costs


def _item_theme_year(conn: Any, set_number: str) -> tuple[str | None, int | None]:
    """Fetch (theme, year_retired) for a single set. Missing metadata → (None, None)."""
    row = conn.execute(
        "SELECT theme, year_retired FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if not row:
        return (None, None)
    theme = row[0]
    year = int(row[1]) if row[1] is not None else None
    return (theme, year)


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

    theme, year_retired = _item_theme_year(conn, set_number)
    theme_costs, year_costs = _load_concentration(conn)
    theme_exposure = theme_costs.get(theme, 0) if theme else 0
    year_exposure = year_costs.get(year_retired, 0) if year_retired is not None else 0

    # Per-dimension budget (None when total capital is unknown).
    theme_cap = round(total_capital * MAX_THEME_PCT) if total_capital else None
    year_cap = round(total_capital * MAX_YEAR_PCT) if total_capital else None
    set_cap = round(total_capital * MAX_SET_PCT) if total_capital else None

    # Headroom = how much MORE can still be committed to each bucket.
    theme_head = max(0, theme_cap - theme_exposure) if theme_cap is not None else None
    year_head = max(0, year_cap - year_exposure) if year_cap is not None else None

    # Concentration ceiling on this set's TOTAL committed capital, which
    # caps existing_cost + any new allocation.
    concentration_ceiling: int | None = None
    if set_cap is not None:
        candidates = [set_cap]
        if theme_head is not None:
            candidates.append(existing_cost + theme_head)
        if year_head is not None:
            candidates.append(existing_cost + year_head)
        concentration_ceiling = min(candidates)

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
            theme=theme,
            year_retired=year_retired,
            theme_exposure_cents=theme_exposure,
            year_exposure_cents=year_exposure,
            theme_cap_cents=theme_cap,
            year_cap_cents=year_cap,
            set_cap_cents=set_cap,
            concentration_limited_by=None,
        )

    annual_roi = params["annual_roi"]
    win_prob = params["win_prob"]
    hold_years = params["hold_years"]

    total_return_3yr = ((1.0 + annual_roi) ** hold_years) - 1.0
    avg_win = total_return_3yr

    kelly_f = _kelly_fraction(win_prob, avg_win, AVG_LOSS_PCT)
    half_k = kelly_f * HALF_KELLY_MULTIPLIER
    capped = min(half_k, MAX_SET_PCT)

    raw_target = round((total_capital or 0) * capped) if total_capital else None
    target_position = raw_target
    limited_by: str | None = None
    if raw_target is not None and concentration_ceiling is not None:
        target_position = min(raw_target, concentration_ceiling)
        if target_position < raw_target:
            # Something tighter than the raw Kelly×capital bid. Attribute it
            # to whichever dimension is currently the binding constraint.
            if set_cap is not None and target_position == set_cap:
                limited_by = "set"
            elif theme_head is not None and target_position == existing_cost + theme_head:
                limited_by = "theme"
            elif year_head is not None and target_position == existing_cost + year_head:
                limited_by = "year"

    raw_rec = round(available * capped) if available > 0 else None
    if raw_rec is not None and concentration_ceiling is not None:
        rec_cents: int | None = max(
            0, min(raw_rec, concentration_ceiling - existing_cost)
        )
    else:
        rec_cents = raw_rec

    remaining_amount = (
        max(0, min(target_position - existing_cost, available))
        if target_position is not None
        else None
    )

    target_value = round(rrp_cents * ((1.0 + TARGET_APR) ** hold_years))
    expected_value = round(rrp_cents * (1.0 + total_return_3yr))

    discount_table = _build_discount_table(
        rrp_cents, annual_roi, win_prob, hold_years,
        available, total_capital, existing_cost,
        concentration_ceiling,
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
        theme=theme,
        year_retired=year_retired,
        theme_exposure_cents=theme_exposure,
        year_exposure_cents=year_exposure,
        theme_cap_cents=theme_cap,
        year_cap_cents=year_cap,
        set_cap_cents=set_cap,
        concentration_limited_by=limited_by,
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
        "theme": alloc.theme,
        "year_retired": alloc.year_retired,
        "theme_exposure_cents": alloc.theme_exposure_cents,
        "year_exposure_cents": alloc.year_exposure_cents,
        "theme_cap_cents": alloc.theme_cap_cents,
        "year_cap_cents": alloc.year_cap_cents,
        "set_cap_cents": alloc.set_cap_cents,
        "concentration_limited_by": alloc.concentration_limited_by,
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
