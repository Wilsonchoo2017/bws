"""Batch competition scraper for Carousell.

Wraps `search_carousell` once per LEGO set, filters results by
relevance (title must mention the set number), builds a
`CarousellCompetitionSnapshot`, and persists it through
`competition_repository.save_competition_snapshot`.

Carousell has no per-listing sold counter, so velocity comes from
counting `active -> sold` state transitions between consecutive
snapshots (see `count_active_to_sold_flips`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.carousell.competition_repository import (
    count_active_to_sold_flips,
    save_competition_snapshot,
)
from services.carousell.competition_types import (
    CarousellCompetitionListing,
    CarousellCompetitionSnapshot,
)
from services.carousell.scraper import (
    CarousellListing,
    _carousell_browser,
    search_carousell_on_browser,
)
from services.marketplace_competition.scorer import (
    CAROUSELL_CAPS,
    classify,
    compute_composite_score,
    compute_price_stats,
)

logger = logging.getLogger("bws.carousell.competition.scraper")


@dataclass(frozen=True)
class CarousellCompetitionBatchResult:
    total_items: int
    successful: int
    failed: int
    skipped: int
    errors: tuple[tuple[str, str], ...]


def _is_relevant(listing: CarousellListing, set_number: str) -> bool:
    """Title must contain the set number, case-insensitive."""
    if not listing.title:
        return False
    return bool(re.search(re.escape(set_number), listing.title.upper()))


def _build_snapshot(
    set_number: str,
    listings: list[CarousellListing],
    flipped: int | None,
) -> CarousellCompetitionSnapshot:
    """Aggregate a relevant-listings list into a snapshot dataclass."""
    comp_listings = tuple(
        CarousellCompetitionListing(
            listing_id=l.listing_id,
            listing_url=l.listing_url,
            shop_id=l.shop_id,
            seller_name=l.seller_name,
            title=l.title,
            price_cents=l.price_cents,
            price_display=l.price,
            condition=l.condition,
            image_url=l.image_url,
            time_ago=l.time_ago,
            is_sold=l.is_sold,
            is_reserved=l.is_reserved,
            is_delisted=False,
        )
        for l in listings
    )

    active_prices = [
        l.price_cents
        for l in listings
        if l.price_cents is not None and not l.is_sold and not l.is_reserved
    ]
    stats = compute_price_stats(active_prices)

    active_count = sum(
        1 for l in listings if not l.is_sold and not l.is_reserved
    )
    shop_ids = {l.shop_id for l in listings if l.shop_id and not l.is_sold and not l.is_reserved}
    unique_sellers = len(shop_ids)

    score = compute_composite_score(
        listings_count=active_count,
        unique_sellers=unique_sellers,
        prices_cents=active_prices,
        caps=CAROUSELL_CAPS,
    )

    return CarousellCompetitionSnapshot(
        set_number=set_number,
        listings_count=active_count,
        unique_sellers=unique_sellers,
        flipped_to_sold_count=flipped,
        min_price_cents=stats.min_cents,
        max_price_cents=stats.max_cents,
        avg_price_cents=stats.avg_cents,
        median_price_cents=stats.median_cents,
        saturation_score=score,
        saturation_level=classify(score),
        scraped_at=datetime.now(timezone.utc),
        listings=comp_listings,
    )


async def scrape_set(
    set_number: str,
    *,
    browser: Any,
    conn: Any | None,
    query: str | None = None,
    max_items: int = 60,
) -> CarousellCompetitionSnapshot | None:
    """Scrape one set on a shared Camoufox browser and return a snapshot.

    The snapshot is NOT saved here; caller owns persistence. Returns
    None when the search fails outright (Cloudflare timeout, etc).
    Relevance filtering and state aggregation happen here. The browser
    is supplied by the caller so an entire batch shares one Camoufox
    instance.
    """
    q = query or f"lego {set_number}"
    result = await search_carousell_on_browser(
        browser, q, max_items=max_items, max_pages=3,
    )
    if not result.success:
        logger.warning(
            "Carousell competition scrape failed for %s: %s",
            set_number,
            result.error,
        )
        return None

    relevant = [l for l in result.listings if _is_relevant(l, set_number)]

    flipped: int | None = None
    if conn is not None:
        listings_for_flip = [
            CarousellCompetitionListing(
                listing_id=l.listing_id,
                listing_url=l.listing_url,
                shop_id=l.shop_id,
                seller_name=l.seller_name,
                title=l.title,
                price_cents=l.price_cents,
                price_display=l.price,
                condition=l.condition,
                image_url=l.image_url,
                time_ago=l.time_ago,
                is_sold=l.is_sold,
                is_reserved=l.is_reserved,
                is_delisted=False,
            )
            for l in relevant
        ]
        flipped = count_active_to_sold_flips(conn, set_number, listings_for_flip)

    return _build_snapshot(set_number, relevant, flipped)


async def run_competition_batch(
    items: list[dict],
    conn: Any | None = None,
) -> CarousellCompetitionBatchResult:
    """Run Carousell competition scrape across a batch of LEGO sets.

    `items` is the tiered-selection output: dicts with `set_number`.
    One Camoufox browser is launched for the whole batch and shared
    across items, so per-item cost is ~one page navigation, not a full
    browser boot. Cloudflare cookies also persist across items in the
    same batch, so at most one CF challenge per sweep.
    """
    import asyncio

    total = len(items)
    successful = 0
    failed = 0
    skipped = 0
    errors: list[tuple[str, str]] = []

    logger.info("Starting Carousell competition batch: %d items (shared browser)", total)

    try:
        async with _carousell_browser() as browser:
            for idx, item in enumerate(items):
                set_number = item["set_number"]
                try:
                    snapshot = await scrape_set(
                        set_number, browser=browser, conn=conn,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Carousell competition scrape errored for %s", set_number,
                    )
                    errors.append((set_number, str(exc)))
                    failed += 1
                else:
                    if snapshot is None:
                        skipped += 1
                    elif conn is not None:
                        try:
                            save_competition_snapshot(conn, snapshot)
                            successful += 1
                        except Exception as exc:  # noqa: BLE001
                            logger.exception(
                                "Carousell snapshot save errored for %s", set_number,
                            )
                            errors.append((set_number, str(exc)))
                            failed += 1
                    else:
                        successful += 1

                # Inter-item cooldown so we don't hammer Carousell with
                # back-to-back navigations on the same browser.
                if idx < total - 1:
                    await asyncio.sleep(3)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Carousell batch browser session failed")
        remaining = total - successful - failed - skipped
        if remaining > 0:
            errors.append(("__batch__", str(exc)))
            failed += remaining

    logger.info(
        "Carousell competition batch done: %d/%d successful (%d failed, %d skipped)",
        successful, total, failed, skipped,
    )

    return CarousellCompetitionBatchResult(
        total_items=total,
        successful=successful,
        failed=failed,
        skipped=skipped,
        errors=tuple(errors),
    )
