"""WorldBricks scraper service.

Scrapes LEGO set metadata from WorldBricks.com, including:
- Year released (HIGH PRIORITY)
- Year retired (HIGH PRIORITY)
- Parts count
- Dimensions
"""

from bws.services.worldbricks.parser import (
    WorldBricksData,
    construct_search_url,
    extract_parts_count,
    extract_year_released,
    extract_year_retired,
    parse_search_results,
    parse_worldbricks_page,
)
from bws.services.worldbricks.repository import (
    get_set,
    get_sets_needing_scraping,
    list_sets,
    upsert_set,
)
from bws.services.worldbricks.scraper import (
    WorldBricksScrapeResult,
    scrape_set,
    scrape_set_sync,
)


__all__ = [
    "WorldBricksData",
    "WorldBricksScrapeResult",
    "construct_search_url",
    "extract_parts_count",
    "extract_year_released",
    "extract_year_retired",
    "get_set",
    "get_sets_needing_scraping",
    "list_sets",
    "parse_search_results",
    "parse_worldbricks_page",
    "scrape_set",
    "scrape_set_sync",
    "upsert_set",
]
