"""Bricklink scraper orchestration.

Coordinates fetching HTML and parsing data from Bricklink.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from config.settings import (
    get_random_accept_language,
    get_random_delay,
    get_random_user_agent,
)
from services.bricklink.parser import (
    build_item_url,
    build_price_guide_url,
    parse_bricklink_url,
    parse_full_item,
    parse_monthly_sales,
)
from services.bricklink.repository import (
    create_price_history,
    upsert_item,
    upsert_monthly_sales,
)
from bws_types.models import BricklinkData, BricklinkItem, MonthlySale


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


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page with browser-like headers.

    Args:
        client: HTTP client
        url: URL to fetch

    Returns:
        HTML content

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    response = await client.get(url, headers=_get_headers(), follow_redirects=True)
    response.raise_for_status()
    return response.text


async def scrape_item(
    conn: "DuckDBPyConnection",
    url: str,
    *,
    save: bool = True,
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
            create_price_history(conn, item_id, data)
            if monthly_sales:
                upsert_monthly_sales(conn, item_id, list(monthly_sales))

        return ScrapeResult(
            success=True,
            item_id=item_id,
            data=data,
            monthly_sales=monthly_sales,
        )

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
    client: httpx.AsyncClient | None = None,
) -> ScrapeResult:
    """Scrape a Bricklink item by type and ID.

    Args:
        conn: DuckDB connection
        item_type: Item type (P, S, M, etc.)
        item_id: Item ID
        save: Whether to save results to database
        client: Optional HTTP client

    Returns:
        ScrapeResult with data or error
    """
    url = build_price_guide_url(item_type, item_id)
    return await scrape_item(conn, url, save=save, client=client)


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
) -> ScrapeResult:
    """Synchronous wrapper for scrape_item.

    Args:
        conn: DuckDB connection
        url: Bricklink URL
        save: Whether to save results to database

    Returns:
        ScrapeResult with data or error
    """
    return asyncio.run(scrape_item(conn, url, save=save))


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
