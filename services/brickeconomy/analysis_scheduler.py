"""Periodic sweep to re-scrape BrickEconomy analysis pages.

Runs every 5 months (configurable) to keep theme/year/subtheme
aggregate growth data fresh for ML features.
"""

import asyncio
import logging

logger = logging.getLogger("bws.brickeconomy.analysis_scheduler")

# 5 months in days
DEFAULT_INTERVAL_DAYS = 150


async def run_analysis_sweep(
    *,
    interval_days: int = DEFAULT_INTERVAL_DAYS,
) -> None:
    """Periodically scrape BrickEconomy analysis pages.

    Scrapes analysis-years, analysis-themes, analysis-subthemes
    and saves parsed JSON to data/brickeconomy_analysis/.
    """
    logger.info(
        "BrickEconomy analysis sweep started (interval=%dd)", interval_days,
    )

    first_run = True
    while True:
        if first_run:
            first_run = False
            # Delay to let other sweeps start first
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(interval_days * 86400)

        try:
            from services.brickeconomy.analysis_scraper import (
                load_analysis_data,
                run_scrape_and_parse,
            )

            # Check if we already have data (skip on first startup if recent)
            existing = load_analysis_data()
            if existing and first_run:
                logger.info(
                    "Analysis data already exists (%d themes, %d years), skipping initial scrape",
                    len(existing.get("themes", [])),
                    len(existing.get("years", [])),
                )
                continue

            result = await run_scrape_and_parse(headless=True)
            for name, records in result.items():
                logger.info(
                    "Analysis sweep: scraped %d %s records", len(records), name,
                )

        except Exception:
            logger.exception("BrickEconomy analysis sweep failed")
