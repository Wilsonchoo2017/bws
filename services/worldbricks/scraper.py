"""WorldBricks scraper orchestration.

Coordinates fetching HTML and parsing data from WorldBricks.com.
"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from config.settings import (
    get_random_delay,
    get_random_user_agent,
)
from services.worldbricks.parser import (
    WorldBricksData,
    construct_search_url,
    is_valid_worldbricks_page,
    parse_search_results,
    parse_worldbricks_page,
)
from services.worldbricks.repository import upsert_set


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


@dataclass(frozen=True)
class WorldBricksScrapeResult:
    """Result of a WorldBricks scrape operation."""

    success: bool
    set_number: str
    data: WorldBricksData | None = None
    error: str | None = None


def _get_headers() -> dict[str, str]:
    """Generate random browser-like headers."""
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
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


async def scrape_set(
    conn: "DuckDBPyConnection",
    set_number: str,
    *,
    save: bool = True,
    client: httpx.AsyncClient | None = None,
) -> WorldBricksScrapeResult:
    """Scrape a single LEGO set from WorldBricks.

    Uses search to find the product page, then scrapes the page.

    Args:
        conn: DuckDB connection
        set_number: LEGO set number (e.g., "75192")
        save: Whether to save results to database
        client: Optional HTTP client (creates one if not provided)

    Returns:
        WorldBricksScrapeResult with data or error
    """
    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        # Step 1: Search for the set
        search_url = construct_search_url(set_number)
        search_html = await _fetch_page(client, search_url)

        # Step 2: Find product page URL from search results
        product_url = parse_search_results(search_html, set_number)
        if not product_url:
            return WorldBricksScrapeResult(
                success=False,
                set_number=set_number,
                error=f"Set {set_number} not found in WorldBricks search results",
            )

        # Rate limit delay between requests
        await asyncio.sleep(get_random_delay())

        # Step 3: Fetch product page
        product_html = await _fetch_page(client, product_url)

        # Validate page
        if not is_valid_worldbricks_page(product_html):
            return WorldBricksScrapeResult(
                success=False,
                set_number=set_number,
                error="Page does not appear to be a valid WorldBricks product page",
            )

        # Step 4: Parse the page
        data = parse_worldbricks_page(product_html, set_number)

        # Step 5: Save to database if requested
        if save:
            upsert_set(conn, data)

        return WorldBricksScrapeResult(
            success=True,
            set_number=set_number,
            data=data,
        )

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return WorldBricksScrapeResult(
            success=False,
            set_number=set_number,
            error=error_msg,
        )
    except httpx.RequestError as e:
        return WorldBricksScrapeResult(
            success=False,
            set_number=set_number,
            error=f"Request error: {e}",
        )
    except ValueError as e:
        return WorldBricksScrapeResult(
            success=False,
            set_number=set_number,
            error=str(e),
        )
    except (TimeoutError, OSError) as e:
        return WorldBricksScrapeResult(
            success=False,
            set_number=set_number,
            error=f"Network error: {e}",
        )
    finally:
        if should_close_client:
            await client.aclose()


async def scrape_batch(
    conn: "DuckDBPyConnection",
    set_numbers: list[str],
    *,
    save: bool = True,
    progress_callback: ("callable[[int, int, WorldBricksScrapeResult], None] | None") = None,
) -> list[WorldBricksScrapeResult]:
    """Scrape multiple sets from WorldBricks with rate limiting.

    Args:
        conn: DuckDB connection
        set_numbers: List of LEGO set numbers to scrape
        save: Whether to save results to database
        progress_callback: Optional callback(current, total, result)

    Returns:
        List of WorldBricksScrapeResult objects
    """
    results: list[WorldBricksScrapeResult] = []
    total = len(set_numbers)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, set_number in enumerate(set_numbers):
            result = await scrape_set(
                conn,
                set_number,
                save=save,
                client=client,
            )
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total, result)

            # Rate limit delay between items (skip for last item)
            if i < total - 1:
                delay = get_random_delay() * 2  # Extra delay for WorldBricks
                await asyncio.sleep(delay)

    return results


def scrape_set_sync(
    conn: "DuckDBPyConnection",
    set_number: str,
    *,
    save: bool = True,
) -> WorldBricksScrapeResult:
    """Synchronous wrapper for scrape_set.

    Args:
        conn: DuckDB connection
        set_number: LEGO set number
        save: Whether to save results to database

    Returns:
        WorldBricksScrapeResult with data or error
    """
    return asyncio.run(scrape_set(conn, set_number, save=save))


def scrape_batch_sync(
    conn: "DuckDBPyConnection",
    set_numbers: list[str],
    *,
    save: bool = True,
    progress_callback: ("callable[[int, int, WorldBricksScrapeResult], None] | None") = None,
) -> list[WorldBricksScrapeResult]:
    """Synchronous wrapper for scrape_batch.

    Args:
        conn: DuckDB connection
        set_numbers: List of LEGO set numbers to scrape
        save: Whether to save results to database
        progress_callback: Optional callback(current, total, result)

    Returns:
        List of WorldBricksScrapeResult objects
    """
    return asyncio.run(
        scrape_batch(conn, set_numbers, save=save, progress_callback=progress_callback)
    )
