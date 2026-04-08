"""Listing automation API routes."""

import threading

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/listing", tags=["listing"])


class ListRequest(BaseModel):
    set_number: str
    platform: str  # "shopee" for now


@router.post("/login")
async def listing_login(request: ListRequest):
    """Open the seller portal, log in, and create a product listing.

    Runs in a background thread so the API responds immediately.
    The browser will be left open for user review before publishing.
    """
    if request.platform != "shopee":
        return {"success": False, "error": f"Unsupported platform: {request.platform}"}

    from services.listing.shopee import create_listing

    thread = threading.Thread(
        target=create_listing,
        args=(request.set_number,),
        daemon=True,
    )
    thread.start()

    return {"success": True, "message": "Creating Shopee listing..."}
