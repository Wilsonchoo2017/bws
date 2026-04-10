"""Portfolio API routes -- transactions, holdings, and summary."""

import logging
import time
from typing import Any
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from api.dependencies import get_db
from api.jobs import job_manager
from services.items.repository import get_or_create_item
from services.portfolio.repository import (
    create_transaction,
    delete_transaction,
    delete_transactions_by_bill,
    get_holding_detail,
    get_holdings,
    get_portfolio_summary,
    get_transaction,
    list_transactions,
    update_transaction,
)
from services.portfolio.forward_return_query import (
    get_holdings_forward_returns,
)
from services.portfolio.reallocation import get_reallocation_analysis
from services.portfolio.wbr_metrics import calculate_wbr


logger = logging.getLogger("bws.api.portfolio")

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class CreateTransactionRequest(BaseModel):
    set_number: str = Field(
        ..., min_length=1, max_length=20, pattern=r"^\d{3,6}(-\d+)?$"
    )
    txn_type: str = Field(..., pattern=r"^(BUY|SELL)$")
    quantity: int = Field(..., gt=0)
    price_cents: int = Field(..., gt=0)
    condition: str = Field(default="new", pattern=r"^(new|used)$")
    txn_date: datetime
    currency: str = Field(default="MYR", max_length=3)
    notes: str | None = None
    supplier: str | None = Field(default=None, max_length=100)
    platform: str | None = Field(default=None, max_length=100)


@router.post("/transactions", status_code=201)
async def add_transaction(request: CreateTransactionRequest, conn: Any = Depends(get_db)) -> dict:
    """Record a BUY or SELL transaction."""
    # Auto-create lego_items entry and queue enrichment if metadata missing
    get_or_create_item(conn, request.set_number)
    row = conn.execute(
        "SELECT title, theme, image_url FROM lego_items WHERE set_number = ?",
        [request.set_number],
    ).fetchone()
    if row and (row[0] is None or row[1] is None or row[2] is None):
        job_manager.create_job("enrichment", request.set_number, reason="missing metadata on transaction add")
        logger.info("Queued enrichment for set %s", request.set_number)

    txn_id = create_transaction(
        conn,
        request.set_number,
        request.txn_type,
        request.quantity,
        request.price_cents,
        request.condition,
        request.txn_date,
        currency=request.currency,
        notes=request.notes,
        supplier=request.supplier,
        platform=request.platform,
    )
    txn = get_transaction(conn, txn_id)
    return {"success": True, "data": txn}


class BillLineItem(BaseModel):
    set_number: str = Field(
        ..., min_length=1, max_length=20, pattern=r"^\d{3,6}(-\d+)?$"
    )
    quantity: int = Field(..., gt=0)
    unit_price_cents: int = Field(..., gt=0)


class CreateBillRequest(BaseModel):
    items: list[BillLineItem] = Field(..., min_length=1, max_length=50)
    final_amount_cents: int = Field(..., gt=0)
    txn_date: datetime
    txn_type: str = Field(default="BUY", pattern=r"^(BUY|SELL)$")
    condition: str = Field(default="new", pattern=r"^(new|used)$")
    currency: str = Field(default="MYR", max_length=3)
    notes: str | None = None
    supplier: str | None = Field(default=None, max_length=100)
    platform: str | None = Field(default=None, max_length=100)


def _compute_effective_prices(
    items: list[BillLineItem], final_amount_cents: int
) -> list[int]:
    """Distribute final_amount proportionally across line items.

    Returns the effective unit price (cents) for each item.
    Uses the "largest remainder" method to distribute rounding error:
    each line's total allocation is computed, then unit price = total // qty,
    with the remainder absorbed by the last line.
    """
    subtotal = sum(item.quantity * item.unit_price_cents for item in items)
    if subtotal <= 0:
        raise ValueError("Subtotal must be positive")

    # Allocate total cents to each line proportionally
    line_totals = [
        round(item.quantity * item.unit_price_cents * final_amount_cents / subtotal)
        for item in items
    ]

    # Fix rounding: adjust the largest line's total so everything sums exactly
    allocated = sum(line_totals)
    remainder = final_amount_cents - allocated
    if remainder != 0:
        largest_idx = max(
            range(len(items)),
            key=lambda i: items[i].quantity * items[i].unit_price_cents,
        )
        line_totals[largest_idx] += remainder

    # Convert line totals back to unit prices (integer division)
    return [line_totals[i] // items[i].quantity for i in range(len(items))]


@router.post("/transactions/bill", status_code=201)
async def add_bill(
    request: CreateBillRequest, conn: Any = Depends(get_db)
) -> dict:
    """Record multiple BUY transactions from a single bill/receipt.

    The final_amount_cents is distributed proportionally across line items
    so that platform discounts, shipping, etc. are reflected in each unit cost.
    """
    effective_prices = _compute_effective_prices(
        request.items, request.final_amount_cents
    )

    # Validate all effective prices are positive
    for i, eff in enumerate(effective_prices):
        if eff <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Adjustment makes price non-positive for {request.items[i].set_number}",
            )

    bill_id = f"bill_{uuid4().hex[:8]}"
    created_txns = []

    for item, eff_price in zip(request.items, effective_prices):
        # Auto-create lego_items entry and queue enrichment
        get_or_create_item(conn, item.set_number)
        row = conn.execute(
            "SELECT title, theme, image_url FROM lego_items WHERE set_number = ?",
            [item.set_number],
        ).fetchone()
        if row and (row[0] is None or row[1] is None or row[2] is None):
            job_manager.create_job("enrichment", item.set_number, reason="missing metadata on bill create")
            logger.info("Queued enrichment for set %s", item.set_number)

        txn_id = create_transaction(
            conn,
            item.set_number,
            request.txn_type,
            item.quantity,
            eff_price,
            request.condition,
            request.txn_date,
            currency=request.currency,
            notes=request.notes,
            bill_id=bill_id,
            supplier=request.supplier,
            platform=request.platform,
        )
        txn = get_transaction(conn, txn_id)
        created_txns.append(txn)

    subtotal = sum(
        item.quantity * item.unit_price_cents for item in request.items
    )
    return {
        "success": True,
        "data": {
            "bill_id": bill_id,
            "transactions": created_txns,
            "subtotal_cents": subtotal,
            "final_amount_cents": request.final_amount_cents,
            "adjustment_cents": request.final_amount_cents - subtotal,
        },
    }


@router.put("/transactions/bill/{bill_id}")
async def update_bill(
    bill_id: str, request: CreateBillRequest, conn: Any = Depends(get_db)
) -> dict:
    """Replace all transactions in a bill with new data.

    Deletes existing transactions for the bill_id, then creates new ones
    with the adjusted prices.
    """
    # Verify the bill exists
    existing = conn.execute(
        "SELECT COUNT(*) FROM portfolio_transactions WHERE bill_id = ?",
        [bill_id],
    ).fetchone()
    if not existing or existing[0] == 0:
        raise HTTPException(status_code=404, detail="Bill not found")

    effective_prices = _compute_effective_prices(
        request.items, request.final_amount_cents
    )

    for i, eff in enumerate(effective_prices):
        if eff <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Adjustment makes price non-positive for {request.items[i].set_number}",
            )

    # Delete old transactions
    delete_transactions_by_bill(conn, bill_id)

    # Create new transactions with the same bill_id
    created_txns = []
    for item, eff_price in zip(request.items, effective_prices):
        get_or_create_item(conn, item.set_number)
        row = conn.execute(
            "SELECT title, theme, image_url FROM lego_items WHERE set_number = ?",
            [item.set_number],
        ).fetchone()
        if row and (row[0] is None or row[1] is None or row[2] is None):
            job_manager.create_job("enrichment", item.set_number, reason="missing metadata on bill update")
            logger.info("Queued enrichment for set %s", item.set_number)

        txn_id = create_transaction(
            conn,
            item.set_number,
            request.txn_type,
            item.quantity,
            eff_price,
            request.condition,
            request.txn_date,
            currency=request.currency,
            notes=request.notes,
            bill_id=bill_id,
            supplier=request.supplier,
            platform=request.platform,
        )
        txn = get_transaction(conn, txn_id)
        created_txns.append(txn)

    subtotal = sum(
        item.quantity * item.unit_price_cents for item in request.items
    )
    return {
        "success": True,
        "data": {
            "bill_id": bill_id,
            "transactions": created_txns,
            "subtotal_cents": subtotal,
            "final_amount_cents": request.final_amount_cents,
            "adjustment_cents": request.final_amount_cents - subtotal,
        },
    }


@router.get("/transactions")
async def list_txns(
    set_number: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    conn: Any = Depends(get_db),
) -> dict:
    """List transactions with optional filters."""
    txns = list_transactions(conn, set_number=set_number, limit=limit, offset=offset)
    return {"success": True, "data": txns, "count": len(txns)}


@router.get("/transactions/{txn_id}")
async def get_txn(txn_id: int, conn: Any = Depends(get_db)) -> dict:
    """Get a single transaction."""
    txn = get_transaction(conn, txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True, "data": txn}


class UpdateTransactionRequest(BaseModel):
    txn_type: str | None = Field(default=None, pattern=r"^(BUY|SELL)$")
    quantity: int | None = Field(default=None, gt=0)
    price_cents: int | None = Field(default=None, gt=0)
    condition: str | None = Field(default=None, pattern=r"^(new|used)$")
    txn_date: datetime | None = None
    notes: str | None = None
    clear_notes: bool = False
    supplier: str | None = None
    clear_supplier: bool = False
    platform: str | None = None
    clear_platform: bool = False


@router.put("/transactions/{txn_id}")
async def edit_transaction(
    txn_id: int, request: UpdateTransactionRequest, conn: Any = Depends(get_db)
) -> dict:
    """Update fields on an existing transaction."""
    kwargs: dict[str, Any] = {}
    if request.txn_type is not None:
        kwargs["txn_type"] = request.txn_type
    if request.quantity is not None:
        kwargs["quantity"] = request.quantity
    if request.price_cents is not None:
        kwargs["price_cents"] = request.price_cents
    if request.condition is not None:
        kwargs["condition"] = request.condition
    if request.txn_date is not None:
        kwargs["txn_date"] = request.txn_date
    if request.clear_notes:
        kwargs["notes"] = None
    elif request.notes is not None:
        kwargs["notes"] = request.notes
    if request.clear_supplier:
        kwargs["supplier"] = None
    elif request.supplier is not None:
        kwargs["supplier"] = request.supplier
    if request.clear_platform:
        kwargs["platform"] = None
    elif request.platform is not None:
        kwargs["platform"] = request.platform

    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = update_transaction(conn, txn_id, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn = get_transaction(conn, txn_id)
    return {"success": True, "data": txn}


@router.delete("/transactions/{txn_id}")
async def remove_txn(txn_id: int, conn: Any = Depends(get_db)) -> dict:
    """Delete a transaction."""
    deleted = delete_transaction(conn, txn_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True, "message": "Transaction deleted"}


@router.get("/holdings")
async def list_holdings(conn: Any = Depends(get_db)) -> dict:
    """Get current holdings with market values and P&L."""
    holdings = get_holdings(conn)
    return {"success": True, "data": holdings, "count": len(holdings)}


@router.get("/holdings/{set_number}")
async def holding_detail(
    set_number: str = Path(..., pattern=r"^\d{3,6}(-\d+)?$"),
    conn: Any = Depends(get_db),
) -> dict:
    """Get holding detail for a single set."""
    detail = get_holding_detail(conn, set_number)
    if not detail:
        raise HTTPException(
            status_code=404,
            detail=f"No transactions found for {set_number}",
        )
    return {"success": True, "data": detail}


@router.post("/enrich")
async def enrich_portfolio_items(conn: Any = Depends(get_db)) -> dict:
    """Queue enrichment for all portfolio sets missing metadata."""
    # Ensure all portfolio sets exist in lego_items first
    missing_items = conn.execute(
        """
        SELECT DISTINCT pt.set_number
        FROM portfolio_transactions pt
        LEFT JOIN lego_items li ON li.set_number = pt.set_number
        WHERE li.set_number IS NULL
        """
    ).fetchall()
    for (sn,) in missing_items:
        get_or_create_item(conn, sn)

    # Queue enrichment for ALL portfolio sets (force re-enrich)
    # Reset last_enriched_at so the enrichment worker won't skip them
    conn.execute(
        """
        UPDATE lego_items SET last_enriched_at = NULL
        WHERE set_number IN (
            SELECT DISTINCT set_number FROM portfolio_transactions
        )
        """
    )

    rows = conn.execute(
        "SELECT DISTINCT set_number FROM portfolio_transactions"
    ).fetchall()

    queued = []
    for (set_number,) in rows:
        job_manager.create_job("enrichment", set_number, reason="manual re-enrich sweep")
        queued.append(set_number)

    return {
        "success": True,
        "data": {"queued": len(queued), "set_numbers": queued},
    }


@router.get("/summary")
async def portfolio_summary(conn: Any = Depends(get_db)) -> dict:
    """Get portfolio-wide summary totals."""
    summary = get_portfolio_summary(conn)
    return {"success": True, "data": summary}


# ---------------------------------------------------------------------------
# Forward Return & Decision Engine
# ---------------------------------------------------------------------------

_fr_cache: dict = {}
_FR_TTL = 600  # 10 minutes


@router.get("/forward-returns")
async def forward_returns(
    refresh: bool = Query(default=False),
    conn: Any = Depends(get_db),
) -> dict:
    """Holdings with forward annual return calculations and decisions."""
    now = time.time()
    cache_key = "holdings_fr"

    if not refresh and cache_key in _fr_cache and _fr_cache[cache_key]["expires"] > now:
        cached = _fr_cache[cache_key]["data"]
        return {"success": True, "data": cached, "count": len(cached), "cached": True}

    data = get_holdings_forward_returns(conn)
    _fr_cache[cache_key] = {"data": data, "expires": now + _FR_TTL}
    return {"success": True, "data": data, "count": len(data)}



@router.get("/wbr")
async def wbr_metrics(conn: Any = Depends(get_db)) -> dict:
    """Weekly Business Review metrics for capital allocation."""
    now = time.time()
    cache_key = "wbr"

    if cache_key in _fr_cache and _fr_cache[cache_key]["expires"] > now:
        return {"success": True, "data": _fr_cache[cache_key]["data"], "cached": True}

    data = calculate_wbr(conn)
    _fr_cache[cache_key] = {"data": data, "expires": now + _FR_TTL}
    return {"success": True, "data": data}


@router.get("/reallocation")
async def reallocation_analysis(
    refresh: bool = Query(default=False),
    conn: Any = Depends(get_db),
) -> dict:
    """Hold vs. Sell opportunity cost analysis for all holdings."""
    now = time.time()
    cache_key = "reallocation"

    if not refresh and cache_key in _fr_cache and _fr_cache[cache_key]["expires"] > now:
        return {"success": True, "data": _fr_cache[cache_key]["data"], "cached": True}

    data = get_reallocation_analysis(conn)
    _fr_cache[cache_key] = {"data": data, "expires": now + _FR_TTL}
    return {"success": True, "data": data}
