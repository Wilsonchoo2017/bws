"""Database queries for forward return calculation inputs.

Assembles ForwardReturnInput objects by joining holdings, BE snapshots,
ML predictions, and price records.
"""

from __future__ import annotations

import logging
from typing import Any

from config.runtime_settings import runtime_settings
from services.portfolio.forward_return import (
    ForwardReturnInput,
    ForwardReturnResult,
    calculate_forward_return,
)

__all__ = [
    "get_holdings_forward_returns",
    "get_holdings_forward_results",
    "get_opportunity_forward_returns",
    "get_holdings_inputs",
    "get_candidate_inputs",
    "result_to_dict",
]
from services.portfolio.repository import MYR_PER_USD

logger = logging.getLogger("bws.forward_return_query")


def get_holdings_forward_returns(conn: Any) -> list[dict]:
    """Compute forward returns for all current holdings.

    Joins FIFO cost basis with latest BE snapshots, ML predictions,
    and BrickLink prices to produce ForwardReturnResult dicts.
    """
    _, results = get_holdings_forward_results(conn)
    return [result_to_dict(r) for r in results]


def get_holdings_forward_results(
    conn: Any,
) -> tuple[list[ForwardReturnInput], list[ForwardReturnResult]]:
    """Return both inputs and results for reuse by WBR metrics."""
    inputs = get_holdings_inputs(conn)
    fr_settings = runtime_settings.get_section("forward_return")
    results = [calculate_forward_return(inp, fr_settings) for inp in inputs]
    return inputs, results


def get_opportunity_forward_returns(
    conn: Any,
    *,
    min_return: float | None = None,
    limit: int = 200,
) -> list[dict]:
    """Compute forward returns for all sets (held + candidates), ranked.

    Returns sorted by forward_annual_return descending.
    """
    held_inputs = get_holdings_inputs(conn)
    candidate_inputs = get_candidate_inputs(conn, held_inputs)

    fr_settings = runtime_settings.get_section("forward_return")
    all_results = [
        calculate_forward_return(inp, fr_settings)
        for inp in [*held_inputs, *candidate_inputs]
    ]

    # Filter by min_return if specified
    if min_return is not None:
        all_results = [
            r
            for r in all_results
            if r.forward_annual_return is not None
            and r.forward_annual_return >= min_return
        ]

    # Sort by forward_annual_return descending (None last)
    all_results.sort(
        key=lambda r: r.forward_annual_return if r.forward_annual_return is not None else -999.0,
        reverse=True,
    )

    return [result_to_dict(r) for r in all_results[:limit]]


# ---------------------------------------------------------------------------
# Internal: build ForwardReturnInput lists
# ---------------------------------------------------------------------------


def get_holdings_inputs(conn: Any) -> list[ForwardReturnInput]:
    """Build ForwardReturnInput for each held position."""
    rows = conn.execute(
        "SELECT DISTINCT set_number FROM portfolio_transactions"
    ).fetchall()

    held_set_numbers = [r[0] for r in rows]
    if not held_set_numbers:
        return []

    # Get FIFO cost basis per set (reuse existing logic)
    from services.portfolio.repository import _fifo_cost_basis

    txn_rows = conn.execute(
        """
        SELECT set_number, condition, txn_type, quantity, price_cents, txn_date
        FROM portfolio_transactions
        ORDER BY set_number, condition, txn_date ASC, id ASC
        """
    ).fetchall()

    groups: dict[str, list[tuple]] = {}
    for row in txn_rows:
        groups.setdefault(row[0], []).append(row)

    # Aggregate by set_number (sum across conditions)
    holdings_map: dict[str, dict] = {}
    for set_number, txns in groups.items():
        cost, qty = _fifo_cost_basis(txns)
        if qty <= 0:
            continue
        avg_cost = cost // qty if qty > 0 else 0
        holdings_map[set_number] = {
            "quantity": qty,
            "total_cost_cents": cost,
            "avg_cost_cents": avg_cost,
        }

    if not holdings_map:
        return []

    placeholders = ", ".join(["?"] * len(holdings_map))
    set_numbers = list(holdings_map.keys())

    enrichment_rows = conn.execute(
        f"""
        WITH latest_be AS (
            SELECT set_number, future_estimate_cents, future_estimate_date,
                   annual_growth_pct, value_new_cents, year_retired AS be_year_retired
            FROM (
                SELECT set_number, future_estimate_cents, future_estimate_date,
                       annual_growth_pct, value_new_cents, year_retired,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
                FROM brickeconomy_snapshots
            ) sub WHERE rn = 1
        ),
        latest_ml AS (
            SELECT set_number, predicted_growth_pct, confidence
            FROM (
                SELECT set_number, predicted_growth_pct, confidence,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY snapshot_date DESC) AS rn
                FROM ml_prediction_snapshots
            ) sub WHERE rn = 1
        ),
        latest_bl AS (
            SELECT set_number, price_cents AS bl_price_cents, currency AS bl_currency
            FROM (
                SELECT set_number, price_cents, currency,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
                FROM price_records
                WHERE source = 'bricklink_new'
            ) sub WHERE rn = 1
        ),
        latest_bph AS (
            SELECT set_number, six_month_new, current_new
            FROM (
                SELECT set_number, six_month_new, current_new,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
                FROM bricklink_price_history
            ) sub WHERE rn = 1
        )
        SELECT li.set_number,
               li.year_retired, li.retiring_soon,
               be.future_estimate_cents, be.future_estimate_date,
               be.annual_growth_pct, be.value_new_cents, be.be_year_retired,
               ml.predicted_growth_pct, ml.confidence,
               bl.bl_price_cents, bl.bl_currency,
               bph.six_month_new, bph.current_new
        FROM lego_items li
        LEFT JOIN latest_be be ON be.set_number = li.set_number
        LEFT JOIN latest_ml ml ON ml.set_number = li.set_number
        LEFT JOIN latest_bl bl ON bl.set_number = li.set_number
        LEFT JOIN latest_bph bph ON bph.set_number = li.set_number
        WHERE li.set_number IN ({placeholders})
        """,  # noqa: S608
        set_numbers,
    ).fetchall()

    enrichment_map: dict[str, dict] = {}
    for row in enrichment_rows:
        six_month_new = row[12] or {}
        current_new = row[13] or {}
        enrichment_map[row[0]] = {
            "year_retired": row[1] or row[7],  # prefer lego_items, fallback BE
            "retiring_soon": bool(row[2]),
            "be_future_estimate_cents": row[3],
            "be_future_estimate_date": row[4],
            "be_annual_growth_pct": row[5],
            "be_value_new_cents": row[6],
            "ml_growth_pct": row[8],
            "ml_confidence": row[9],
            "bl_price_cents": row[10],
            "bl_currency": row[11],
            "bl_6mo_avg_price_cents": _extract_price(six_month_new),
            "bl_current_avg_price_cents": _extract_price(current_new),
            "bl_6mo_times_sold": _extract_int(six_month_new, "times_sold"),
        }

    inputs: list[ForwardReturnInput] = []
    for sn, holding in holdings_map.items():
        enr = enrichment_map.get(sn, {})
        bl_cents = _to_myr(enr.get("bl_price_cents"), enr.get("bl_currency"))
        market_price = bl_cents or 0

        inputs.append(
            ForwardReturnInput(
                set_number=sn,
                cost_basis_cents=holding["avg_cost_cents"],
                acquisition_price_cents=None,
                market_price_cents=market_price,
                bricklink_new_cents=bl_cents,
                be_future_estimate_cents=_usd_to_myr(enr.get("be_future_estimate_cents")),
                be_future_estimate_date=enr.get("be_future_estimate_date"),
                be_annual_growth_pct=enr.get("be_annual_growth_pct"),
                be_value_new_cents=_usd_to_myr(enr.get("be_value_new_cents")),
                ml_growth_pct=enr.get("ml_growth_pct"),
                ml_confidence=enr.get("ml_confidence"),
                ml_avoid_probability=None,
                year_retired=enr.get("year_retired"),
                retiring_soon=enr.get("retiring_soon", False),
                is_held=True,
                bl_6mo_avg_price_cents=enr.get("bl_6mo_avg_price_cents"),
                bl_current_avg_price_cents=enr.get("bl_current_avg_price_cents"),
                bl_6mo_times_sold=enr.get("bl_6mo_times_sold"),
            )
        )

    return inputs


def get_candidate_inputs(
    conn: Any,
    held_inputs: list[ForwardReturnInput],
) -> list[ForwardReturnInput]:
    """Build ForwardReturnInput for non-held sets with retail prices."""
    held_sns = {inp.set_number for inp in held_inputs}

    rows = conn.execute(
        """
        WITH latest_per_source AS (
            SELECT set_number, price_cents, currency,
                   ROW_NUMBER() OVER (
                       PARTITION BY set_number, source ORDER BY recorded_at DESC
                   ) AS rn
            FROM price_records
            WHERE source IN ('shopee', 'toysrus', 'mightyutan', 'hobbydigi')
        ),
        latest_retail AS (
            SELECT set_number, price_cents AS min_retail_cents, currency AS retail_currency
            FROM (
                SELECT set_number, price_cents, currency,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY price_cents ASC) AS rn2
                FROM latest_per_source WHERE rn = 1
            ) ranked WHERE rn2 = 1
        ),
        latest_be AS (
            SELECT set_number, future_estimate_cents, future_estimate_date,
                   annual_growth_pct, value_new_cents, year_retired AS be_year_retired
            FROM (
                SELECT set_number, future_estimate_cents, future_estimate_date,
                       annual_growth_pct, value_new_cents, year_retired,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
                FROM brickeconomy_snapshots
            ) sub WHERE rn = 1
        ),
        latest_ml AS (
            SELECT set_number, predicted_growth_pct, confidence
            FROM (
                SELECT set_number, predicted_growth_pct, confidence,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY snapshot_date DESC) AS rn
                FROM ml_prediction_snapshots
            ) sub WHERE rn = 1
        ),
        latest_bl AS (
            SELECT set_number, price_cents AS bl_price_cents, currency AS bl_currency
            FROM (
                SELECT set_number, price_cents, currency,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
                FROM price_records
                WHERE source = 'bricklink_new'
            ) sub WHERE rn = 1
        ),
        latest_bph AS (
            SELECT set_number, six_month_new, current_new
            FROM (
                SELECT set_number, six_month_new, current_new,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
                FROM bricklink_price_history
            ) sub WHERE rn = 1
        )
        SELECT li.set_number,
               li.year_retired, li.retiring_soon, li.rrp_cents,
               rt.min_retail_cents, rt.retail_currency,
               be.future_estimate_cents, be.future_estimate_date,
               be.annual_growth_pct, be.value_new_cents, be.be_year_retired,
               ml.predicted_growth_pct, ml.confidence,
               bl.bl_price_cents, bl.bl_currency,
               bph.six_month_new, bph.current_new
        FROM lego_items li
        LEFT JOIN latest_retail rt ON rt.set_number = li.set_number
        LEFT JOIN latest_be be ON be.set_number = li.set_number
        LEFT JOIN latest_ml ml ON ml.set_number = li.set_number
        LEFT JOIN latest_bl bl ON bl.set_number = li.set_number
        LEFT JOIN latest_bph bph ON bph.set_number = li.set_number
        WHERE (rt.min_retail_cents IS NOT NULL OR li.rrp_cents IS NOT NULL)
        """
    ).fetchall()

    inputs: list[ForwardReturnInput] = []
    for row in rows:
        sn = row[0]
        if sn in held_sns:
            continue

        year_retired = row[1] or row[10]
        retiring_soon = bool(row[2])
        rrp_cents = row[3]
        retail_cents = row[4]
        retail_currency = row[5]

        # Best acquisition price: retail if available, else RRP
        acq_price = None
        if retail_cents is not None:
            acq_price = (
                retail_cents
                if retail_currency == "MYR"
                else round(retail_cents * MYR_PER_USD)
            )
        elif rrp_cents is not None:
            acq_price = rrp_cents

        bl_cents = _to_myr(row[13], row[14])
        market_price = bl_cents or acq_price or 0

        six_month_new = row[15] or {}
        current_new = row[16] or {}

        inputs.append(
            ForwardReturnInput(
                set_number=sn,
                cost_basis_cents=None,
                acquisition_price_cents=acq_price,
                market_price_cents=market_price,
                bricklink_new_cents=bl_cents,
                be_future_estimate_cents=_usd_to_myr(row[6]),
                be_future_estimate_date=row[7],
                be_annual_growth_pct=row[8],
                be_value_new_cents=_usd_to_myr(row[9]),
                ml_growth_pct=row[11],
                ml_confidence=row[12],
                ml_avoid_probability=None,
                year_retired=year_retired,
                retiring_soon=retiring_soon,
                is_held=False,
                bl_6mo_avg_price_cents=_extract_price(six_month_new),
                bl_current_avg_price_cents=_extract_price(current_new),
                bl_6mo_times_sold=_extract_int(six_month_new, "times_sold"),
            )
        )

    return inputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_price(bl_json: dict) -> int | None:
    """Extract qty_avg_price amount from BL price history JSONB."""
    qty_avg = bl_json.get("qty_avg_price")
    if qty_avg and isinstance(qty_avg, dict):
        amount = qty_avg.get("amount")
        if amount is not None and amount > 0:
            return int(amount)
    # Fallback to avg_price
    avg = bl_json.get("avg_price")
    if avg and isinstance(avg, dict):
        amount = avg.get("amount")
        if amount is not None and amount > 0:
            return int(amount)
    return None


def _extract_int(bl_json: dict, key: str) -> int | None:
    """Extract an integer field from BL price history JSONB."""
    val = bl_json.get(key)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return None


def _to_myr(price_cents: int | None, currency: str | None) -> int | None:
    """Convert price to MYR cents. Returns None if input is None."""
    if price_cents is None:
        return None
    if currency == "MYR":
        return price_cents
    return round(price_cents * MYR_PER_USD)


def _usd_to_myr(cents: int | None) -> int | None:
    """Convert USD cents to MYR cents. BE values are always USD."""
    if cents is None:
        return None
    return round(cents * MYR_PER_USD)


def result_to_dict(r: ForwardReturnResult) -> dict:
    """Convert ForwardReturnResult to a JSON-serializable dict."""
    return {
        "set_number": r.set_number,
        "forward_annual_return": r.forward_annual_return,
        "expected_future_price_cents": r.expected_future_price_cents,
        "current_price_cents": r.current_price_cents,
        "expected_time_years": r.expected_time_years,
        "price_source": r.price_source,
        "decision": r.decision,
        "exceeds_target": r.exceeds_target,
        "exceeds_hurdle": r.exceeds_hurdle,
    }
