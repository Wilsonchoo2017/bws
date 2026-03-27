"""BrickRanker scraper service.

Scrapes LEGO retirement data from BrickRanker.com retirement tracker, including:
- Retirement predictions
- "Retiring Soon" status
- Expected retirement dates
- Theme information
"""

from bws.services.brickranker.parser import (
    BrickRankerParseResult,
    RetirementItem,
    parse_retirement_tracker_page,
)
from bws.services.brickranker.repository import (
    batch_upsert_items,
    get_item,
    get_retiring_soon_items,
    list_items,
    upsert_item,
)
from bws.services.brickranker.scraper import (
    BrickRankerScrapeResult,
    scrape_retirement_tracker,
    scrape_retirement_tracker_sync,
)


__all__ = [
    "BrickRankerParseResult",
    "BrickRankerScrapeResult",
    "RetirementItem",
    "batch_upsert_items",
    "get_item",
    "get_retiring_soon_items",
    "list_items",
    "parse_retirement_tracker_page",
    "scrape_retirement_tracker",
    "scrape_retirement_tracker_sync",
    "upsert_item",
]
