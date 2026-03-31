"""BrickEconomy scraper service -- set valuation data and price history."""

from services.brickeconomy.parser import BrickeconomySnapshot, parse_brickeconomy_page
from services.brickeconomy.repository import (
    get_latest_snapshot,
    get_snapshots,
    record_current_value,
    save_snapshot,
)
from services.brickeconomy.scraper import (
    BrickeconomyScrapeResult,
    scrape_batch,
    scrape_batch_sync,
    scrape_set,
    scrape_set_sync,
)

__all__ = [
    "BrickeconomySnapshot",
    "BrickeconomyScrapeResult",
    "parse_brickeconomy_page",
    "scrape_set",
    "scrape_set_sync",
    "scrape_batch",
    "scrape_batch_sync",
    "save_snapshot",
    "record_current_value",
    "get_latest_snapshot",
    "get_snapshots",
]
