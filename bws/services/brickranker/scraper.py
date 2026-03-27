"""BrickRanker scraper orchestration.

Coordinates fetching HTML and parsing data from BrickRanker.com retirement tracker.
"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from bws.config.settings import get_random_user_agent
from bws.services.brickranker.parser import (
    BRICKRANKER_URL,
    BrickRankerParseResult,
    is_valid_brickranker_url,
    parse_retirement_tracker_page,
)
from bws.services.brickranker.repository import batch_upsert_items


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


@dataclass(frozen=True)
class BrickRankerScrapeResult:
    """Result of a BrickRanker scrape operation."""

    success: bool
    data: BrickRankerParseResult | None = None
    stats: dict[str, int] | None = None
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


async def scrape_retirement_tracker(
    conn: "DuckDBPyConnection",
    *,
    url: str = BRICKRANKER_URL,
    save: bool = True,
    client: httpx.AsyncClient | None = None,
) -> BrickRankerScrapeResult:
    """Scrape the BrickRanker retirement tracker page.

    This is a full-page scrape that fetches all retirement items at once.

    Args:
        conn: DuckDB connection
        url: BrickRanker retirement tracker URL
        save: Whether to save results to database
        client: Optional HTTP client (creates one if not provided)

    Returns:
        BrickRankerScrapeResult with data or error
    """
    # Validate URL
    if not is_valid_brickranker_url(url):
        return BrickRankerScrapeResult(
            success=False,
            error=f"Invalid BrickRanker URL: {url}",
        )

    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        # Fetch the retirement tracker page
        response = await client.get(
            url,
            headers=_get_headers(),
            follow_redirects=True,
        )
        response.raise_for_status()

        html = response.text

        # Parse the page
        data = parse_retirement_tracker_page(html)

        # Save to database if requested
        stats = None
        if save:
            stats = batch_upsert_items(conn, list(data.items))

        return BrickRankerScrapeResult(
            success=True,
            data=data,
            stats=stats,
        )

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return BrickRankerScrapeResult(
            success=False,
            error=error_msg,
        )
    except httpx.RequestError as e:
        return BrickRankerScrapeResult(
            success=False,
            error=f"Request error: {e}",
        )
    except ValueError as e:
        return BrickRankerScrapeResult(
            success=False,
            error=str(e),
        )
    except (TimeoutError, OSError) as e:
        return BrickRankerScrapeResult(
            success=False,
            error=f"Network error: {e}",
        )
    finally:
        if should_close_client:
            await client.aclose()


def scrape_retirement_tracker_sync(
    conn: "DuckDBPyConnection",
    *,
    url: str = BRICKRANKER_URL,
    save: bool = True,
) -> BrickRankerScrapeResult:
    """Synchronous wrapper for scrape_retirement_tracker.

    Args:
        conn: DuckDB connection
        url: BrickRanker retirement tracker URL
        save: Whether to save results to database

    Returns:
        BrickRankerScrapeResult with data or error
    """
    return asyncio.run(scrape_retirement_tracker(conn, url=url, save=save))
