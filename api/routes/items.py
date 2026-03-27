"""Items API routes."""

from fastapi import APIRouter, HTTPException

from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import get_all_items, get_item_detail
from services.shopee.repository import get_all_products

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


@router.get("/{set_number}")
async def get_item(set_number: str):
    """Get a single item with full price history from all sources."""
    try:
        conn = get_connection()
        init_schema(conn)
        item = get_item_detail(conn, set_number)
        conn.close()
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
        return {"success": True, "data": item}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
