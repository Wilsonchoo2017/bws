"""ToysRUs LEGO catalog scraper.

HTTP-based scraper that paginates through the Demandware Search-ShowAjax
endpoint. Stops when a page contains only unavailable products.
"""


import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from config.settings import get_random_delay, get_random_user_agent, get_random_accept_language
from services.toysrus.parser import ToysRUsProduct, parse_products, parse_total_count
from services.toysrus.repository import upsert_products


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


logger = logging.getLogger(__name__)

_BASE_URL = "https://www.toysrus.com.my"
_AJAX_URL = (
    f"{_BASE_URL}/on/demandware.store/Sites-ToysRUs_MY-Site/en_MY/Search-ShowAjax"
)
_PAGE_SIZE = 48


@dataclass(frozen=True)
class ScrapeResult:
    """Result of scraping the full LEGO catalog."""

    success: bool
    products: tuple[ToysRUsProduct, ...] = ()
    total_listed: int = 0
    pages_fetched: int = 0
    saved_count: int = 0
    error: str | None = None


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": get_random_accept_language(),
        "Connection": "keep-alive",
        "Referer": f"{_BASE_URL}/lego/",
    }


async def _fetch_page(client: httpx.AsyncClient, start: int) -> str:
    """Fetch one page of LEGO products."""
    params = {"cgid": "lego", "start": start, "sz": _PAGE_SIZE}
    response = await client.get(
        _AJAX_URL, params=params, headers=_get_headers(), follow_redirects=True
    )
    response.raise_for_status()
    return response.text


async def scrape_all_lego(
    conn: "DuckDBPyConnection | None" = None,
) -> ScrapeResult:
    """Scrape all available LEGO products from ToysRUs Malaysia.

    Paginates through the catalog and stops when a page has
    all unavailable products (sorted by availability).

    Args:
        conn: DuckDB connection. If provided, saves products to DB.
    """
    all_products: list[ToysRUsProduct] = []
    pages_fetched = 0
    total_listed = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # First page to get total count
            html = await _fetch_page(client, start=0)
            pages_fetched += 1
            total_listed = parse_total_count(html)
            products = parse_products(html)

            available = tuple(p for p in products if p.available)
            all_products.extend(available)

            logger.info(
                "Page 1: %d products (%d available), %d total listed",
                len(products),
                len(available),
                total_listed,
            )

            # If first page already has all unavailable, we're done
            if not available and products:
                return ScrapeResult(
                    success=True,
                    products=tuple(all_products),
                    total_listed=total_listed,
                    pages_fetched=pages_fetched,
                )

            # Paginate until all products on a page are unavailable
            start = _PAGE_SIZE
            while start < total_listed:
                delay = get_random_delay(min_ms=2_000, max_ms=5_000)
                await asyncio.sleep(delay)

                html = await _fetch_page(client, start=start)
                pages_fetched += 1
                products = parse_products(html)

                if not products:
                    logger.info("Page %d: no products, stopping", pages_fetched)
                    break

                available = tuple(p for p in products if p.available)
                all_products.extend(available)

                logger.info(
                    "Page %d (start=%d): %d products, %d available",
                    pages_fetched,
                    start,
                    len(products),
                    len(available),
                )

                # Stop if entire page is unavailable
                if len(available) == 0:
                    logger.info("All products unavailable on page %d, stopping", pages_fetched)
                    break

                start += _PAGE_SIZE

        except httpx.HTTPStatusError as e:
            return ScrapeResult(
                success=False,
                products=tuple(all_products),
                total_listed=total_listed,
                pages_fetched=pages_fetched,
                error=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
            )
        except httpx.RequestError as e:
            return ScrapeResult(
                success=False,
                products=tuple(all_products),
                total_listed=total_listed,
                pages_fetched=pages_fetched,
                error=f"Request error: {e}",
            )

    products_tuple = tuple(all_products)
    saved_count = 0

    if conn is not None and products_tuple:
        saved_count = upsert_products(conn, products_tuple)
        logger.info("Saved %d products to database", saved_count)

    return ScrapeResult(
        success=True,
        products=products_tuple,
        total_listed=total_listed,
        pages_fetched=pages_fetched,
        saved_count=saved_count,
    )


def scrape_all_lego_sync(
    conn: "DuckDBPyConnection | None" = None,
) -> ScrapeResult:
    """Synchronous wrapper for scrape_all_lego."""
    return asyncio.run(scrape_all_lego(conn=conn))
