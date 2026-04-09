"""Portfolio repository -- transactions, holdings, and P&L calculations."""

from __future__ import annotations

from datetime import datetime

from typing import Any

_SENTINEL = object()

# Conversion rate for non-MYR prices
MYR_PER_USD: float = 4.50


def create_transaction(
    conn: Any,
    set_number: str,
    txn_type: str,
    quantity: int,
    price_cents: int,
    condition: str,
    txn_date: datetime,
    *,
    currency: str = "MYR",
    notes: str | None = None,
    bill_id: str | None = None,
    supplier: str | None = None,
    platform: str | None = None,
) -> int:
    """Insert a BUY or SELL transaction. Returns the new transaction ID.

    Validates that SELL does not exceed current holdings.
    """
    if txn_type not in ("BUY", "SELL"):
        raise ValueError(f"Invalid txn_type: {txn_type}")
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    if price_cents <= 0:
        raise ValueError("Price must be positive")

    if txn_type == "SELL":
        held = _held_quantity(conn, set_number, condition)
        if quantity > held:
            raise ValueError(
                f"Cannot sell {quantity} units of {set_number} ({condition}) "
                f"-- only {held} held"
            )

    row = conn.execute(
        """
        INSERT INTO portfolio_transactions (
            id, set_number, txn_type, quantity, price_cents,
            currency, condition, txn_date, notes, bill_id, supplier, platform
        ) VALUES (
            nextval('portfolio_transactions_id_seq'),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        ) RETURNING id
        """,
        [set_number, txn_type, quantity, price_cents, currency, condition, txn_date, notes, bill_id, supplier, platform],
    ).fetchone()

    return row[0]


def list_transactions(
    conn: Any,
    *,
    set_number: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List transactions with optional set_number filter."""
    where = ""
    params: list = []
    if set_number:
        where = "WHERE pt.set_number = ?"
        params.append(set_number)

    params.extend([limit, offset])
    rows = conn.execute(
        f"""
        SELECT pt.id, pt.set_number, pt.txn_type, pt.quantity,
               pt.price_cents, pt.currency, pt.condition, pt.txn_date,
               pt.notes, pt.created_at, pt.bill_id, pt.supplier, pt.platform,
               li.title,
               CASE
                   WHEN ia.status = 'downloaded' THEN '/api/images/set/' || pt.set_number
                   ELSE COALESCE(li.image_url, 'https://img.bricklink.com/ItemImage/SN/0/' || pt.set_number || '-1.png')
               END AS image_url,
               li.theme
        FROM portfolio_transactions pt
        LEFT JOIN lego_items li ON li.set_number = pt.set_number
        LEFT JOIN image_assets ia ON ia.asset_type = 'set' AND ia.item_id = pt.set_number
        {where}
        ORDER BY pt.txn_date DESC, pt.id DESC
        LIMIT ? OFFSET ?
        """,  # noqa: S608
        params,
    ).fetchall()

    columns = [
        "id", "set_number", "txn_type", "quantity", "price_cents",
        "currency", "condition", "txn_date", "notes", "created_at", "bill_id",
        "supplier", "platform", "title", "image_url", "theme",
    ]
    return [dict(zip(columns, row)) for row in rows]


def get_transaction(conn: Any, txn_id: int) -> dict | None:
    """Get a single transaction by ID."""
    row = conn.execute(
        """
        SELECT pt.id, pt.set_number, pt.txn_type, pt.quantity,
               pt.price_cents, pt.currency, pt.condition, pt.txn_date,
               pt.notes, pt.created_at, pt.bill_id, pt.supplier, pt.platform,
               li.title,
               CASE
                   WHEN ia.status = 'downloaded' THEN '/api/images/set/' || pt.set_number
                   ELSE COALESCE(li.image_url, 'https://img.bricklink.com/ItemImage/SN/0/' || pt.set_number || '-1.png')
               END AS image_url,
               li.theme
        FROM portfolio_transactions pt
        LEFT JOIN lego_items li ON li.set_number = pt.set_number
        LEFT JOIN image_assets ia ON ia.asset_type = 'set' AND ia.item_id = pt.set_number
        WHERE pt.id = ?
        """,
        [txn_id],
    ).fetchone()
    if not row:
        return None

    columns = [
        "id", "set_number", "txn_type", "quantity", "price_cents",
        "currency", "condition", "txn_date", "notes", "created_at", "bill_id",
        "supplier", "platform", "title", "image_url", "theme",
    ]
    return dict(zip(columns, row))


def update_transaction(
    conn: Any,
    txn_id: int,
    *,
    txn_type: str | None = None,
    quantity: int | None = None,
    price_cents: int | None = None,
    condition: str | None = None,
    txn_date: datetime | None = None,
    notes: str | None = _SENTINEL,
    supplier: str | None = _SENTINEL,
    platform: str | None = _SENTINEL,
) -> bool:
    """Update a transaction. Returns True if a row was updated.

    Only provided fields are changed; None means keep current value.
    For notes, pass explicitly (even None) to clear; omit to keep.
    """
    existing = get_transaction(conn, txn_id)
    if not existing:
        return False

    new_type = txn_type or existing["txn_type"]
    new_qty = quantity or existing["quantity"]
    new_cond = condition or existing["condition"]

    if new_type == "SELL":
        held = _held_quantity(conn, existing["set_number"], new_cond)
        # Add back the existing quantity before checking
        if existing["txn_type"] == "SELL" and existing["condition"] == new_cond:
            held += existing["quantity"]
        if new_qty > held:
            raise ValueError(
                f"Cannot sell {new_qty} units of {existing['set_number']} ({new_cond}) "
                f"-- only {held} held"
            )

    fields: list[str] = []
    params: list[Any] = []
    if txn_type is not None:
        fields.append("txn_type = ?")
        params.append(txn_type)
    if quantity is not None:
        fields.append("quantity = ?")
        params.append(quantity)
    if price_cents is not None:
        fields.append("price_cents = ?")
        params.append(price_cents)
    if condition is not None:
        fields.append("condition = ?")
        params.append(condition)
    if txn_date is not None:
        fields.append("txn_date = ?")
        params.append(txn_date)
    if notes is not _SENTINEL:
        fields.append("notes = ?")
        params.append(notes)
    if supplier is not _SENTINEL:
        fields.append("supplier = ?")
        params.append(supplier)
    if platform is not _SENTINEL:
        fields.append("platform = ?")
        params.append(platform)

    if not fields:
        return True

    params.append(txn_id)
    conn.execute(
        f"UPDATE portfolio_transactions SET {', '.join(fields)} WHERE id = ?",  # noqa: S608
        params,
    )
    return True


def delete_transaction(conn: Any, txn_id: int) -> bool:
    """Delete a transaction. Returns True if a row was deleted."""
    row = conn.execute(
        "DELETE FROM portfolio_transactions WHERE id = ? RETURNING id", [txn_id]
    ).fetchone()

    return row is not None


def delete_transactions_by_bill(conn: Any, bill_id: str) -> int:
    """Delete all transactions with the given bill_id. Returns count deleted."""
    rows = conn.execute(
        "DELETE FROM portfolio_transactions WHERE bill_id = ? RETURNING id",
        [bill_id],
    ).fetchall()
    return len(rows)


def get_holdings(conn: Any) -> list[dict]:
    """Compute current holdings from transactions, with market values.

    Holdings are derived by aggregating BUY - SELL quantities.
    Cost basis for remaining units uses FIFO.
    Market value uses bricklink_new qty avg from price_records.
    """
    txn_rows = conn.execute(
        """
        SELECT set_number, condition, txn_type, quantity, price_cents, txn_date
        FROM portfolio_transactions
        ORDER BY set_number, condition, txn_date ASC, id ASC
        """
    ).fetchall()

    # Group transactions by (set_number, condition)
    groups: dict[tuple[str, str], list[tuple]] = {}
    for row in txn_rows:
        key = (row[0], row[1])
        groups.setdefault(key, []).append(row)

    holdings = []
    for (set_number, condition), txns in groups.items():
        cost_basis, held_qty = _fifo_cost_basis(txns)
        if held_qty <= 0:
            continue
        holdings.append({
            "set_number": set_number,
            "condition": condition,
            "quantity": held_qty,
            "total_cost_cents": cost_basis,
            "avg_cost_cents": cost_basis // held_qty if held_qty > 0 else 0,
        })

    if not holdings:
        return []

    # Fetch latest market prices for held sets
    set_numbers = list({h["set_number"] for h in holdings})
    prices = _latest_prices(conn, set_numbers)

    # Fetch item metadata
    meta = _item_metadata(conn, set_numbers)

    # Fetch active marketplace listings
    from services.listing.repository import get_active_listings_bulk
    active_listings = get_active_listings_bulk(conn, set_numbers)

    for h in holdings:
        sn = h["set_number"]
        market_price = prices.get(sn, 0)
        h["current_value_cents"] = market_price * h["quantity"]
        h["unrealized_pl_cents"] = h["current_value_cents"] - h["total_cost_cents"]
        h["unrealized_pl_pct"] = (
            round(h["unrealized_pl_cents"] / h["total_cost_cents"] * 100, 2)
            if h["total_cost_cents"] > 0
            else 0.0
        )
        item = meta.get(sn, {})
        h["title"] = item.get("title")
        h["image_url"] = item.get("image_url")
        h["theme"] = item.get("theme")
        h["market_price_cents"] = market_price
        h["listing_price_cents"] = item.get("listing_price_cents")
        h["listing_currency"] = item.get("listing_currency")
        h["listed_on"] = active_listings.get(sn, [])

    return sorted(holdings, key=lambda h: abs(h["unrealized_pl_cents"]), reverse=True)


def get_holding_detail(
    conn: Any, set_number: str
) -> dict | None:
    """Get holding detail for a single set with all its transactions."""
    txns = list_transactions(conn, set_number=set_number, limit=1000)
    if not txns:
        return None

    raw = conn.execute(
        """
        SELECT set_number, condition, txn_type, quantity, price_cents, txn_date
        FROM portfolio_transactions
        WHERE set_number = ?
        ORDER BY condition, txn_date ASC, id ASC
        """,
        [set_number],
    ).fetchall()

    # Aggregate by condition
    groups: dict[str, list[tuple]] = {}
    for row in raw:
        groups.setdefault(row[1], []).append(row)

    prices = _latest_prices(conn, [set_number])
    meta = _item_metadata(conn, [set_number])
    market_price = prices.get(set_number, 0)
    item = meta.get(set_number, {})

    conditions = []
    for cond, cond_txns in groups.items():
        cost_basis, held_qty = _fifo_cost_basis(cond_txns)
        realized = _fifo_realized_pl(cond_txns)
        if held_qty > 0 or realized != 0:
            conditions.append({
                "condition": cond,
                "quantity": held_qty,
                "total_cost_cents": cost_basis,
                "avg_cost_cents": cost_basis // held_qty if held_qty > 0 else 0,
                "current_value_cents": market_price * held_qty,
                "unrealized_pl_cents": (market_price * held_qty) - cost_basis,
                "realized_pl_cents": realized,
            })

    return {
        "set_number": set_number,
        "title": item.get("title"),
        "image_url": item.get("image_url"),
        "theme": item.get("theme"),
        "market_price_cents": market_price,
        "conditions": conditions,
        "transactions": txns,
    }


def get_portfolio_summary(conn: Any) -> dict:
    """Compute portfolio-wide totals."""
    holdings = get_holdings(conn)

    total_cost = sum(h["total_cost_cents"] for h in holdings)
    total_market = sum(h["current_value_cents"] for h in holdings)
    unrealized = total_market - total_cost

    # Compute realized P&L across all sets
    realized = _total_realized_pl(conn)

    unique_sets = len({h["set_number"] for h in holdings})

    return {
        "total_cost_cents": total_cost,
        "total_market_value_cents": total_market,
        "unrealized_pl_cents": unrealized,
        "unrealized_pl_pct": (
            round(unrealized / total_cost * 100, 2) if total_cost > 0 else 0.0
        ),
        "realized_pl_cents": realized,
        "holdings_count": sum(h["quantity"] for h in holdings),
        "unique_sets": unique_sets,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _held_quantity(
    conn: Any, set_number: str, condition: str
) -> int:
    """Current held quantity for a (set_number, condition) pair."""
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN txn_type = 'BUY' THEN quantity ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN txn_type = 'SELL' THEN quantity ELSE 0 END), 0)
        FROM portfolio_transactions
        WHERE set_number = ? AND condition = ?
        """,
        [set_number, condition],
    ).fetchone()
    return row[0] if row else 0


def _fifo_cost_basis(txns: list[tuple]) -> tuple[int, int]:
    """Compute FIFO cost basis for remaining holdings.

    Each tuple: (set_number, condition, txn_type, quantity, price_cents, txn_date).

    Returns (remaining_cost_cents, remaining_quantity).
    """
    # Build a list of buy lots: [(qty_remaining, price_cents), ...]
    lots: list[list[int]] = []
    for row in txns:
        txn_type, qty, price = row[2], row[3], row[4]
        if txn_type == "BUY":
            lots.append([qty, price])
        elif txn_type == "SELL":
            remaining = qty
            for lot in lots:
                if remaining <= 0:
                    break
                consumed = min(lot[0], remaining)
                lot[0] -= consumed
                remaining -= consumed

    total_cost = sum(lot[0] * lot[1] for lot in lots)
    total_qty = sum(lot[0] for lot in lots)
    return total_cost, total_qty


def _fifo_realized_pl(txns: list[tuple]) -> int:
    """Compute realized P&L using FIFO lot matching.

    Each tuple: (set_number, condition, txn_type, quantity, price_cents, txn_date).
    """
    lots: list[list[int]] = []
    realized = 0

    for row in txns:
        txn_type, qty, price = row[2], row[3], row[4]
        if txn_type == "BUY":
            lots.append([qty, price])
        elif txn_type == "SELL":
            remaining = qty
            for lot in lots:
                if remaining <= 0:
                    break
                consumed = min(lot[0], remaining)
                realized += consumed * (price - lot[1])
                lot[0] -= consumed
                remaining -= consumed

    return realized


def _total_realized_pl(conn: Any) -> int:
    """Compute total realized P&L across all positions."""
    txn_rows = conn.execute(
        """
        SELECT set_number, condition, txn_type, quantity, price_cents, txn_date
        FROM portfolio_transactions
        ORDER BY set_number, condition, txn_date ASC, id ASC
        """
    ).fetchall()

    groups: dict[tuple[str, str], list[tuple]] = {}
    for row in txn_rows:
        key = (row[0], row[1])
        groups.setdefault(key, []).append(row)

    return sum(_fifo_realized_pl(txns) for txns in groups.values())


def _latest_prices(
    conn: Any, set_numbers: list[str]
) -> dict[str, int]:
    """Get latest market price per set in MYR cents.

    Uses bricklink_new (qty avg) as the canonical market value (USD -> MYR).
    """
    if not set_numbers:
        return {}

    placeholders = ", ".join(["?"] * len(set_numbers))

    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT set_number, price_cents, currency,
                   ROW_NUMBER() OVER (
                       PARTITION BY set_number
                       ORDER BY recorded_at DESC
                   ) AS rn
            FROM price_records
            WHERE set_number IN ({placeholders})
              AND source = 'bricklink_new'
        )
        SELECT set_number, price_cents, currency FROM ranked WHERE rn = 1
        """,  # noqa: S608
        set_numbers,
    ).fetchall()

    result: dict[str, int] = {}
    for set_number, price_cents, currency in rows:
        if currency == "MYR":
            result[set_number] = price_cents
        else:
            # Convert USD cents to MYR cents
            result[set_number] = round(price_cents * MYR_PER_USD)
    return result


def _item_metadata(
    conn: Any, set_numbers: list[str]
) -> dict[str, dict]:
    """Get title, image_url, theme for a list of set numbers."""
    if not set_numbers:
        return {}

    placeholders = ", ".join(["?"] * len(set_numbers))
    rows = conn.execute(
        f"""
        SELECT li.set_number, li.title,
               CASE
                   WHEN ia.status = 'downloaded' THEN '/api/images/set/' || li.set_number
                   ELSE COALESCE(li.image_url, 'https://img.bricklink.com/ItemImage/SN/0/' || li.set_number || '-1.png')
               END AS image_url,
               li.theme,
               li.listing_price_cents,
               li.listing_currency
        FROM lego_items li
        LEFT JOIN image_assets ia ON ia.asset_type = 'set' AND ia.item_id = li.set_number
        WHERE li.set_number IN ({placeholders})
        """,  # noqa: S608
        set_numbers,
    ).fetchall()
    return {
        row[0]: {
            "title": row[1],
            "image_url": row[2],
            "theme": row[3],
            "listing_price_cents": row[4],
            "listing_currency": row[5],
        }
        for row in rows
    }
