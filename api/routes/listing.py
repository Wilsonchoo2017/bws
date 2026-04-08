"""Listing automation and marketplace tracking API routes."""

import logging
import threading
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_db
from services.listing.repository import (
    get_active_listings_for_set,
    get_listings_for_set,
    record_listing,
    update_listing_status,
)

logger = logging.getLogger("bws.api.listing")

router = APIRouter(prefix="/listing", tags=["listing"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ListRequest(BaseModel):
    set_number: str
    platform: Literal["shopee", "carousell", "facebook"]


class RecordListingRequest(BaseModel):
    set_number: str
    platform: Literal["shopee", "carousell", "facebook"]
    listing_price_cents: int
    currency: str = "MYR"


class UpdateStatusRequest(BaseModel):
    set_number: str
    platform: Literal["shopee", "carousell", "facebook"]
    status: Literal["active", "sold", "delisted"]


# ---------------------------------------------------------------------------
# Browser automation
# ---------------------------------------------------------------------------


def _run_listing(fn: Callable[[str], bool], set_number: str) -> None:
    """Run listing creation in a thread with error logging."""
    try:
        fn(set_number)
    except Exception:
        logger.exception("Listing creation failed for %s", set_number)


@router.post("/login")
async def listing_login(request: ListRequest) -> dict[str, Any]:
    """Open the seller portal, log in, and create a product listing.

    Runs in a background thread so the API responds immediately.
    """
    if request.platform == "shopee":
        from services.listing.shopee import create_listing
    elif request.platform == "facebook":
        from services.listing.facebook import create_listing
    else:
        from services.listing.carousell import create_listing

    thread = threading.Thread(
        target=_run_listing,
        args=(create_listing, request.set_number),
        daemon=True,
    )
    thread.start()

    return {"success": True, "message": f"Creating {request.platform} listing..."}


# ---------------------------------------------------------------------------
# Listing CRUD
# ---------------------------------------------------------------------------


@router.post("/record")
async def record_marketplace_listing(
    request: RecordListingRequest, conn: Any = Depends(get_db),
) -> dict[str, Any]:
    """Record that a set has been listed on a marketplace."""
    record_listing(
        conn,
        set_number=request.set_number,
        platform=request.platform,
        listing_price_cents=request.listing_price_cents,
        currency=request.currency,
    )
    return {
        "success": True,
        "message": f"{request.set_number} listed on {request.platform}",
    }


@router.put("/status")
async def update_marketplace_status(
    request: UpdateStatusRequest, conn: Any = Depends(get_db),
) -> dict[str, Any]:
    """Update listing status (active / sold / delisted)."""
    updated = update_listing_status(
        conn,
        set_number=request.set_number,
        platform=request.platform,
        status=request.status,
    )
    if not updated:
        return {"success": False, "error": "Listing not found"}
    return {
        "success": True,
        "message": f"{request.set_number} on {request.platform} -> {request.status}",
    }


@router.get("/{set_number}")
async def get_set_listings(
    set_number: str, conn: Any = Depends(get_db),
) -> dict[str, Any]:
    """Get all marketplace listings for a set."""
    listings = get_listings_for_set(conn, set_number)
    active = get_active_listings_for_set(conn, set_number)
    return {
        "success": True,
        "data": {
            "set_number": set_number,
            "listed_on": active,
            "listings": listings,
        },
    }
