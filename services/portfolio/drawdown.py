"""Position-level drawdown tracker.

For each currently-held position, compute the peak market value observed
since the cost-weighted acquisition date and the current drawdown from
that peak. Uses `bricklink_monthly_sales` (new-condition, monthly) as
the price series — same source as the ML ground truth, so drawdown
attribution is consistent with the signal the classifier sees.

The tracker flags positions that are quietly failing even when the
top-level portfolio return still looks healthy: one big winner can mask
three positions in 30% drawdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.portfolio.repository import (
    MYR_PER_USD,
    _fifo_cost_basis,
    _fifo_weighted_avg_date,
    _latest_prices,
)


# Positions at or beyond this drawdown are flagged as "at risk" in the UI.
DRAWDOWN_ALERT_PCT: float = 0.20


@dataclass(frozen=True)
class PositionDrawdown:
    set_number: str
    condition: str
    quantity: int
    cost_basis_cents: int
    avg_cost_cents: int
    acquired_at: datetime | None
    current_value_cents: int     # per unit, MYR cents
    peak_value_cents: int        # per unit, MYR cents (since acquisition)
    peak_date: datetime | None
    drawdown_pct: float          # (peak - current) / peak, clamped ≥ 0
    unrealized_pl_cents: int
    unrealized_pl_pct: float
    months_in_drawdown: int      # months elapsed since peak_date
    at_risk: bool                # drawdown_pct >= DRAWDOWN_ALERT_PCT


def get_positions_drawdown(conn: Any) -> list[PositionDrawdown]:
    """Compute drawdown metrics for every currently-held (set, condition).

    Sorted by drawdown_pct descending so the worst offenders surface first.
    """
    txn_rows = conn.execute(
        """
        SELECT set_number, condition, txn_type, quantity, price_cents, txn_date
        FROM portfolio_transactions
        ORDER BY set_number, condition, txn_date ASC, id ASC
        """
    ).fetchall()

    groups: dict[tuple[str, str], list[tuple]] = {}
    for row in txn_rows:
        groups.setdefault((row[0], row[1]), []).append(tuple(row))

    positions: list[tuple[str, str, int, int, datetime | None]] = []
    for (sn, cond), txns in groups.items():
        cost, qty = _fifo_cost_basis(txns)
        if qty <= 0:
            continue
        positions.append((sn, cond, qty, cost, _fifo_weighted_avg_date(txns)))

    if not positions:
        return []

    set_numbers = sorted({p[0] for p in positions})
    current_prices = _latest_prices(conn, set_numbers)
    series_by_set = _load_monthly_series(conn, set_numbers)

    now = datetime.now(timezone.utc)
    out: list[PositionDrawdown] = []
    for sn, cond, qty, cost, acquired in positions:
        current = current_prices.get(sn, 0)
        avg_cost = cost // qty if qty > 0 else 0

        series = series_by_set.get(sn, [])
        since = _normalize_tz(acquired)
        window = [(d, v) for d, v in series if since is None or d >= since]

        # Peak floor = max(series max, entry cost). Using entry cost as a
        # floor avoids understating drawdown for positions that dropped on
        # entry and never recovered — their series max can equal `current`,
        # which would otherwise report 0% drawdown on a losing position.
        peak, peak_date = _peak_from_window(window, current, avg_cost, acquired)
        drawdown = 0.0
        if peak > 0 and current < peak:
            drawdown = (peak - current) / peak

        months_since_peak = 0
        if peak_date is not None:
            months_since_peak = max(
                0,
                (now.year - peak_date.year) * 12 + (now.month - peak_date.month),
            )

        unrealized_pl = (current * qty) - cost
        unrealized_pl_pct = (unrealized_pl / cost) if cost > 0 else 0.0

        out.append(
            PositionDrawdown(
                set_number=sn,
                condition=cond,
                quantity=qty,
                cost_basis_cents=cost,
                avg_cost_cents=avg_cost,
                acquired_at=acquired,
                current_value_cents=current,
                peak_value_cents=peak,
                peak_date=peak_date,
                drawdown_pct=round(drawdown, 4),
                unrealized_pl_cents=unrealized_pl,
                unrealized_pl_pct=round(unrealized_pl_pct, 4),
                months_in_drawdown=months_since_peak,
                at_risk=drawdown >= DRAWDOWN_ALERT_PCT,
            )
        )

    out.sort(key=lambda p: p.drawdown_pct, reverse=True)
    return out


def get_drawdown_summary(positions: list[PositionDrawdown]) -> dict:
    """Portfolio-wide drawdown roll-up for the dashboard header."""
    if not positions:
        return {
            "position_count": 0,
            "at_risk_count": 0,
            "at_risk_cost_cents": 0,
            "max_drawdown_pct": 0.0,
            "weighted_drawdown_pct": 0.0,
        }

    total_cost = sum(p.cost_basis_cents for p in positions)
    at_risk = [p for p in positions if p.at_risk]
    max_dd = max(p.drawdown_pct for p in positions)
    weighted = (
        sum(p.drawdown_pct * p.cost_basis_cents for p in positions) / total_cost
        if total_cost > 0
        else 0.0
    )
    return {
        "position_count": len(positions),
        "at_risk_count": len(at_risk),
        "at_risk_cost_cents": sum(p.cost_basis_cents for p in at_risk),
        "max_drawdown_pct": round(max_dd, 4),
        "weighted_drawdown_pct": round(weighted, 4),
    }


def position_drawdown_to_dict(p: PositionDrawdown) -> dict:
    return {
        "set_number": p.set_number,
        "condition": p.condition,
        "quantity": p.quantity,
        "cost_basis_cents": p.cost_basis_cents,
        "avg_cost_cents": p.avg_cost_cents,
        "acquired_at": p.acquired_at.isoformat() if p.acquired_at else None,
        "current_value_cents": p.current_value_cents,
        "peak_value_cents": p.peak_value_cents,
        "peak_date": p.peak_date.isoformat() if p.peak_date else None,
        "drawdown_pct": p.drawdown_pct,
        "unrealized_pl_cents": p.unrealized_pl_cents,
        "unrealized_pl_pct": p.unrealized_pl_pct,
        "months_in_drawdown": p.months_in_drawdown,
        "at_risk": p.at_risk,
    }


def _normalize_tz(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    if d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d


def _peak_from_window(
    window: list[tuple[datetime, int]],
    current: int,
    avg_cost: int,
    acquired_at: datetime | None,
) -> tuple[int, datetime | None]:
    """Return (peak, peak_date).

    Peak is the max of (best observed in window, avg_cost floor, current).
    peak_date is None when the peak is current or the cost floor (neither
    has a meaningful history date). When entry cost is the binding peak,
    use acquisition date so the caller can report "months in drawdown".
    """
    series_peak_d: datetime | None = None
    series_peak_v = 0
    if window:
        series_peak_d, series_peak_v = max(window, key=lambda r: r[1])

    peak = max(series_peak_v, avg_cost, current)
    if peak <= current:
        return (current, None)
    if peak == series_peak_v:
        return (peak, series_peak_d)
    # Cost-floor peak — acquisition date is the effective high-water mark.
    return (peak, _normalize_tz(acquired_at))


def _load_monthly_series(
    conn: Any, set_numbers: list[str]
) -> dict[str, list[tuple[datetime, int]]]:
    """Load monthly BL new-sales avg price per set as (date, MYR_cents).

    Filters to `condition='new'` to match how the UI surfaces market
    value. Legacy rows in USD are converted on the fly. Ordered ascending
    by (year, month).
    """
    if not set_numbers:
        return {}

    placeholders = ", ".join(["?"] * len(set_numbers))
    rows = conn.execute(
        f"""
        SELECT set_number, year, month, avg_price, currency
        FROM bricklink_monthly_sales
        WHERE set_number IN ({placeholders})
          AND condition = 'new'
          AND avg_price IS NOT NULL
          AND avg_price > 0
        ORDER BY set_number, year, month
        """,  # noqa: S608
        set_numbers,
    ).fetchall()

    out: dict[str, list[tuple[datetime, int]]] = {}
    for sn, year, month, avg_price, currency in rows:
        if year < 100:  # legacy 2-digit year typo — skip rather than fabricate
            continue
        try:
            d = datetime(int(year), int(month), 1, tzinfo=timezone.utc)
        except ValueError:
            continue
        price = int(avg_price)
        if currency == "USD":
            price = round(price * MYR_PER_USD)
        out.setdefault(sn, []).append((d, price))
    return out
