"""Bricklink scraper orchestration.

Coordinates fetching HTML and parsing data from Bricklink.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx

from config.settings import (
    BRICKLINK_RATE_LIMITER,
    RETRY_CONFIG,
    calculate_backoff,
    get_random_accept_language,
    get_random_delay,
    get_random_user_agent,
)
from services.bricklink.parser import (
    build_catalog_list_url,
    build_item_url,
    build_minifig_inventory_url,
    build_price_guide_url,
    parse_bricklink_url,
    parse_catalog_list_page,
    parse_catalog_list_pagination,
    parse_full_item,
    parse_minifig_inventory,
    parse_monthly_sales,
)
from services.bricklink.repository import (
    create_minifig_price_history,
    create_price_history,
    get_item,
    has_recent_minifig_pricing,
    upsert_item,
    upsert_minifigure,
    upsert_monthly_sales,
    upsert_set_minifigures,
)
from bws_types.models import BricklinkData, BricklinkItem, CatalogListItem, MinifigureData, MonthlySale


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


@dataclass(frozen=True)
class ScrapeResult:
    """Result of a scrape operation."""

    success: bool
    item_id: str
    data: BricklinkData | None = None
    monthly_sales: tuple[MonthlySale, ...] | None = None
    error: str | None = None


@dataclass(frozen=True)
class MinifigScrapeResult:
    """Result of scraping minifigures for a set."""

    success: bool
    set_item_id: str
    minifig_count: int = 0
    minifigures_scraped: int = 0
    minifigures: tuple[MinifigureData, ...] = ()
    total_value_cents: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class CatalogScrapeResult:
    """Result of scraping a catalog list."""

    success: bool
    total_pages: int = 0
    items_found: int = 0
    items_inserted: int = 0
    items_skipped: int = 0
    items: tuple[CatalogListItem, ...] = ()
    error: str | None = None


def _get_headers() -> dict[str, str]:
    """Generate random browser-like headers."""
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": get_random_accept_language(),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


class BricklinkQuotaExceeded(Exception):
    """Raised when BrickLink returns a quota exceeded redirect."""


def _is_rate_limited(response: httpx.Response) -> bool:
    """Check if BrickLink redirected to a rate-limit error page (429)."""
    return "error.page" in str(response.url) and "code=429" in str(response.url)


def _is_forbidden(response: httpx.Response) -> bool:
    """Check if BrickLink redirected to a forbidden error page (403).

    BrickLink escalates from 429 -> 403 after sustained scraping.
    A 403 indicates a hard IP ban, requiring a much longer cooldown.
    """
    return "error.page" in str(response.url) and "code=403" in str(response.url)


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page with browser-like headers and exponential backoff.

    Retries on HTTP 429/503 status codes and BrickLink's quota exceeded
    redirect (302 -> error.page?code=429 returning 200).
    Backoff starts at 30s and doubles each attempt.

    Args:
        client: HTTP client
        url: URL to fetch

    Returns:
        HTML content

    Raises:
        httpx.HTTPStatusError: If request fails after retries
        BricklinkQuotaExceeded: If quota exceeded after all retries
    """
    for attempt in range(1, RETRY_CONFIG.max_retries + 1):
        await BRICKLINK_RATE_LIMITER.acquire()
        response = await client.get(url, headers=_get_headers(), follow_redirects=True)

        # 403 = hard IP ban -- trip immediately, no retries
        if response.status_code == 403 or _is_forbidden(response):
            BRICKLINK_RATE_LIMITER.trip_forbidden()
            raise BricklinkQuotaExceeded(f"403 Forbidden (IP banned): {url}")

        is_rate_limited = response.status_code in (429, 503) or _is_rate_limited(response)

        if is_rate_limited:
            if attempt < RETRY_CONFIG.max_retries:
                backoff = calculate_backoff(attempt)
                logging.getLogger("bws.bricklink").warning(
                    "Rate limited (attempt %d/%d), backing off %.0fs: %s",
                    attempt, RETRY_CONFIG.max_retries, backoff, url,
                )
                await asyncio.sleep(backoff)
                continue
            BRICKLINK_RATE_LIMITER.trip_quota_exceeded()
            raise BricklinkQuotaExceeded(f"Quota exceeded after {RETRY_CONFIG.max_retries} retries: {url}")

        response.raise_for_status()
        return response.text
    # Unreachable, but satisfies type checker
    raise BricklinkQuotaExceeded(f"Quota exceeded: {url}")


async def scrape_item(
    conn: "DuckDBPyConnection",
    url: str,
    *,
    save: bool = True,
    skip_pricing: bool = False,
    client: httpx.AsyncClient | None = None,
) -> ScrapeResult:
    """Scrape a single Bricklink item.

    Args:
        conn: DuckDB connection
        url: Bricklink URL (price guide or catalog page)
        save: Whether to save results to database
        client: Optional HTTP client (creates one if not provided)

    Returns:
        ScrapeResult with data or error
    """
    try:
        item_type, item_id = parse_bricklink_url(url)
    except ValueError as e:
        return ScrapeResult(success=False, item_id="unknown", error=str(e))

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        # Build URLs
        item_url = build_item_url(item_type, item_id)
        price_guide_url = build_price_guide_url(item_type, item_id)

        # Fetch item page
        item_html = await _fetch_page(client, item_url)

        # Rate limit delay
        await asyncio.sleep(get_random_delay())

        # Fetch price guide
        price_guide_html = await _fetch_page(client, price_guide_url)

        # Parse data
        data = parse_full_item(item_html, price_guide_html, item_type, item_id)

        # Parse monthly sales
        monthly_sales_list = parse_monthly_sales(price_guide_html)
        # Update item_id in monthly sales (parser returns empty string)
        monthly_sales = tuple(
            MonthlySale(
                item_id=item_id,
                year=s.year,
                month=s.month,
                condition=s.condition,
                times_sold=s.times_sold,
                total_quantity=s.total_quantity,
                min_price=s.min_price,
                max_price=s.max_price,
                avg_price=s.avg_price,
                currency=s.currency,
            )
            for s in monthly_sales_list
        )

        # Save to database if requested
        if save:
            upsert_item(conn, data)
            if not skip_pricing:
                create_price_history(conn, item_id, data)
                if monthly_sales:
                    upsert_monthly_sales(conn, item_id, list(monthly_sales))

        return ScrapeResult(
            success=True,
            item_id=item_id,
            data=data,
            monthly_sales=monthly_sales,
        )

    except BricklinkQuotaExceeded as e:
        return ScrapeResult(success=False, item_id=item_id, error=str(e))
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return ScrapeResult(success=False, item_id=item_id, error=error_msg)
    except httpx.RequestError as e:
        return ScrapeResult(success=False, item_id=item_id, error=f"Request error: {e}")
    except ValueError as e:
        return ScrapeResult(success=False, item_id=item_id, error=str(e))
    except (TimeoutError, OSError) as e:
        return ScrapeResult(success=False, item_id=item_id, error=f"Network error: {e}")
    finally:
        if should_close_client:
            await client.aclose()


async def scrape_item_by_id(
    conn: "DuckDBPyConnection",
    item_type: str,
    item_id: str,
    *,
    save: bool = True,
    skip_pricing: bool = False,
    client: httpx.AsyncClient | None = None,
) -> ScrapeResult:
    """Scrape a Bricklink item by type and ID.

    Args:
        conn: DuckDB connection
        item_type: Item type (P, S, M, etc.)
        item_id: Item ID
        save: Whether to save results to database
        skip_pricing: Whether to skip writing pricing data
        client: Optional HTTP client

    Returns:
        ScrapeResult with data or error
    """
    url = build_price_guide_url(item_type, item_id)
    return await scrape_item(conn, url, save=save, skip_pricing=skip_pricing, client=client)


async def scrape_set_minifigures(
    conn: "DuckDBPyConnection",
    item_id: str,
    *,
    save: bool = True,
    scrape_prices: bool = True,
    pricing_freshness: timedelta | None = None,
    client: httpx.AsyncClient | None = None,
) -> MinifigScrapeResult:
    """Scrape minifigure inventory and prices for a LEGO set.

    Args:
        conn: DuckDB connection
        item_id: Set item ID (e.g., "77256-1")
        save: Whether to save results to database
        scrape_prices: Whether to fetch individual minifig prices
        pricing_freshness: If set, skip pricing writes for minifigs with
            recent pricing within this window
        client: Optional HTTP client

    Returns:
        MinifigScrapeResult with minifig data
    """
    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        # Fetch minifigure inventory page
        inventory_url = build_minifig_inventory_url(item_id)
        inventory_html = await _fetch_page(client, inventory_url)

        # Parse inventory
        minifig_infos = parse_minifig_inventory(inventory_html)

        if not minifig_infos:
            return MinifigScrapeResult(
                success=True,
                set_item_id=item_id,
                minifig_count=0,
            )

        # Save set-minifig relationships
        if save:
            upsert_set_minifigures(conn, item_id, minifig_infos)

        # Scrape individual minifig prices
        minifig_data_list: list[MinifigureData] = []
        total_value_cents = 0
        has_value = False

        for mf_info in minifig_infos:
            if not scrape_prices:
                minifig_data_list.append(MinifigureData(
                    minifig_id=mf_info.minifig_id,
                    name=mf_info.name,
                    image_url=mf_info.image_url,
                ))
                continue

            await asyncio.sleep(get_random_delay())

            try:
                # Fetch minifig catalog page
                mf_item_url = build_item_url("M", mf_info.minifig_id)
                mf_item_html = await _fetch_page(client, mf_item_url)

                await asyncio.sleep(get_random_delay())

                # Fetch minifig price guide
                mf_price_url = build_price_guide_url("M", mf_info.minifig_id)
                mf_price_html = await _fetch_page(client, mf_price_url)

                # Parse using existing parser (supports M type)
                mf_full = parse_full_item(mf_item_html, mf_price_html, "M", mf_info.minifig_id)

                mf_data = MinifigureData(
                    minifig_id=mf_info.minifig_id,
                    name=mf_full.title or mf_info.name,
                    image_url=mf_full.image_url or mf_info.image_url,
                    year_released=mf_full.year_released,
                    six_month_new=mf_full.six_month_new,
                    six_month_used=mf_full.six_month_used,
                    current_new=mf_full.current_new,
                    current_used=mf_full.current_used,
                )
                minifig_data_list.append(mf_data)

                # Accumulate total value (current new avg price * quantity)
                if mf_data.current_new and mf_data.current_new.avg_price:
                    total_value_cents += mf_data.current_new.avg_price.amount * mf_info.quantity
                    has_value = True

                # Save minifig data
                if save:
                    upsert_minifigure(conn, mf_data)
                    skip_mf_pricing = (
                        pricing_freshness is not None
                        and has_recent_minifig_pricing(conn, mf_info.minifig_id, pricing_freshness)
                    )
                    if not skip_mf_pricing:
                        create_minifig_price_history(conn, mf_info.minifig_id, mf_data)

            except BricklinkQuotaExceeded:
                raise  # Stop all scraping on quota exceeded
            except (httpx.HTTPStatusError, httpx.RequestError, ValueError, TimeoutError) as e:
                # Log but continue with other minifigs
                minifig_data_list.append(MinifigureData(
                    minifig_id=mf_info.minifig_id,
                    name=mf_info.name,
                    image_url=mf_info.image_url,
                ))
                continue

        return MinifigScrapeResult(
            success=True,
            set_item_id=item_id,
            minifig_count=len(minifig_infos),
            minifigures_scraped=sum(
                1 for m in minifig_data_list if m.current_new is not None
            ),
            minifigures=tuple(minifig_data_list),
            total_value_cents=total_value_cents if has_value else None,
        )

    except BricklinkQuotaExceeded as e:
        return MinifigScrapeResult(success=False, set_item_id=item_id, error=str(e))
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return MinifigScrapeResult(success=False, set_item_id=item_id, error=error_msg)
    except httpx.RequestError as e:
        return MinifigScrapeResult(success=False, set_item_id=item_id, error=f"Request error: {e}")
    except (TimeoutError, OSError) as e:
        return MinifigScrapeResult(success=False, set_item_id=item_id, error=f"Network error: {e}")
    finally:
        if should_close_client:
            await client.aclose()


async def scrape_catalog_list(
    conn: "DuckDBPyConnection",
    url: str,
    *,
    save: bool = True,
    client: httpx.AsyncClient | None = None,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> CatalogScrapeResult:
    """Scrape a BrickLink catalog list page with pagination.

    Discovers items from catalogList.asp pages, inserting minimal records
    so the enrichment worker can populate metadata later.

    Args:
        conn: DuckDB connection
        url: catalogList.asp URL (any page -- pagination is auto-detected)
        save: Whether to save discovered items to database
        client: Optional HTTP client
        on_progress: Optional callback(current_page, total_pages, items_so_far)

    Returns:
        CatalogScrapeResult with discovered items
    """
    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        # Fetch first page
        page1_url = build_catalog_list_url(url, page=1)
        html = await _fetch_page(client, page1_url)

        # Parse items and detect total pages
        all_items = parse_catalog_list_page(html)
        total_pages = parse_catalog_list_pagination(html)

        if on_progress:
            on_progress(1, total_pages, len(all_items))

        # Fetch remaining pages
        for page_num in range(2, total_pages + 1):
            await asyncio.sleep(get_random_delay())
            page_url = build_catalog_list_url(url, page=page_num)
            page_html = await _fetch_page(client, page_url)
            page_items = parse_catalog_list_page(page_html)
            all_items.extend(page_items)

            if on_progress:
                on_progress(page_num, total_pages, len(all_items))

        # Deduplicate by item_id
        seen: set[str] = set()
        unique_items: list[CatalogListItem] = []
        for item in all_items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                unique_items.append(item)

        items_inserted = 0
        items_skipped = 0

        if save:
            for item in unique_items:
                existing = get_item(conn, item.item_id)
                if existing:
                    items_skipped += 1
                    continue

                # Create minimal BricklinkData for new items
                data = BricklinkData(
                    item_id=item.item_id,
                    item_type=item.item_type,
                    title=item.title,
                    year_released=item.year_released,
                    image_url=item.image_url,
                )
                upsert_item(conn, data)
                items_inserted += 1

        return CatalogScrapeResult(
            success=True,
            total_pages=total_pages,
            items_found=len(unique_items),
            items_inserted=items_inserted,
            items_skipped=items_skipped,
            items=tuple(unique_items),
        )

    except BricklinkQuotaExceeded as e:
        return CatalogScrapeResult(success=False, error=str(e))
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return CatalogScrapeResult(success=False, error=error_msg)
    except httpx.RequestError as e:
        return CatalogScrapeResult(success=False, error=f"Request error: {e}")
    except (TimeoutError, OSError) as e:
        return CatalogScrapeResult(success=False, error=f"Network error: {e}")
    finally:
        if should_close_client:
            await client.aclose()


def scrape_set_minifigures_sync(
    conn: "DuckDBPyConnection",
    item_id: str,
    *,
    save: bool = True,
    scrape_prices: bool = True,
    pricing_freshness: timedelta | None = None,
) -> MinifigScrapeResult:
    """Synchronous wrapper for scrape_set_minifigures."""
    return asyncio.run(
        scrape_set_minifigures(
            conn, item_id, save=save, scrape_prices=scrape_prices,
            pricing_freshness=pricing_freshness,
        )
    )


async def scrape_batch(
    conn: "DuckDBPyConnection",
    items: list[BricklinkItem],
    *,
    progress_callback: Callable[[int, int, ScrapeResult], None] | None = None,
) -> list[ScrapeResult]:
    """Scrape a batch of items with rate limiting.

    Args:
        conn: DuckDB connection
        items: List of BricklinkItem to scrape
        progress_callback: Optional callback(current, total, result)

    Returns:
        List of ScrapeResult objects
    """
    results: list[ScrapeResult] = []
    total = len(items)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, item in enumerate(items):
            # Scrape item
            result = await scrape_item_by_id(
                conn,
                item.item_type,
                item.item_id,
                save=True,
                client=client,
            )
            results.append(result)

            # Call progress callback
            if progress_callback:
                progress_callback(i + 1, total, result)

            # Rate limit delay between items (skip for last item)
            if i < total - 1:
                delay = get_random_delay()
                await asyncio.sleep(delay)

    return results


def scrape_item_sync(
    conn: "DuckDBPyConnection",
    url: str,
    *,
    save: bool = True,
    skip_pricing: bool = False,
) -> ScrapeResult:
    """Synchronous wrapper for scrape_item.

    Args:
        conn: DuckDB connection
        url: Bricklink URL
        save: Whether to save results to database
        skip_pricing: Whether to skip writing pricing data

    Returns:
        ScrapeResult with data or error
    """
    return asyncio.run(scrape_item(conn, url, save=save, skip_pricing=skip_pricing))


def scrape_batch_sync(
    conn: "DuckDBPyConnection",
    items: list[BricklinkItem],
    *,
    progress_callback: Callable[[int, int, ScrapeResult], None] | None = None,
) -> list[ScrapeResult]:
    """Synchronous wrapper for scrape_batch.

    Args:
        conn: DuckDB connection
        items: List of BricklinkItem to scrape
        progress_callback: Optional callback(current, total, result)

    Returns:
        List of ScrapeResult objects
    """
    return asyncio.run(scrape_batch(conn, items, progress_callback=progress_callback))
