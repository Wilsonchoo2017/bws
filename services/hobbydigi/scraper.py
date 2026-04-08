"""HobbyDigi LEGO catalog scraper.

Browser-based scraper that paginates through hobbydigi.com/my/lego
using Camoufox for anti-detection. Extracts product data from the
Magento DOM via Playwright page.evaluate().
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.browser.helpers import human_delay, new_page, stealth_browser
from services.hobbydigi.parser import (
    EXTRACT_PAGINATION_JS,
    EXTRACT_PRODUCTS_JS,
    HobbyDigiProduct,
    parse_raw_pagination,
    parse_raw_products,
)
from services.hobbydigi.repository import upsert_products

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.hobbydigi.com/my/lego"
_PAGE_SIZE = 80  # Magento supports 28, 40, 80 -- use largest


@dataclass(frozen=True)
class ScrapeResult:
    """Result of scraping the full LEGO catalog."""

    success: bool
    products: tuple[HobbyDigiProduct, ...] = ()
    total_listed: int = 0
    pages_fetched: int = 0
    saved_count: int = 0
    error: str | None = None


async def scrape_all_lego(
    conn: Any | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ScrapeResult:
    """Scrape all LEGO products from HobbyDigi Malaysia.

    Uses Camoufox browser to paginate through the Magento catalog,
    extracting product data from the rendered DOM.
    """
    all_products: list[HobbyDigiProduct] = []
    pages_fetched = 0
    total_listed = 0

    try:
        async with stealth_browser(
            headless=True, profile_name="hobbydigi"
        ) as browser:
            page = await new_page(browser)

            # Page 1
            url = f"{_BASE_URL}?product_list_limit={_PAGE_SIZE}"
            if on_progress:
                on_progress("Loading page 1...")

            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await human_delay(2000, 4000)
            pages_fetched += 1

            raw_products = await page.evaluate(EXTRACT_PRODUCTS_JS)
            raw_pagination = await page.evaluate(EXTRACT_PAGINATION_JS)

            products = parse_raw_products(raw_products)
            pagination = parse_raw_pagination(raw_pagination)

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
            if on_progress:
                on_progress(
                    f"Page 1/{last_page} -- {len(all_products)} products"
                )

            # Remaining pages
            for page_num in range(2, last_page + 1):
                await human_delay(2000, 5000)

                if on_progress:
                    on_progress(f"Loading page {page_num}/{last_page}...")

                page_url = (
                    f"{_BASE_URL}?p={page_num}"
                    f"&product_list_limit={_PAGE_SIZE}"
                )
                await page.goto(
                    page_url, wait_until="domcontentloaded", timeout=60_000
                )
                await human_delay(1500, 3000)
                pages_fetched += 1

                raw_products = await page.evaluate(EXTRACT_PRODUCTS_JS)
                products = parse_raw_products(raw_products)

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
                if on_progress:
                    on_progress(
                        f"Page {page_num}/{last_page} -- "
                        f"{len(all_products)} products"
                    )

    except Exception as e:
        logger.error("HobbyDigi scrape failed: %s", e, exc_info=True)
        return ScrapeResult(
            success=False,
            products=tuple(all_products),
            total_listed=total_listed,
            pages_fetched=pages_fetched,
            error=str(e),
        )

    products_tuple = tuple(all_products)
    saved_count = 0

    if conn is not None and products_tuple:
        if on_progress:
            on_progress(f"Saving {len(products_tuple)} products to database...")
        saved_count = upsert_products(conn, products_tuple)
        logger.info("Saved %d products to database", saved_count)

    return ScrapeResult(
        success=True,
        products=products_tuple,
        total_listed=total_listed,
        pages_fetched=pages_fetched,
        saved_count=saved_count,
    )
