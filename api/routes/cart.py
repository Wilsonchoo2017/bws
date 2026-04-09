"""Cart API routes -- auto-scan and manual cart management."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field, field_validator

from api.dependencies import get_db

logger = logging.getLogger("bws.api.cart")

COOLDOWN_DAYS = 30

router = APIRouter(prefix="/cart", tags=["cart"])

_SET_NUMBER_RE = re.compile(r"^\d{3,6}(-\d+)?$")


class AddCartItemRequest(BaseModel):
    set_number: str = Field(..., min_length=1, max_length=20, pattern=r"^\d{3,6}(-\d+)?$")


class SyncCartRequest(BaseModel):
    set_numbers: list[str] = Field(..., max_length=500)

    @field_validator("set_numbers")
    @classmethod
    def validate_entries(cls, v: list[str]) -> list[str]:
        for sn in v:
            if not _SET_NUMBER_RE.match(sn):
                raise ValueError(f"Invalid set number: {sn}")
        return v


def _fetch_cart(conn: Any) -> list[dict[str, Any]]:
    """Return all cart items as a list of dicts."""
    rows = conn.execute(
        "SELECT set_number, source, added_at FROM cart_items ORDER BY added_at DESC"
    ).fetchall()
    return [
        {"set_number": r[0], "source": r[1], "added_at": str(r[2])}
        for r in rows
    ]


def _fetch_banned(conn: Any) -> set[str]:
    """Return all banned set numbers."""
    rows = conn.execute("SELECT set_number FROM cart_banned").fetchall()
    return {r[0] for r in rows}


def _fetch_on_cooldown(conn: Any) -> set[str]:
    """Return set numbers removed within the cooldown window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
    rows = conn.execute(
        "SELECT set_number FROM cart_removals WHERE removed_at >= ?",
        [cutoff],
    ).fetchall()
    return {r[0] for r in rows}


def _record_removal(conn: Any, set_number: str) -> None:
    """Upsert a removal timestamp for cooldown tracking."""
    conn.execute(
        """INSERT INTO cart_removals (set_number, removed_at)
           VALUES (?, CURRENT_TIMESTAMP)
           ON CONFLICT (set_number) DO UPDATE SET removed_at = CURRENT_TIMESTAMP""",
        [set_number],
    )


@router.get("")
async def list_cart(conn: Any = Depends(get_db)) -> dict:
    """Return all items currently in the cart."""
    return {"success": True, "data": _fetch_cart(conn)}


@router.post("", status_code=201)
async def add_to_cart(request: AddCartItemRequest, conn: Any = Depends(get_db)) -> dict:
    """Manually add an item to the cart."""
    existing = conn.execute(
        "SELECT set_number, source FROM cart_items WHERE set_number = ?",
        [request.set_number],
    ).fetchone()
    if existing:
        return {"success": True, "data": {"set_number": existing[0], "source": existing[1]}}

    conn.execute(
        "INSERT INTO cart_items (set_number, source) VALUES (?, ?)",
        [request.set_number, "manual"],
    )
    # Remove from watchlist when added to cart
    conn.execute(
        "UPDATE lego_items SET watchlist = FALSE, updated_at = now() WHERE set_number = ? AND watchlist = TRUE",
        [request.set_number],
    )
    return {"success": True, "data": {"set_number": request.set_number, "source": "manual"}}


@router.delete("/{set_number}")
async def remove_from_cart(
    set_number: str = Path(..., pattern=r"^\d{3,6}(-\d+)?$"),
    conn: Any = Depends(get_db),
) -> dict:
    """Remove an item from the cart and start a 30-day auto-add cooldown."""
    conn.execute("DELETE FROM cart_items WHERE set_number = ?", [set_number])
    _record_removal(conn, set_number)
    return {"success": True}


# ── Ban endpoints ──────────────────────────────────────────────


@router.get("/ban")
async def list_banned(conn: Any = Depends(get_db)) -> dict:
    """Return all banned set numbers."""
    rows = conn.execute(
        "SELECT set_number, banned_at FROM cart_banned ORDER BY banned_at DESC"
    ).fetchall()
    data = [{"set_number": r[0], "banned_at": str(r[1])} for r in rows]
    return {"success": True, "data": data}


@router.post("/ban/{set_number}", status_code=201)
async def ban_from_cart(
    set_number: str = Path(..., pattern=r"^\d{3,6}(-\d+)?$"),
    conn: Any = Depends(get_db),
) -> dict:
    """Ban an item from auto-cart and remove it if present as auto."""
    existing = conn.execute(
        "SELECT set_number FROM cart_banned WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO cart_banned (set_number) VALUES (?)",
            [set_number],
        )

    # Remove from cart if it was auto-added
    conn.execute(
        "DELETE FROM cart_items WHERE set_number = ? AND source = 'auto'",
        [set_number],
    )
    logger.info("Banned %s from auto-cart", set_number)
    return {"success": True, "data": _fetch_cart(conn)}


@router.delete("/ban/{set_number}")
async def unban_from_cart(
    set_number: str = Path(..., pattern=r"^\d{3,6}(-\d+)?$"),
    conn: Any = Depends(get_db),
) -> dict:
    """Remove an item from the ban list."""
    conn.execute("DELETE FROM cart_banned WHERE set_number = ?", [set_number])
    logger.info("Unbanned %s from auto-cart", set_number)
    return {"success": True}


# ── Sync endpoint ──────────────────────────────────────────────


@router.put("/sync")
async def sync_auto_cart(request: SyncCartRequest, conn: Any = Depends(get_db)) -> dict:
    """Bulk sync auto-cart items.

    Adds new qualifying items as 'auto', removes stale 'auto' items,
    preserves 'manual' items untouched, skips banned items.
    """
    banned = _fetch_banned(conn)
    on_cooldown = _fetch_on_cooldown(conn)
    desired = set(request.set_numbers) - banned - on_cooldown

    # Get current auto items
    rows = conn.execute(
        "SELECT set_number FROM cart_items WHERE source = 'auto'"
    ).fetchall()
    current_auto = {r[0] for r in rows}

    # Compute diffs
    to_add = desired - current_auto
    if to_add:
        manual_rows = conn.execute(
            "SELECT set_number FROM cart_items WHERE source = 'manual'"
        ).fetchall()
        to_add = to_add - {r[0] for r in manual_rows}

    to_remove = current_auto - desired

    # Batch insert new auto items
    for sn in to_add:
        conn.execute(
            "INSERT INTO cart_items (set_number, source) VALUES (?, 'auto')",
            [sn],
        )

    # Batch delete stale auto items
    if to_remove:
        placeholders = ", ".join(["?"] * len(to_remove))
        conn.execute(
            f"DELETE FROM cart_items WHERE set_number IN ({placeholders}) AND source = 'auto'",
            list(to_remove),
        )

    added = len(to_add)
    removed = len(to_remove)
    logger.info(
        "Cart sync: +%d auto, -%d stale, %d banned, %d on cooldown",
        added, removed, len(banned), len(on_cooldown),
    )

    return {
        "success": True,
        "data": _fetch_cart(conn),
        "added": added,
        "removed": removed,
    }
