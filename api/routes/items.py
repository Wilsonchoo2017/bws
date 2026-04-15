"""Items API routes."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_db
from api.serialization import sanitize_nan
from services.bricklink.repository import (
    get_monthly_sales,
    get_price_history,
    get_set_minifigures,
    get_set_minifig_value_history,
    get_store_listing_country_stats,
)
from services.bricklink.scraper import scrape_set_minifigures
from services.backtesting.position_sizing import (
    compute_position_sizing,
    kelly_to_dict,
)
from services.portfolio.capital_allocation import (
    compute_capital_allocation,
    allocation_to_dict,
)
from services.backtesting.keepa_screener import compute_keepa_signals_with_cohort
from services.backtesting.screener import (
    compute_all_signals_with_cohort,
)
from services.items.repository import get_all_items, get_all_items_lite, get_item_detail, get_or_create_item, item_exists, toggle_watchlist, update_buy_rating, update_listing_price
from services.shopee.repository import get_all_products
from services.shopee.saturation_repository import (
    get_all_latest_saturations,
    get_latest_saturation,
)


router = APIRouter(prefix="/items", tags=["items"])


class AddItemRequest(BaseModel):
    set_number: str = Field(
        ..., min_length=1, max_length=20, pattern=r"^\d{3,6}(-\d+)?$"
    )


class UpdateBuyRatingRequest(BaseModel):
    rating: int | None = Field(None, ge=1, le=4)


class UpdateListingPriceRequest(BaseModel):
    price_cents: int | None = Field(None, ge=0)
    currency: str = Field(default="MYR", max_length=3)


@router.post("", status_code=201)
async def add_item(request: AddItemRequest, conn: Any = Depends(get_db)):
    """Add a new LEGO set to the catalog by set number."""
    if item_exists(conn, request.set_number):
        raise HTTPException(
            status_code=409,
            detail=f"Item {request.set_number} already exists",
        )
    get_or_create_item(conn, request.set_number)
    item = get_item_detail(conn, request.set_number)
    return {"success": True, "data": item, "message": f"Item {request.set_number} created"}


@router.patch("/{set_number}/watchlist")
async def toggle_item_watchlist(set_number: str, conn: Any = Depends(get_db)):
    """Toggle watchlist status for an item."""
    new_value = toggle_watchlist(conn, set_number)
    if new_value is None:
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
    return {"success": True, "data": {"set_number": set_number, "watchlist": new_value}}


@router.put("/{set_number}/buy-rating")
async def set_buy_rating(set_number: str, request: UpdateBuyRatingRequest, conn: Any = Depends(get_db)):
    """Set or clear the buy rating for an item."""
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


@router.put("/{set_number}/listing-price")
async def set_listing_price(
    set_number: str,
    request: UpdateListingPriceRequest,
    conn: Any = Depends(get_db),
):
    """Set or clear the listing price for an item."""
    success = update_listing_price(
        conn, set_number, request.price_cents, request.currency,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
    return {
        "success": True,
        "data": {
            "set_number": set_number,
            "listing_price_cents": request.price_cents,
            "listing_currency": request.currency,
        },
    }


@router.get("/lite")
async def list_items_lite(conn: Any = Depends(get_db)):
    """List all LEGO items with catalog data only (no prices). Fast path for initial load."""
    items = get_all_items_lite(conn)
    return {"success": True, "data": items, "count": len(items)}


@router.get("")
async def list_items(conn: Any = Depends(get_db)):
    """List all LEGO items with latest prices from each source."""
    items = get_all_items(conn)
    return {"success": True, "data": items, "count": len(items)}


_signals_cache: dict = {}  # {"data": ..., "expires": float}
_SIGNALS_TTL = 30 * 24 * 3600  # 30 days


@router.get("/signals")
async def list_signals(
    condition: str = "new",
    refresh: bool = False,
    conn: Any = Depends(get_db),
):
    """Trading signals enriched by ML predictions. Cached for 5 minutes."""
    import time
    from services.scoring.provider import enrich_signals

    cache_key = condition
    now = time.time()

    if not refresh and cache_key in _signals_cache and _signals_cache[cache_key]["expires"] > now:
        cached = _signals_cache[cache_key]["data"]
        return {"success": True, "data": cached, "count": len(cached), "cached": True}

    signals = compute_all_signals_with_cohort(conn, condition=condition)
    signals = enrich_signals(signals, conn)
    result = sanitize_nan(signals)

    _signals_cache[cache_key] = {"data": result, "expires": now + _SIGNALS_TTL}
    return {"success": True, "data": result, "count": len(result)}


@router.get("/signals/be")
async def list_signals_be(
    refresh: bool = False,
    conn: Any = Depends(get_db),
):
    """Bulk Keepa-based signals with cohort ranks. Cached for 30 days."""
    import time

    cache_key = "be"
    now = time.time()

    if not refresh and cache_key in _be_signals_cache and _be_signals_cache[cache_key]["expires"] > now:
        cached = _be_signals_cache[cache_key]["data"]
        return {"success": True, "data": cached, "count": len(cached), "cached": True}

    signals = compute_keepa_signals_with_cohort(conn)
    result = sanitize_nan(signals)
    _be_signals_cache[cache_key] = {"data": result, "expires": now + _SIGNALS_TTL}
    return {"success": True, "data": result, "count": len(result)}


@router.get("/shopee")
async def list_shopee_products(conn: Any = Depends(get_db)):
    """List all raw Shopee products from the database."""
    products = get_all_products(conn)
    return {"success": True, "data": products, "count": len(products)}


@router.get("/saturation")
async def list_saturations(conn: Any = Depends(get_db)):
    """List latest Shopee saturation data for all items."""
    data = get_all_latest_saturations(conn)
    return {"success": True, "data": data, "count": len(data)}


@router.get("/{set_number}/saturation")
async def get_item_saturation(set_number: str, conn: Any = Depends(get_db)):
    """Get Shopee market saturation data for a LEGO set."""
    data = get_latest_saturation(conn, set_number)
    return {"success": True, "data": data}


@router.get("/{set_number}/competition")
async def get_item_competition(set_number: str, conn: Any = Depends(get_db)):
    """Get Shopee competition data with history and current listings."""
    from services.shopee.competition_repository import (
        get_competition_history,
        get_latest_competition_listings,
        get_listing_sold_deltas,
    )

    history = get_competition_history(conn, set_number)
    listings = get_latest_competition_listings(conn, set_number)
    deltas = get_listing_sold_deltas(conn, set_number)

    # Attach sold delta to each listing
    for listing in listings:
        listing["sold_delta"] = deltas.get(listing["product_url"])

    return {
        "success": True,
        "data": {
            "history": history,
            "listings": listings,
        },
    }


@router.get("/{set_number}/my-liquidity")
async def get_item_my_liquidity(set_number: str, conn: Any = Depends(get_db)):
    """Return the Malaysian exit-liquidity composite for a set.

    Composites Shopee competition snapshots, BL/BE USD benchmarks,
    and the current MYR FX rate into a single payload covering
    premium distribution, 30d + 7d velocity, and data sufficiency.
    """
    if not item_exists(conn, set_number):
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
    data = await asyncio.to_thread(_fetch_my_liquidity, set_number)
    return {"success": True, "data": data}


_my_cohort_cache: dict = {}
_MY_COHORT_TTL = 30 * 60  # 30 minutes


def _build_my_cohort_cache() -> dict[str, dict]:
    """Compute + cache MY cohort ranks for the full universe."""
    import time as _time

    from db.connection import get_connection
    from services.my_liquidity import compute_my_cohort_ranks

    now = _time.time()
    cached = _my_cohort_cache.get("all")
    if cached and cached["expires"] > now:
        return cached["results"]

    conn = get_connection()
    try:
        results = compute_my_cohort_ranks(conn)
    finally:
        conn.close()

    _my_cohort_cache["all"] = {
        "results": results,
        "expires": now + _MY_COHORT_TTL,
    }
    return results


def _fetch_my_cohorts(set_number: str) -> dict | None:
    """Return the MY cohort entry for a single set, or None."""
    results = _build_my_cohort_cache()
    return results.get(set_number)


@router.get("/{set_number}/my-liquidity/cohorts")
async def get_item_my_liquidity_cohorts(
    set_number: str,
    conn: Any = Depends(get_db),
):
    """MY-exit percentile rankings within cohort peer groups.

    Signals: my_sold_velocity_30d, my_premium_median_pct,
    my_saturation_inverse, my_churn_ratio, my_liquidity_ratio.
    """
    if not item_exists(conn, set_number):
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
    data = await asyncio.to_thread(_fetch_my_cohorts, set_number)
    if data is None:
        return {"success": True, "data": None}
    return {"success": True, "data": sanitize_nan(data)}


@router.get("/{set_number}/kelly")
async def get_item_kelly(
    set_number: str,
    conn: Any = Depends(get_db),
):
    """Capital allocation using simplified Kelly Criterion (assumption-based)."""
    from services.scoring.growth_provider import growth_provider

    # Look up ML buy category
    scores = growth_provider.score_all(conn)
    pred = scores.get(set_number)
    ml_buy_category = pred.get("buy_category") if pred else None

    # Look up RRP
    row = conn.execute(
        "SELECT rrp_cents, rrp_currency FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    rrp_cents = row[0] if row else None
    rrp_currency = row[1] if row and row[1] else "MYR"

    # If no RRP from lego_items, try brickeconomy
    if rrp_cents is None:
        from services.portfolio.repository import MYR_PER_USD

        be_row = conn.execute(
            """
            SELECT rrp_usd_cents FROM brickeconomy_snapshots
            WHERE set_number = ?
            ORDER BY scraped_at DESC LIMIT 1
            """,
            [set_number],
        ).fetchone()
        if be_row and be_row[0]:
            rrp_cents = round(be_row[0] * MYR_PER_USD)
            rrp_currency = "MYR"

    alloc = compute_capital_allocation(
        conn, set_number, ml_buy_category, rrp_cents, rrp_currency
    )
    return {"success": True, "data": allocation_to_dict(alloc)}


@router.get("/{set_number}/signals")
async def get_item_signals(set_number: str, condition: str = "new", conn: Any = Depends(get_db)):
    """Trading signals for a single item. Uses cached signals list, computes on first call."""
    import time
    from services.scoring.provider import enrich_signals

    cache_key = condition
    now = time.time()

    if cache_key not in _signals_cache or _signals_cache[cache_key]["expires"] <= now:
        signals = compute_all_signals_with_cohort(conn, condition=condition)
        signals = enrich_signals(signals, conn)
        result = sanitize_nan(signals)
        _signals_cache[cache_key] = {"data": result, "expires": now + _SIGNALS_TTL}

    cached = _signals_cache[cache_key]["data"]
    match = next(
        (s for s in cached if s.get("set_number") == set_number),
        None,
    )
    if not match:
        return {"success": True, "data": None}
    return {"success": True, "data": match}


_be_signals_cache: dict = {}


@router.get("/{set_number}/signals/be")
async def get_item_signals_be(set_number: str, conn: Any = Depends(get_db)):
    """Keepa-based signals and cohort ranks for a single item."""
    import time

    now = time.time()
    cache_key = "be"

    if cache_key not in _be_signals_cache or _be_signals_cache[cache_key]["expires"] <= now:
        signals = compute_keepa_signals_with_cohort(conn)
        result = sanitize_nan(signals)
        _be_signals_cache[cache_key] = {"data": result, "expires": now + _SIGNALS_TTL}

    cached = _be_signals_cache[cache_key]["data"]
    match = next(
        (s for s in cached if s.get("set_number") == set_number),
        None,
    )
    if not match:
        return {"success": True, "data": None}
    return {"success": True, "data": match}


_liquidity_cache: dict = {}
_LIQUIDITY_TTL = 30 * 24 * 3600


@router.get("/liquidity/bulk")
async def get_liquidity_bulk(
    source: str = "bricklink",
    condition: str = "new",
    refresh: bool = False,
    conn: Any = Depends(get_db),
) -> dict:
    """Return composite liquidity percentile for every item. Reuses same cache."""
    import time

    cache_key = f"{source}:{condition}"
    now = time.time()

    if refresh or cache_key not in _liquidity_cache or _liquidity_cache[cache_key]["expires"] <= now:
        await get_item_liquidity("__warmup__", source, condition, refresh, conn)

    cached = _liquidity_cache.get(cache_key)
    if not cached:
        return {"success": True, "data": {}}

    ranked = cached["ranked"]
    result = {sn: r["composite_pct"] for sn, r in ranked.items()}
    return {"success": True, "data": result}


@router.get("/liquidity/cohorts/bulk")
async def get_liquidity_cohorts_bulk(
    source: str = "bricklink",
    condition: str = "new",
    conn: Any = Depends(get_db),
) -> dict:
    """Return per-cohort liquidity percentiles for every item."""
    cached = await _ensure_liq_cohort_cache(source, condition, conn)
    if not cached:
        return {"success": True, "data": {}}

    result: dict[str, dict[str, float | None]] = {}
    for sn, strategies in cached["results"].items():
        if not strategies:
            continue
        entry: dict[str, float | None] = {}
        for strategy, vals in strategies.items():
            entry[strategy] = vals.get("composite_pct")
        result[sn] = entry
    return {"success": True, "data": sanitize_nan(result)}


@router.get("/{set_number}")
async def get_item(set_number: str, conn: Any = Depends(get_db)):
    """Get a single item with full price history from all sources."""
    item = get_item_detail(conn, set_number)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
    item["saturation"] = get_latest_saturation(conn, set_number)

    # Check if item is in portfolio (has positive holdings)
    held = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN txn_type = 'BUY' THEN quantity ELSE -quantity END), 0)
        FROM portfolio_transactions
        WHERE set_number = ?
        """,
        [set_number],
    ).fetchone()
    item["in_portfolio"] = (held[0] or 0) > 0

    # Marketplace listings
    from services.listing.repository import get_listings_for_set
    item["marketplace_listings"] = get_listings_for_set(conn, set_number)
    item["listed_on"] = [
        ml["platform"]
        for ml in item["marketplace_listings"]
        if ml["status"] == "active"
    ]

    # ML growth prediction
    from services.scoring.provider import enrich_signals

    ml_section = enrich_signals([{"set_number": set_number}], conn)[0]
    ml_section.pop("set_number", None)
    if ml_section:
        # Strip ml_ prefix for cleaner nesting under ml_prediction
        stripped = {k.removeprefix("ml_"): v for k, v in ml_section.items()}
        item["ml_prediction"] = sanitize_nan(stripped)

    return {"success": True, "data": item}


def _item_volume_stats(txn_counts: list[int], qty_counts: list[int] | None = None) -> dict:
    """Compute volume metrics for a single item from monthly counts."""
    total_months = len(txn_counts)
    if total_months == 0:
        return {}
    months_with_sales = sum(1 for c in txn_counts if c > 0)
    total_txns = sum(txn_counts)
    consistency = months_with_sales / total_months
    avg_monthly_txns = total_txns / total_months

    recent = txn_counts[-6:] if len(txn_counts) >= 6 else txn_counts
    older = txn_counts[:-6] if len(txn_counts) > 6 else []
    recent_avg = sum(recent) / len(recent) if recent else 0
    older_avg = sum(older) / len(older) if older else 0
    trend_ratio = (recent_avg / older_avg) if older_avg > 0 else None

    total_qty = sum(qty_counts) if qty_counts else None
    avg_monthly_qty = round(total_qty / total_months, 1) if total_qty is not None else None

    recent_avg_qty: float | None = None
    if qty_counts:
        recent_q = qty_counts[-6:] if len(qty_counts) >= 6 else qty_counts
        recent_avg_qty = round(sum(recent_q) / len(recent_q), 1) if recent_q else None

    return {
        "total_months": total_months,
        "months_with_sales": months_with_sales,
        "consistency": round(consistency, 3),
        "total_txns": total_txns,
        "total_qty": total_qty,
        "avg_monthly_txns": round(avg_monthly_txns, 1),
        "avg_monthly_qty": avg_monthly_qty,
        "recent_avg_txns": round(recent_avg, 1),
        "recent_avg_qty": recent_avg_qty,
        "trend_ratio": round(trend_ratio, 2) if trend_ratio is not None else None,
    }


def _percentile(all_values: list[float], target: float) -> float:
    """Percentile rank of target within all_values (0-100)."""
    n = len(all_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in all_values if v < target)
    equal = sum(1 for v in all_values if v == target)
    return round((below + 0.5 * equal) / n * 100.0, 1)



@router.get("/{set_number}/liquidity")
async def get_item_liquidity(
    set_number: str,
    source: str = "bricklink",
    condition: str = "new",
    refresh: bool = False,
    conn: Any = Depends(get_db),
):
    """Liquidity percentile rankings based on sales volume."""
    import json as json_mod
    import time

    cache_key = f"{source}:{condition}"
    now = time.time()

    # Build or use cached per-item stats for all items
    if refresh or cache_key not in _liquidity_cache or _liquidity_cache[cache_key]["expires"] <= now:
        all_stats: dict[str, dict] = {}

        if source == "brickeconomy":
            rows = conn.execute(
                """
                SELECT DISTINCT ON (set_number) set_number, sales_trend_json
                FROM brickeconomy_snapshots
                WHERE sales_trend_json IS NOT NULL
                ORDER BY set_number, scraped_at DESC
                """,
            ).fetchall()
            for r in rows:
                sn = r[0]
                raw = json_mod.loads(r[1]) if isinstance(r[1], str) else r[1]
                if not raw:
                    continue
                txns = [int(entry[1]) for entry in raw]
                if txns:
                    monthly = [{"label": entry[0], "txns": int(entry[1])} for entry in raw]
                    stats = _item_volume_stats(txns)
                    if stats:
                        stats["monthly"] = monthly
                        all_stats[sn] = stats
        else:
            rows = conn.execute(
                """
                SELECT item_id, year, month, times_sold, total_quantity
                FROM bricklink_monthly_sales
                WHERE condition = ?
                ORDER BY item_id, year, month
                """,
                [condition],
            ).fetchall()

            # Load latest listing snapshot per item for listing ratio
            listing_map: dict[str, tuple[int, int]] = {}  # item_id -> (lots, qty)
            try:
                snap_rows = conn.execute(
                    """
                    SELECT DISTINCT ON (item_id) item_id, current_new
                    FROM bricklink_price_history
                    WHERE current_new IS NOT NULL
                    ORDER BY item_id, scraped_at DESC
                    """,
                ).fetchall()
                for sr in snap_rows:
                    raw_box = sr[1]
                    if isinstance(raw_box, str):
                        raw_box = json_mod.loads(raw_box)
                    if isinstance(raw_box, dict):
                        lots = raw_box.get("total_lots")
                        qty = raw_box.get("total_qty")
                        if lots is not None or qty is not None:
                            listing_map[sr[0]] = (int(lots or 0), int(qty or 0))
            except Exception:
                logger.debug("Could not load listing snapshots", exc_info=True)

            from itertools import groupby
            for item_id, group in groupby(rows, key=lambda r: r[0]):
                records = list(group)
                sn = item_id.split("-")[0]
                txns = [r[3] or 0 for r in records]
                qtys = [r[4] or 0 for r in records]
                monthly = [{"label": f"{r[1]}-{r[2]:02d}", "txns": r[3] or 0} for r in records]
                stats = _item_volume_stats(txns, qtys)
                if stats:
                    stats["monthly"] = monthly
                    # Listing ratio: current listings / avg monthly sold (last 6mo)
                    listing = listing_map.get(item_id)
                    if listing and stats.get("recent_avg_qty") and stats["recent_avg_qty"] > 0:
                        stats["listing_lots"] = listing[0]
                        stats["listing_qty"] = listing[1]
                        stats["listing_ratio"] = round(listing[1] / stats["recent_avg_qty"], 2)
                    all_stats[sn] = stats

        # Precompute percentiles and ranks for all items
        vol_vals = [v["avg_monthly_txns"] for v in all_stats.values()]
        con_vals = [v["consistency"] for v in all_stats.values()]
        trend_vals = [v["trend_ratio"] for v in all_stats.values() if v.get("trend_ratio") is not None]
        qty_vals = [v["avg_monthly_qty"] for v in all_stats.values() if v.get("avg_monthly_qty") is not None]
        # Listing ratio: lower = tighter supply = better, so invert for percentile
        lr_vals = [v["listing_ratio"] for v in all_stats.values() if v.get("listing_ratio") is not None]

        ranked: dict[str, dict] = {}
        composites: list[tuple[str, float]] = []
        for k, v in all_stats.items():
            v_pct = _percentile(vol_vals, v["avg_monthly_txns"])
            c_pct = _percentile(con_vals, v["consistency"])
            t_pct = _percentile(trend_vals, v["trend_ratio"]) if v.get("trend_ratio") is not None and trend_vals else None
            q_pct = _percentile(qty_vals, v["avg_monthly_qty"]) if v.get("avg_monthly_qty") is not None and qty_vals else None
            # Invert listing ratio: lower ratio = higher percentile (better)
            lr_pct = None
            if v.get("listing_ratio") is not None and lr_vals:
                lr_pct = round(100.0 - _percentile(lr_vals, v["listing_ratio"]), 1)

            # Optimized weights: volume 50%, consistency 38%, listing_ratio 12%
            if lr_pct is not None:
                comp = round(v_pct * 0.50 + c_pct * 0.38 + lr_pct * 0.12, 1)
            else:
                comp = round(v_pct * 0.57 + c_pct * 0.43, 1)
            composites.append((k, comp))

            ranked[k] = {
                "volume_pct": v_pct,
                "consistency_pct": c_pct,
                "trend_pct": t_pct,
                "qty_pct": q_pct,
                "listing_ratio_pct": lr_pct,
                "composite_pct": comp,
            }

        # Ordinal ranks by composite (1 = best)
        sorted_comp = sorted(composites, key=lambda x: x[1], reverse=True)
        total_size = len(sorted_comp)
        for pos, (k, _) in enumerate(sorted_comp, 1):
            ranked[k]["rank"] = pos
            ranked[k]["size"] = total_size

        _liquidity_cache[cache_key] = {
            "stats": all_stats,
            "ranked": ranked,
            "expires": now + _LIQUIDITY_TTL,
        }

    cached = _liquidity_cache[cache_key]
    all_stats = cached["stats"]
    all_ranked = cached["ranked"]

    if set_number not in all_stats:
        return {"success": True, "data": None}

    target = all_stats[set_number]
    r = all_ranked[set_number]

    metrics: dict = {
        "volume": {"value": target["avg_monthly_txns"], "pct": r["volume_pct"], "label": "Avg txns/mo"},
        "consistency": {"value": target["consistency"], "pct": r["consistency_pct"], "label": "Consistency"},
    }
    if r.get("qty_pct") is not None:
        metrics["quantity"] = {"value": target["avg_monthly_qty"], "pct": r["qty_pct"], "label": "Avg qty/mo"}
    if r.get("trend_pct") is not None:
        metrics["trend"] = {"value": target["trend_ratio"], "pct": r["trend_pct"], "label": "Recent trend"}
    if r.get("listing_ratio_pct") is not None:
        metrics["listing_ratio"] = {
            "value": target["listing_ratio"],
            "pct": r["listing_ratio_pct"],
            "label": "Listing ratio",
            "detail": f"{target.get('listing_qty', 0)} units vs {target['recent_avg_qty']}/mo sold",
        }

    data = {
        "set_number": set_number,
        "source": source,
        **target,
        "metrics": metrics,
        "composite_pct": r["composite_pct"],
        "rank": r["rank"],
        "size": r["size"],
    }
    return {"success": True, "data": sanitize_nan(data)}


_liq_cohort_cache: dict = {}
_LIQ_COHORT_TTL = 30 * 24 * 3600


async def _ensure_liq_cohort_cache(
    source: str, condition: str, conn: Any
) -> dict | None:
    """Build (or reuse) the liquidity-cohort cache and return it."""
    import time

    from services.backtesting.cohort import STRATEGY_NAMES, _assign_bucket, _compute_percentile

    cache_key = f"{source}:{condition}"
    now = time.time()

    # Ensure liquidity cache is warm
    if cache_key not in _liquidity_cache or _liquidity_cache[cache_key]["expires"] <= now:
        await get_item_liquidity("__warmup__", source, condition, False, conn)

    cached = _liquidity_cache.get(cache_key)
    if not cached:
        return None

    all_stats = cached["stats"]
    all_ranked = cached["ranked"]

    if (
        cache_key not in _liq_cohort_cache
        or _liq_cohort_cache[cache_key]["expires"] <= now
    ):
        be_rows = conn.execute(
            """
            SELECT set_number, year_released, theme, pieces, rrp_usd_cents
            FROM (
                SELECT set_number, year_released, theme, pieces, rrp_usd_cents,
                       ROW_NUMBER() OVER (
                           PARTITION BY set_number ORDER BY scraped_at DESC
                       ) AS rn
                FROM brickeconomy_snapshots
            ) sub WHERE rn = 1
            """
        ).fetchall()
        meta_map: dict[str, dict] = {}
        for r in be_rows:
            meta_map[r[0]] = {
                "set_number": r[0],
                "year_released": r[1],
                "theme": r[2],
                "parts_count": r[3],
                "rrp_usd_cents": r[4],
            }
        bl_rows = conn.execute(
            "SELECT set_number, year_released, theme, parts_count FROM bricklink_items"
        ).fetchall()
        for r in bl_rows:
            sn = r[0]
            if sn not in meta_map:
                meta_map[sn] = {
                    "set_number": sn,
                    "year_released": r[1],
                    "theme": r[2],
                    "parts_count": r[3],
                    "rrp_usd_cents": None,
                }
            elif not meta_map[sn].get("year_released") and r[1]:
                meta_map[sn]["year_released"] = r[1]

        from collections import defaultdict

        buckets: dict[str, dict[str, list[str]]] = {
            s: defaultdict(list) for s in STRATEGY_NAMES
        }
        for sn in all_stats:
            meta = meta_map.get(sn, {})
            for strategy in STRATEGY_NAMES:
                key = _assign_bucket(meta, strategy)
                if key is not None:
                    buckets[strategy][key].append(sn)

        liq_metrics = ("avg_monthly_txns", "consistency", "trend_ratio", "listing_ratio")
        cohort_results: dict[str, dict[str, dict]] = {sn: {} for sn in all_stats}

        for strategy in STRATEGY_NAMES:
            for bucket_key, members in buckets[strategy].items():
                valid = [sn for sn in members if sn in all_ranked]
                if len(valid) < 3:
                    continue

                cohort_size = len(valid)

                metric_vals: dict[str, list[float]] = {}
                for metric in liq_metrics:
                    vals = []
                    for sn in valid:
                        v = all_stats[sn].get(metric)
                        if v is not None:
                            vals.append(float(v))
                    metric_vals[metric] = vals

                comp_vals = [(sn, all_ranked[sn]["composite_pct"]) for sn in valid]
                comp_sorted = sorted(comp_vals, key=lambda x: x[1], reverse=True)
                ordinal: dict[str, int] = {}
                for pos, (sn, _) in enumerate(comp_sorted, 1):
                    ordinal[sn] = pos

                all_comp = [all_ranked[sn]["composite_pct"] for sn in valid]

                for sn in valid:
                    stats = all_stats[sn]
                    ranked = all_ranked[sn]

                    vol_pct = None
                    if metric_vals["avg_monthly_txns"]:
                        v = stats.get("avg_monthly_txns")
                        if v is not None:
                            vol_pct = _compute_percentile(metric_vals["avg_monthly_txns"], float(v))

                    con_pct = None
                    if metric_vals["consistency"]:
                        v = stats.get("consistency")
                        if v is not None:
                            con_pct = _compute_percentile(metric_vals["consistency"], float(v))

                    trend_pct = None
                    if len(metric_vals["trend_ratio"]) >= 3:
                        v = stats.get("trend_ratio")
                        if v is not None:
                            trend_pct = _compute_percentile(metric_vals["trend_ratio"], float(v))

                    lr_pct = None
                    if len(metric_vals["listing_ratio"]) >= 3:
                        v = stats.get("listing_ratio")
                        if v is not None:
                            lr_pct = round(
                                100.0 - _compute_percentile(metric_vals["listing_ratio"], float(v)),
                                1,
                            )

                    comp_pct = _compute_percentile(all_comp, ranked["composite_pct"])

                    cohort_results[sn][strategy] = {
                        "key": bucket_key,
                        "size": cohort_size,
                        "rank": ordinal.get(sn),
                        "composite_pct": comp_pct,
                        "volume_pct": vol_pct,
                        "consistency_pct": con_pct,
                        "trend_pct": trend_pct,
                        "listing_ratio_pct": lr_pct,
                    }

        _liq_cohort_cache[cache_key] = {
            "results": cohort_results,
            "expires": now + _LIQ_COHORT_TTL,
        }

    return _liq_cohort_cache[cache_key]


@router.get("/{set_number}/liquidity/cohorts")
async def get_item_liquidity_cohorts(
    set_number: str,
    source: str = "bricklink",
    condition: str = "new",
    conn: Any = Depends(get_db),
):
    """Liquidity percentile rankings within cohort peer groups."""
    cached = await _ensure_liq_cohort_cache(source, condition, conn)
    if not cached:
        return {"success": True, "data": None}

    cohort_data = cached["results"].get(set_number, {})
    if not cohort_data:
        return {"success": True, "data": None}

    return {"success": True, "data": sanitize_nan(cohort_data)}


@router.get("/{set_number}/minifigures")
async def get_item_minifigures(set_number: str, conn: Any = Depends(get_db)):
    """Get minifigure inventory and values for a LEGO set."""
    rows = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE set_number = ?",
        [set_number],
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


@router.get("/{set_number}/minifigures/value-history")
async def get_minifig_value_history(set_number: str, conn: Any = Depends(get_db)):
    """Get aggregated minifigure value history for a LEGO set."""
    rows = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE set_number = ?",
        [set_number],
    ).fetchall()

    if not rows:
        return {"success": True, "data": {"snapshots": []}}

    item_id = rows[0][0]
    snapshots = get_set_minifig_value_history(conn, item_id)

    return {"success": True, "data": {"snapshots": snapshots}}


@router.post("/{set_number}/minifigures/scrape")
async def scrape_item_minifigures(set_number: str, conn: Any = Depends(get_db)):
    """Trigger minifigure scraping for a LEGO set."""
    rows = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE set_number = ?",
        [set_number],
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


@router.get("/{set_number}/bricklink-prices")
async def get_item_bricklink_prices(set_number: str, conn: Any = Depends(get_db)):
    """Get BrickLink price history and monthly sales for an item."""
    rows = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE set_number = ?",
        [set_number],
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


@router.get("/{set_number}/brickeconomy")
async def get_item_brickeconomy(set_number: str, conn: Any = Depends(get_db)):
    """Get the latest BrickEconomy snapshot for an item."""
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


@router.get("/{set_number}/keepa")
async def get_item_keepa(set_number: str, conn: Any = Depends(get_db)):
    """Get the latest Keepa snapshot for an item."""
    from services.keepa.repository import get_latest_keepa_snapshot

    snapshot = get_latest_keepa_snapshot(conn, set_number)
    if not snapshot:
        return {"success": True, "data": None}

    if snapshot.get("scraped_at"):
        snapshot["scraped_at"] = str(snapshot["scraped_at"])

    return {"success": True, "data": snapshot}


@router.get("/{set_number}/trends")
async def get_item_trends(set_number: str, conn: Any = Depends(get_db)):
    """Get the latest Google Trends snapshot for an item."""
    from services.google_trends.repository import get_latest_trends_snapshot

    snapshot = get_latest_trends_snapshot(conn, set_number)
    if not snapshot:
        return {"success": True, "data": None}

    if snapshot.get("scraped_at"):
        snapshot["scraped_at"] = str(snapshot["scraped_at"])

    return {"success": True, "data": snapshot}


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


# ---------------------------------------------------------------------------
# Bundle endpoint: returns all detail-page data in a single request
# ---------------------------------------------------------------------------

_bundle_logger = logging.getLogger("bws.api.items.bundle")


def _fetch_brickeconomy(set_number: str) -> dict | None:
    from db.connection import get_connection
    from services.brickeconomy.repository import get_latest_snapshot

    conn = get_connection()
    try:
        snapshot = get_latest_snapshot(conn, set_number)
        if not snapshot and "-" not in set_number:
            snapshot = get_latest_snapshot(conn, f"{set_number}-1")
        if snapshot and snapshot.get("scraped_at"):
            snapshot["scraped_at"] = str(snapshot["scraped_at"])
        return snapshot
    finally:
        conn.close()


def _fetch_keepa(set_number: str) -> dict | None:
    from db.connection import get_connection
    from services.keepa.repository import get_latest_keepa_snapshot

    conn = get_connection()
    try:
        snapshot = get_latest_keepa_snapshot(conn, set_number)
        if snapshot and snapshot.get("scraped_at"):
            snapshot["scraped_at"] = str(snapshot["scraped_at"])
        return snapshot
    finally:
        conn.close()


def _fetch_bricklink_prices(set_number: str) -> dict:
    from db.connection import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE set_number = ?",
            [set_number],
        ).fetchall()
        if not rows:
            return {"price_history": [], "monthly_sales": []}

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
            "item_id": item_id,
            "price_history": serialized_history,
            "monthly_sales": serialized_sales,
        }
    finally:
        conn.close()


def _fetch_bricklink_sellers(set_number: str) -> dict | None:
    from db.connection import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE set_number = ?",
            [set_number],
        ).fetchall()
        if not rows:
            return None
        item_id = rows[0][0]
        stats = get_store_listing_country_stats(conn, item_id)
        if stats is None:
            return None
        return {"item_id": item_id, **stats}
    finally:
        conn.close()


def _fetch_competition(set_number: str) -> dict:
    from db.connection import get_connection
    from services.shopee.competition_repository import (
        get_competition_history,
        get_latest_competition_listings,
        get_listing_sold_deltas,
    )

    conn = get_connection()
    try:
        history = get_competition_history(conn, set_number)
        listings = get_latest_competition_listings(conn, set_number)
        deltas = get_listing_sold_deltas(conn, set_number)
        for listing in listings:
            listing["sold_delta"] = deltas.get(listing["product_url"])
        return {"history": history, "listings": listings}
    finally:
        conn.close()


def _fetch_my_liquidity(set_number: str) -> dict:
    from db.connection import get_connection
    from services.my_liquidity import build_my_liquidity_data

    conn = get_connection()
    try:
        return sanitize_nan(build_my_liquidity_data(conn, set_number))
    finally:
        conn.close()


def _fetch_minifigures(set_number: str) -> dict:
    from db.connection import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE set_number = ?",
            [set_number],
        ).fetchall()
        if not rows:
            return {"minifig_count": 0, "minifigures": []}

        item_id = rows[0][0]
        minifigs = get_set_minifigures(conn, item_id)

        total_value_cents = 0
        has_value = False
        for mf in minifigs:
            if mf["current_new_avg_cents"] is not None:
                total_value_cents += mf["current_new_avg_cents"] * mf["quantity"]
                has_value = True

        return {
            "set_item_id": item_id,
            "minifig_count": len(minifigs),
            "total_value_cents": total_value_cents if has_value else None,
            "total_value_currency": minifigs[0]["currency"] if minifigs else "USD",
            "minifigures": minifigs,
        }
    finally:
        conn.close()


def _fetch_minifig_value_history(set_number: str) -> dict:
    from db.connection import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE set_number = ?",
            [set_number],
        ).fetchall()
        if not rows:
            return {"snapshots": []}

        item_id = rows[0][0]
        snapshots = get_set_minifig_value_history(conn, item_id)
        return {"snapshots": snapshots}
    finally:
        conn.close()


def _fetch_ml_growth(set_number: str) -> dict | None:
    from db.connection import get_connection
    from services.scoring.growth_provider import growth_provider

    conn = get_connection()
    try:
        scores = growth_provider.score_all(conn)
        pred = scores.get(set_number)
        if pred is not None:
            return sanitize_nan({"set_number": set_number, **pred})
        return None
    finally:
        conn.close()


def _fetch_ml_tracking(set_number: str) -> list:
    from db.connection import get_connection
    from services.ml.prediction_tracker import get_prediction_history

    conn = get_connection()
    try:
        return get_prediction_history(conn, set_number)
    finally:
        conn.close()


def _fetch_signals(set_number: str) -> dict | None:
    """Return cached signals for a single item (uses module-level cache)."""
    import time

    from db.connection import get_connection
    from services.scoring.provider import enrich_signals

    cache_key = "new"
    now = time.time()

    if cache_key not in _signals_cache or _signals_cache[cache_key]["expires"] <= now:
        conn = get_connection()
        try:
            signals = compute_all_signals_with_cohort(conn, condition="new")
            signals = enrich_signals(signals, conn)
            result = sanitize_nan(signals)
            _signals_cache[cache_key] = {"data": result, "expires": now + _SIGNALS_TTL}
        finally:
            conn.close()

    cached = _signals_cache[cache_key]["data"]
    return next((s for s in cached if s.get("set_number") == set_number), None)


def _fetch_signals_be(set_number: str) -> dict | None:
    """Return cached Keepa signals for a single item."""
    import time

    from db.connection import get_connection

    now = time.time()
    cache_key = "be"

    if cache_key not in _be_signals_cache or _be_signals_cache[cache_key]["expires"] <= now:
        conn = get_connection()
        try:
            signals = compute_keepa_signals_with_cohort(conn)
            result = sanitize_nan(signals)
            _be_signals_cache[cache_key] = {"data": result, "expires": now + _SIGNALS_TTL}
        finally:
            conn.close()

    cached = _be_signals_cache[cache_key]["data"]
    return next((s for s in cached if s.get("set_number") == set_number), None)


@router.get("/{set_number}/bricklink-sellers")
async def get_item_bricklink_sellers(set_number: str, conn: Any = Depends(get_db)):
    """Return latest BrickLink store-listing snapshot grouped by condition.

    Provides Asia stats (count/min/max/mean/median) plus the cheapest
    Asian shop and cheapest global shop for both new and used listings.
    """
    if not item_exists(conn, set_number):
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")
    data = await asyncio.to_thread(_fetch_bricklink_sellers, set_number)
    return {"success": True, "data": data}


@router.get("/{set_number}/detail-bundle")
async def get_item_detail_bundle(set_number: str, conn: Any = Depends(get_db)):
    """Return all detail-page data in a single response.

    Runs independent queries in parallel threads to minimize latency.
    Each thread gets its own pooled DB connection.
    """
    # Verify item exists first
    if not item_exists(conn, set_number):
        raise HTTPException(status_code=404, detail=f"Item {set_number} not found")

    # Run cheap per-item fetches in parallel
    (
        brickeconomy,
        keepa,
        bricklink_prices,
        bricklink_sellers,
        competition,
        my_liquidity,
        my_liquidity_cohorts,
        minifigures,
        minifig_value_history,
        ml_growth,
        ml_tracking,
    ) = await asyncio.gather(
        asyncio.to_thread(_fetch_brickeconomy, set_number),
        asyncio.to_thread(_fetch_keepa, set_number),
        asyncio.to_thread(_fetch_bricklink_prices, set_number),
        asyncio.to_thread(_fetch_bricklink_sellers, set_number),
        asyncio.to_thread(_fetch_competition, set_number),
        asyncio.to_thread(_fetch_my_liquidity, set_number),
        asyncio.to_thread(_fetch_my_cohorts, set_number),
        asyncio.to_thread(_fetch_minifigures, set_number),
        asyncio.to_thread(_fetch_minifig_value_history, set_number),
        asyncio.to_thread(_fetch_ml_growth, set_number),
        asyncio.to_thread(_fetch_ml_tracking, set_number),
    )

    # Signals and liquidity compute over ALL items on cold cache (very slow).
    # Only include them if the caches are already warm.
    import time as _time

    _now = _time.time()
    signals = None
    signals_be = None
    liq_bl_data = None
    liq_be_data = None
    liq_cohorts_data = None

    if "new" in _signals_cache and _signals_cache["new"]["expires"] > _now:
        cached = _signals_cache["new"]["data"]
        signals = next((s for s in cached if s.get("set_number") == set_number), None)

    if "be" in _be_signals_cache and _be_signals_cache["be"]["expires"] > _now:
        cached = _be_signals_cache["be"]["data"]
        signals_be = next((s for s in cached if s.get("set_number") == set_number), None)

    liq_bl_key = "bricklink:new"
    if liq_bl_key in _liquidity_cache and _liquidity_cache[liq_bl_key]["expires"] > _now:
        liq_bl_resp = await get_item_liquidity(set_number, "bricklink", "new", False, conn)
        liq_bl_data = liq_bl_resp.get("data") if isinstance(liq_bl_resp, dict) else None

    liq_be_key = "brickeconomy:new"
    if liq_be_key in _liquidity_cache and _liquidity_cache[liq_be_key]["expires"] > _now:
        liq_be_resp = await get_item_liquidity(set_number, "brickeconomy", "new", False, conn)
        liq_be_data = liq_be_resp.get("data") if isinstance(liq_be_resp, dict) else None

    if liq_bl_data is not None:
        liq_cohorts_resp = await get_item_liquidity_cohorts(set_number, "bricklink", "new", conn)
        liq_cohorts_data = liq_cohorts_resp.get("data") if isinstance(liq_cohorts_resp, dict) else None

    return {
        "success": True,
        "data": {
            "brickeconomy": brickeconomy,
            "keepa": keepa,
            "bricklink_prices": bricklink_prices,
            "bricklink_sellers": bricklink_sellers,
            "competition": competition,
            "my_liquidity": my_liquidity,
            "my_liquidity_cohorts": sanitize_nan(my_liquidity_cohorts) if my_liquidity_cohorts else None,
            "minifigures": minifigures,
            "minifig_value_history": minifig_value_history,
            "ml_growth": ml_growth,
            "ml_tracking": sanitize_nan(ml_tracking),
            "signals": signals,
            "signals_be": signals_be,
            "liquidity_bricklink": liq_bl_data,
            "liquidity_brickeconomy": liq_be_data,
            "liquidity_cohorts": liq_cohorts_data,
        },
    }
