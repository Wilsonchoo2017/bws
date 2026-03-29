"""Items API routes."""

from fastapi import APIRouter, HTTPException

from db.connection import get_connection
from db.schema import init_schema
from services.bricklink.repository import (
    get_monthly_sales,
    get_price_history,
)
from services.backtesting.kelly import (
    compute_position_sizing,
    kelly_to_dict,
)
from services.backtesting.screener import (
    compute_all_signals,
    compute_item_signals,
)
from services.items.repository import get_all_items, get_item_detail
from services.shopee.repository import get_all_products
from services.shopee.saturation_repository import (
    get_all_latest_saturations,
    get_latest_saturation,
)

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
async def list_items():
    """List all LEGO items with latest prices from each source."""
    try:
        conn = get_connection()
        init_schema(conn)
        items = get_all_items(conn)
        conn.close()
        return {"success": True, "data": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals")
async def list_signals(condition: str = "new"):
    """Compute current trading signals for all items."""
    try:
        conn = get_connection()
        init_schema(conn)
        signals = compute_all_signals(conn, condition=condition)
        conn.close()
        return {"success": True, "data": signals, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shopee")
async def list_shopee_products():
    """List all raw Shopee products from the database."""
    try:
        conn = get_connection()
        init_schema(conn)
        products = get_all_products(conn)
        conn.close()
        return {"success": True, "data": products, "count": len(products)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/saturation")
async def list_saturations():
    """List latest Shopee saturation data for all items."""
    conn = get_connection()
    try:
        init_schema(conn)
        data = get_all_latest_saturations(conn)
        return {"success": True, "data": data, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{set_number}/saturation")
async def get_item_saturation(set_number: str):
    """Get Shopee market saturation data for a LEGO set."""
    conn = get_connection()
    try:
        init_schema(conn)
        data = get_latest_saturation(conn, set_number)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{set_number}/kelly")
async def get_item_kelly(
    set_number: str,
    budget: int | None = None,
    condition: str = "new",
):
    """Compute Kelly Criterion position sizing for a single item."""
    conn = get_connection()
    try:
        init_schema(conn)
        sizing = compute_position_sizing(
            conn, set_number, budget_cents=budget, condition=condition
        )
        if not sizing:
            return {"success": True, "data": None}
        return {"success": True, "data": kelly_to_dict(sizing)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{set_number}/signals")
async def get_item_signals(set_number: str, condition: str = "new"):
    """Compute current trading signals for a single item."""
    try:
        conn = get_connection()
        init_schema(conn)
        signals = compute_item_signals(conn, set_number, condition=condition)
        conn.close()
        if not signals:
            return {"success": True, "data": None}
        return {"success": True, "data": signals}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{set_number}")
async def get_item(set_number: str):
    """Get a single item with full price history from all sources."""
    try:
        conn = get_connection()
        init_schema(conn)
        item = get_item_detail(conn, set_number)
        if not item:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
        item["saturation"] = get_latest_saturation(conn, set_number)
        conn.close()
        return {"success": True, "data": item}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{set_number}/bricklink-prices")
async def get_item_bricklink_prices(set_number: str):
    """Get BrickLink price history and monthly sales for an item."""
    conn = get_connection()
    try:
        init_schema(conn)

        # Find bricklink item_id(s) matching this set_number
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE item_id LIKE ?",
            [f"{set_number}-%"],
        ).fetchall()

        if not rows:
            return {"success": True, "data": {"price_history": [], "monthly_sales": []}}

        item_id = rows[0][0]

        history = get_price_history(conn, item_id, limit=50)
        sales = get_monthly_sales(conn, item_id)

        serialized_history = [
            {
                "scraped_at": str(h["scraped_at"]) if h["scraped_at"] else None,
                "six_month_new": _serialize_box(h["six_month_new"]),
                "six_month_used": _serialize_box(h["six_month_used"]),
                "current_new": _serialize_box(h["current_new"]),
                "current_used": _serialize_box(h["current_used"]),
            }
            for h in history
        ]

        serialized_sales = [
            {
                "year": s.year,
                "month": s.month,
                "condition": s.condition.value,
                "times_sold": s.times_sold,
                "total_quantity": s.total_quantity,
                "min_price_cents": s.min_price.amount if s.min_price else None,
                "max_price_cents": s.max_price.amount if s.max_price else None,
                "avg_price_cents": s.avg_price.amount if s.avg_price else None,
                "currency": s.currency,
            }
            for s in sales
        ]

        return {
            "success": True,
            "data": {
                "item_id": item_id,
                "price_history": serialized_history,
                "monthly_sales": serialized_sales,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _serialize_box(box) -> dict | None:
    """Serialize a PricingBox to a JSON-friendly dict."""
    if box is None:
        return None
    return {
        "times_sold": box.times_sold,
        "total_lots": box.total_lots,
        "total_qty": box.total_qty,
        "min_price_cents": box.min_price.amount if box.min_price else None,
        "avg_price_cents": box.avg_price.amount if box.avg_price else None,
        "qty_avg_price_cents": box.qty_avg_price.amount if box.qty_avg_price else None,
        "max_price_cents": box.max_price.amount if box.max_price else None,
        "currency": (
            box.avg_price.currency
            if box.avg_price
            else (box.min_price.currency if box.min_price else "USD")
        ),
    }
