"""Items API routes."""

import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.connection import get_connection
from db.schema import init_schema
from services.bricklink.repository import (
    get_monthly_sales,
    get_price_history,
    get_set_minifigures,
    get_set_minifig_value_history,
)
from services.bricklink.scraper import scrape_set_minifigures
from services.backtesting.kelly import (
    compute_position_sizing,
    kelly_to_dict,
)
from services.backtesting.screener import (
    compute_all_signals,
    compute_all_signals_with_cohort,
    compute_item_signals,
)
from services.items.repository import get_all_items, get_all_items_lite, get_item_detail, get_or_create_item, item_exists, toggle_watchlist, update_buy_rating
from services.shopee.repository import get_all_products
from services.shopee.saturation_repository import (
    get_all_latest_saturations,
    get_latest_saturation,
)

router = APIRouter(prefix="/items", tags=["items"])


def _sanitize_nan(data: list[dict]) -> list[dict]:
    """Replace NaN float values with None for JSON-safe serialization."""
    return [
        {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
        for row in data
    ]


class AddItemRequest(BaseModel):
    set_number: str = Field(
        ..., min_length=1, max_length=20, pattern=r"^\d{3,6}(-\d+)?$"
    )


class UpdateBuyRatingRequest(BaseModel):
    rating: int | None = Field(None, ge=1, le=4)


@router.post("", status_code=201)
async def add_item(request: AddItemRequest):
    """Add a new LEGO set to the catalog by set number."""
    conn = get_connection()
    try:
        init_schema(conn)
        if item_exists(conn, request.set_number):
            raise HTTPException(
                status_code=409,
                detail=f"Item {request.set_number} already exists",
            )
        get_or_create_item(conn, request.set_number)
        item = get_item_detail(conn, request.set_number)
        return {"success": True, "data": item, "message": f"Item {request.set_number} created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.patch("/{set_number}/watchlist")
async def toggle_item_watchlist(set_number: str):
    """Toggle watchlist status for an item."""
    conn = get_connection()
    try:
        init_schema(conn)
        new_value = toggle_watchlist(conn, set_number)
        if new_value is None:
            raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
        return {"success": True, "data": {"set_number": set_number, "watchlist": new_value}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/{set_number}/buy-rating")
async def set_buy_rating(set_number: str, request: UpdateBuyRatingRequest):
    """Set or clear the buy rating for an item."""
    conn = get_connection()
    try:
        init_schema(conn)
        result = update_buy_rating(conn, set_number, request.rating)
        if result is None and request.rating is not None:
            raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
        # For clearing (rating=None), we still need to check item exists
        if request.rating is None:
            row = conn.execute(
                "SELECT 1 FROM lego_items WHERE set_number = ?", [set_number]
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
        return {"success": True, "data": {"set_number": set_number, "buy_rating": request.rating}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/lite")
async def list_items_lite():
    """List all LEGO items with catalog data only (no prices). Fast path for initial load."""
    try:
        conn = get_connection()
        init_schema(conn)
        items = get_all_items_lite(conn)
        conn.close()
        return {"success": True, "data": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """Compute current trading signals for all items with cohort rankings."""
    try:
        conn = get_connection()
        init_schema(conn)
        signals = compute_all_signals_with_cohort(conn, condition=condition)
        conn.close()
        return {"success": True, "data": _sanitize_nan(signals), "count": len(signals)}
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
    """Compute current trading signals for a single item with cohort context."""
    try:
        conn = get_connection()
        init_schema(conn)
        # Compute all signals to get cohort context, then filter
        all_signals = compute_all_signals_with_cohort(conn, condition=condition)
        conn.close()
        match = next(
            (s for s in all_signals if s["set_number"] == set_number),
            None,
        )
        if not match:
            return {"success": True, "data": None}
        return {"success": True, "data": _sanitize_nan([match])[0]}
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


@router.get("/{set_number}/minifigures")
async def get_item_minifigures(set_number: str):
    """Get minifigure inventory and values for a LEGO set."""
    conn = get_connection()
    try:
        init_schema(conn)

        # Find bricklink item_id matching this set_number
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE item_id LIKE ?",
            [f"{set_number}-%"],
        ).fetchall()

        if not rows:
            return {"success": True, "data": {"minifig_count": 0, "minifigures": []}}

        item_id = rows[0][0]
        minifigs = get_set_minifigures(conn, item_id)

        # Compute total value
        total_value_cents = 0
        has_value = False
        for mf in minifigs:
            if mf["current_new_avg_cents"] is not None:
                total_value_cents += mf["current_new_avg_cents"] * mf["quantity"]
                has_value = True

        return {
            "success": True,
            "data": {
                "set_item_id": item_id,
                "minifig_count": len(minifigs),
                "total_value_cents": total_value_cents if has_value else None,
                "total_value_currency": minifigs[0]["currency"] if minifigs else "USD",
                "minifigures": minifigs,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{set_number}/minifigures/value-history")
async def get_minifig_value_history(set_number: str):
    """Get aggregated minifigure value history for a LEGO set."""
    conn = get_connection()
    try:
        init_schema(conn)

        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE item_id LIKE ?",
            [f"{set_number}-%"],
        ).fetchall()

        if not rows:
            return {"success": True, "data": {"snapshots": []}}

        item_id = rows[0][0]
        snapshots = get_set_minifig_value_history(conn, item_id)

        return {"success": True, "data": {"snapshots": snapshots}}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch minifigure value history")
    finally:
        conn.close()


@router.post("/{set_number}/minifigures/scrape")
async def scrape_item_minifigures(set_number: str):
    """Trigger minifigure scraping for a LEGO set."""
    conn = get_connection()
    try:
        init_schema(conn)

        # Find bricklink item_id
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE item_id LIKE ?",
            [f"{set_number}-%"],
        ).fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"Set {set_number} not found in BrickLink data. Scrape the set first.",
            )

        item_id = rows[0][0]
        result = await scrape_set_minifigures(conn, item_id, save=True, scrape_prices=True)

        return {
            "success": result.success,
            "data": {
                "set_item_id": result.set_item_id,
                "minifig_count": result.minifig_count,
                "minifigures_scraped": result.minifigures_scraped,
                "total_value_cents": result.total_value_cents,
            },
            "error": result.error,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


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


@router.get("/{set_number}/brickeconomy")
async def get_item_brickeconomy(set_number: str):
    """Get the latest BrickEconomy snapshot for an item."""
    conn = get_connection()
    try:
        init_schema(conn)

        from services.brickeconomy.repository import get_latest_snapshot

        snapshot = get_latest_snapshot(conn, set_number)
        # Try with -1 suffix if bare number didn't match
        if not snapshot and "-" not in set_number:
            snapshot = get_latest_snapshot(conn, f"{set_number}-1")
        if not snapshot:
            return {"success": True, "data": None}

        # Ensure datetime is serialized as ISO string
        if snapshot.get("scraped_at"):
            snapshot["scraped_at"] = str(snapshot["scraped_at"])

        return {"success": True, "data": snapshot}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{set_number}/keepa")
async def get_item_keepa(set_number: str):
    """Get the latest Keepa snapshot for an item."""
    conn = get_connection()
    try:
        init_schema(conn)

        from services.keepa.repository import get_latest_keepa_snapshot

        snapshot = get_latest_keepa_snapshot(conn, set_number)
        if not snapshot:
            return {"success": True, "data": None}

        if snapshot.get("scraped_at"):
            snapshot["scraped_at"] = str(snapshot["scraped_at"])

        return {"success": True, "data": snapshot}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{set_number}/trends")
async def get_item_trends(set_number: str):
    """Get the latest Google Trends snapshot for an item."""
    conn = get_connection()
    try:
        init_schema(conn)

        from services.google_trends.repository import get_latest_trends_snapshot

        snapshot = get_latest_trends_snapshot(conn, set_number)
        if not snapshot:
            return {"success": True, "data": None}

        if snapshot.get("scraped_at"):
            snapshot["scraped_at"] = str(snapshot["scraped_at"])

        return {"success": True, "data": snapshot}
    except Exception:
        logger.exception("Failed to fetch trends for %s", set_number)
        raise HTTPException(status_code=500, detail="Internal server error")
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
