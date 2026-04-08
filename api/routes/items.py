"""Items API routes."""

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
)
from services.bricklink.scraper import scrape_set_minifigures
from services.backtesting.position_sizing import (
    compute_position_sizing,
    kelly_to_dict,
)
from services.backtesting.be_screener import compute_be_signals_with_cohort
from services.backtesting.screener import (
    compute_all_signals_with_cohort,
)
from services.items.repository import get_all_items, get_all_items_lite, get_item_detail, get_or_create_item, item_exists, toggle_watchlist, update_buy_rating
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


@router.get("/{set_number}/kelly")
async def get_item_kelly(
    set_number: str,
    budget: int | None = None,
    condition: str = "new",
    conn: Any = Depends(get_db),
):
    """Compute Kelly Criterion position sizing for a single item."""
    sizing = compute_position_sizing(
        conn, set_number, budget_cents=budget, condition=condition
    )
    if not sizing:
        return {"success": True, "data": None}
    return {"success": True, "data": kelly_to_dict(sizing)}


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
    """BrickEconomy-based signals and cohort ranks for a single item."""
    import time

    now = time.time()
    cache_key = "be"

    if cache_key not in _be_signals_cache or _be_signals_cache[cache_key]["expires"] <= now:
        signals = compute_be_signals_with_cohort(conn)
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
    # Trigger per-item cohort build via the single-item endpoint
    await get_item_liquidity_cohorts("__warmup__", source, condition, conn)

    cache_key = f"{source}:{condition}"
    cached = _liq_cohort_cache.get(cache_key)
    if not cached:
        return {"success": True, "data": {}}

    # Return only non-empty entries, with composite_pct per strategy
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

    return {
        "total_months": total_months,
        "months_with_sales": months_with_sales,
        "consistency": round(consistency, 3),
        "total_txns": total_txns,
        "total_qty": total_qty,
        "avg_monthly_txns": round(avg_monthly_txns, 1),
        "avg_monthly_qty": avg_monthly_qty,
        "recent_avg_txns": round(recent_avg, 1),
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
                sn = item_id.removesuffix("-1")
                txns = [r[3] or 0 for r in records]
                qtys = [r[4] or 0 for r in records]
                monthly = [{"label": f"{r[1]}-{r[2]:02d}", "txns": r[3] or 0} for r in records]
                stats = _item_volume_stats(txns, qtys)
                if stats:
                    stats["monthly"] = monthly
                    # Listing ratio: current listings / avg monthly sold (last 6mo)
                    listing = listing_map.get(item_id)
                    if listing and stats["recent_avg_txns"] > 0:
                        stats["listing_lots"] = listing[0]
                        stats["listing_qty"] = listing[1]
                        stats["listing_ratio"] = round(listing[0] / stats["recent_avg_txns"], 2)
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
            "detail": f"{target.get('listing_lots', 0)} lots vs {target['recent_avg_txns']}/mo sold",
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


@router.get("/{set_number}/liquidity/cohorts")
async def get_item_liquidity_cohorts(
    set_number: str,
    source: str = "bricklink",
    condition: str = "new",
    conn: Any = Depends(get_db),
):
    """Liquidity percentile rankings within cohort peer groups."""
    import time

    from services.backtesting.cohort import STRATEGY_NAMES, _assign_bucket, _compute_percentile

    cache_key = f"{source}:{condition}"
    now = time.time()

    # Ensure liquidity cache is warm
    if cache_key not in _liquidity_cache or _liquidity_cache[cache_key]["expires"] <= now:
        await get_item_liquidity("__warmup__", source, condition, False, conn)

    cached = _liquidity_cache.get(cache_key)
    if not cached:
        return {"success": True, "data": None}

    all_stats = cached["stats"]
    all_ranked = cached["ranked"]

    if set_number not in all_stats:
        return {"success": True, "data": None}

    # Build or use cohort cache
    if (
        cache_key not in _liq_cohort_cache
        or _liq_cohort_cache[cache_key]["expires"] <= now
    ):
        # Load item metadata for bucket assignment.
        # Use brickeconomy_snapshots as primary source (has theme, pieces,
        # rrp_usd_cents) and enrich with bricklink_items where available.
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
        # Enrich with bricklink_items (has year_released, parts_count)
        bl_rows = conn.execute(
            "SELECT item_id, year_released, theme, parts_count FROM bricklink_items"
        ).fetchall()
        for r in bl_rows:
            sn = r[0].removesuffix("-1")
            if sn not in meta_map:
                meta_map[sn] = {
                    "set_number": sn,
                    "year_released": r[1],
                    "theme": r[2],
                    "parts_count": r[3],
                    "rrp_usd_cents": None,
                }
            else:
                # Prefer bricklink year_released if BE is missing
                if not meta_map[sn].get("year_released") and r[1]:
                    meta_map[sn]["year_released"] = r[1]

        # Assign buckets for each strategy
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

        # Compute per-cohort percentiles for liquidity metrics
        liq_metrics = ("avg_monthly_txns", "consistency", "trend_ratio", "listing_ratio")
        cohort_results: dict[str, dict[str, dict]] = {sn: {} for sn in all_stats}

        for strategy in STRATEGY_NAMES:
            for bucket_key, members in buckets[strategy].items():
                # Filter to members that have liquidity stats
                valid = [sn for sn in members if sn in all_ranked]
                if len(valid) < 3:
                    continue

                cohort_size = len(valid)

                # Collect metric values
                metric_vals: dict[str, list[float]] = {}
                for metric in liq_metrics:
                    vals = []
                    for sn in valid:
                        v = all_stats[sn].get(metric)
                        if v is not None:
                            vals.append(float(v))
                    metric_vals[metric] = vals

                # Collect composite values for ranking
                comp_vals = [(sn, all_ranked[sn]["composite_pct"]) for sn in valid]
                comp_sorted = sorted(comp_vals, key=lambda x: x[1], reverse=True)
                ordinal: dict[str, int] = {}
                for pos, (sn, _) in enumerate(comp_sorted, 1):
                    ordinal[sn] = pos

                # Composite percentiles within cohort
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

                    # Listing ratio: lower = better, so invert
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

    cohort_data = _liq_cohort_cache[cache_key]["results"].get(set_number, {})
    if not cohort_data:
        return {"success": True, "data": None}

    return {"success": True, "data": sanitize_nan(cohort_data)}


@router.get("/{set_number}/minifigures")
async def get_item_minifigures(set_number: str, conn: Any = Depends(get_db)):
    """Get minifigure inventory and values for a LEGO set."""
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


@router.get("/{set_number}/minifigures/value-history")
async def get_minifig_value_history(set_number: str, conn: Any = Depends(get_db)):
    """Get aggregated minifigure value history for a LEGO set."""
    rows = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE item_id LIKE ?",
        [f"{set_number}-%"],
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


@router.get("/{set_number}/bricklink-prices")
async def get_item_bricklink_prices(set_number: str, conn: Any = Depends(get_db)):
    """Get BrickLink price history and monthly sales for an item."""
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
