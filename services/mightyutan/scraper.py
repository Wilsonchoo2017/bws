"""Mighty Utan LEGO catalog scraper.

HTTP-based scraper that paginates through the mightyutan.com.my
LEGO collection. Uses direct httpx requests with browser-like headers
to extract product data from the Next.js RSC payload.
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from config.settings import get_random_delay
from services.http import get_browser_headers
from services.mightyutan.parser import MightyUtanProduct, parse_page
from services.mightyutan.repository import upsert_products
from typing import Any



logger = logging.getLogger(__name__)

_BASE_URL = "https://mightyutan.com.my"
_COLLECTION_URL = f"{_BASE_URL}/collection/lego-1"
_PAGE_SIZE = 100


@dataclass(frozen=True)
class ScrapeResult:
    """Result of scraping the full LEGO catalog."""

    success: bool
    products: tuple[MightyUtanProduct, ...] = ()
    total_listed: int = 0
    pages_fetched: int = 0
    saved_count: int = 0
    error: str | None = None


def _get_headers() -> dict[str, str]:
    return get_browser_headers(referer=f"{_BASE_URL}/")


async def _fetch_page(client: httpx.AsyncClient, page: int) -> str:
    """Fetch one page of the LEGO collection."""
    params = {"page": page, "limit": _PAGE_SIZE}
    response = await client.get(
        _COLLECTION_URL, params=params, headers=_get_headers(), follow_redirects=True
    )
    response.raise_for_status()
    return response.text


async def scrape_all_lego(
    conn: Any | None = None,
) -> ScrapeResult:
    """Scrape all LEGO products from Mighty Utan Malaysia.

    Paginates through the entire collection, extracting product data
    from the embedded Next.js RSC payload on each page.

    Args:
        conn: Database connection. If provided, saves products to DB.
    """
    all_products: list[MightyUtanProduct] = []
    pages_fetched = 0
    total_listed = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            html = await _fetch_page(client, page=1)
            pages_fetched += 1

            products, pagination = parse_page(html)
            if pagination is None:
                return ScrapeResult(
                    success=False,
                    error="Failed to extract pagination data from page 1",
                )

            total_listed = pagination.total
            last_page = pagination.last_page
            all_products.extend(products)

            logger.info(
                "Page 1: %d products, %d total listed, %d pages",
                len(products),
                total_listed,
                last_page,
            )

            for page_num in range(2, last_page + 1):
                delay = get_random_delay(min_ms=2_000, max_ms=5_000)
                await asyncio.sleep(delay)

                html = await _fetch_page(client, page=page_num)
                pages_fetched += 1

                products, _ = parse_page(html)
                if not products:
                    logger.info("Page %d: no products, stopping", page_num)
                    break

                all_products.extend(products)

                logger.info(
                    "Page %d: %d products (%d cumulative)",
                    page_num,
                    len(products),
                    len(all_products),
                )

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
    conn: Any | None = None,
) -> ScrapeResult:
    """Synchronous wrapper for scrape_all_lego."""
    return asyncio.run(scrape_all_lego(conn=conn))
