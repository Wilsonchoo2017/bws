"""Bricklink scraping services.

The per-item BrickLink metadata + pricing scraper runs through the
logged-in Camoufox browser pipeline in ``services.bricklink.browser_scraper``.
The legacy anonymous HTTPX entry points (``scrape_item``, ``scrape_batch``,
``ScrapeResult``) are no longer exported and should not be used for new
work.  The ``services.bricklink.scraper`` module still hosts the
minifigure inventory scraper and the catalog-list discovery scraper,
which have their own callers.
"""

from services.bricklink.browser_scraper import (
    BrowserScrapeResult,
    scrape_item_browser_sync,
)
from services.bricklink.parser import (
    build_price_guide_url,
    extract_price_box,
    parse_bricklink_url,
    parse_item_info,
    parse_monthly_sales,
    parse_price_guide,
)
from services.bricklink.repository import (
    create_price_history,
    get_item,
    get_items_for_scraping,
    insert_store_listings_snapshot,
    upsert_item,
    upsert_monthly_sales,
)


__all__ = [
    "BrowserScrapeResult",
    "build_price_guide_url",
    "create_price_history",
    "extract_price_box",
    "get_item",
    "get_items_for_scraping",
    "insert_store_listings_snapshot",
    "parse_bricklink_url",
    "parse_item_info",
    "parse_monthly_sales",
    "parse_price_guide",
    "scrape_item_browser_sync",
    "upsert_item",
    "upsert_monthly_sales",
]
