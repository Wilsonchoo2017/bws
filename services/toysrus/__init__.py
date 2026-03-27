"""ToysRUs Malaysia LEGO scraper.

HTTP-based scraper for toysrus.com.my LEGO catalog.
Uses Demandware Search-ShowAjax endpoint for pagination.
"""

from services.toysrus.parser import ToysRUsProduct
from services.toysrus.scraper import ScrapeResult, scrape_all_lego, scrape_all_lego_sync

__all__ = [
    "ScrapeResult",
    "ToysRUsProduct",
    "scrape_all_lego",
    "scrape_all_lego_sync",
]
