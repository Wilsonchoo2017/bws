"""Items API routes."""


from fastapi import APIRouter, HTTPException

from db.connection import get_connection
from db.schema import init_schema
from services.shopee.repository import get_all_products

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/shopee")
async def list_shopee_products():
    """List all scraped Shopee products from the database."""
    try:
        conn = get_connection()
        init_schema(conn)
        products = get_all_products(conn)
        conn.close()
        return {"success": True, "data": products, "count": len(products)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
