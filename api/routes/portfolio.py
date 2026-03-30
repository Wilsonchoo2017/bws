"""Portfolio API routes -- transactions, holdings, and summary."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from api.jobs import job_manager
from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import get_or_create_item
from services.portfolio.repository import (
    create_transaction,
    delete_transaction,
    get_holding_detail,
    get_holdings,
    get_portfolio_summary,
    get_transaction,
    list_transactions,
)

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


@router.post("/transactions", status_code=201)
async def add_transaction(request: CreateTransactionRequest) -> dict:
    """Record a BUY or SELL transaction."""
    conn = get_connection()
    try:
        init_schema(conn)

        # Auto-create lego_items entry and queue enrichment if metadata missing
        get_or_create_item(conn, request.set_number)
        row = conn.execute(
            "SELECT title, theme, image_url FROM lego_items WHERE set_number = ?",
            [request.set_number],
        ).fetchone()
        if row and (row[0] is None or row[1] is None or row[2] is None):
            job_manager.create_job("enrichment", request.set_number)
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
        )
        txn = get_transaction(conn, txn_id)
        return {"success": True, "data": txn}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create transaction")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.get("/transactions")
async def list_txns(
    set_number: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List transactions with optional filters."""
    conn = get_connection()
    try:
        init_schema(conn)
        txns = list_transactions(conn, set_number=set_number, limit=limit, offset=offset)
        return {"success": True, "data": txns, "count": len(txns)}
    except Exception:
        logger.exception("Failed to list transactions")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.get("/transactions/{txn_id}")
async def get_txn(txn_id: int) -> dict:
    """Get a single transaction."""
    conn = get_connection()
    try:
        init_schema(conn)
        txn = get_transaction(conn, txn_id)
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return {"success": True, "data": txn}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get transaction %d", txn_id)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.delete("/transactions/{txn_id}")
async def remove_txn(txn_id: int) -> dict:
    """Delete a transaction."""
    conn = get_connection()
    try:
        init_schema(conn)
        deleted = delete_transaction(conn, txn_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return {"success": True, "message": "Transaction deleted"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to delete transaction %d", txn_id)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.get("/holdings")
async def list_holdings() -> dict:
    """Get current holdings with market values and P&L."""
    conn = get_connection()
    try:
        init_schema(conn)
        holdings = get_holdings(conn)
        return {"success": True, "data": holdings, "count": len(holdings)}
    except Exception:
        logger.exception("Failed to get holdings")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.get("/holdings/{set_number}")
async def holding_detail(
    set_number: str = Path(..., pattern=r"^\d{3,6}(-\d+)?$"),
) -> dict:
    """Get holding detail for a single set."""
    conn = get_connection()
    try:
        init_schema(conn)
        detail = get_holding_detail(conn, set_number)
        if not detail:
            raise HTTPException(
                status_code=404,
                detail=f"No transactions found for {set_number}",
            )
        return {"success": True, "data": detail}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get holding detail for %s", set_number)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.post("/enrich")
async def enrich_portfolio_items() -> dict:
    """Queue enrichment for all portfolio sets missing metadata."""
    conn = get_connection()
    try:
        init_schema(conn)
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
            job_manager.create_job("enrichment", set_number)
            queued.append(set_number)

        return {
            "success": True,
            "data": {"queued": len(queued), "set_numbers": queued},
        }
    except Exception:
        logger.exception("Failed to enrich portfolio items")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.get("/summary")
async def portfolio_summary() -> dict:
    """Get portfolio-wide summary totals."""
    conn = get_connection()
    try:
        init_schema(conn)
        summary = get_portfolio_summary(conn)
        return {"success": True, "data": summary}
    except Exception:
        logger.exception("Failed to get portfolio summary")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()
