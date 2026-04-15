"""Periodic Shopee competition sweep.

Thin wrapper over the shared marketplace sweep loop in
`services.marketplace_competition.sweep_scheduler`.
"""

from __future__ import annotations

import logging

from api.jobs import JobManager
from services.marketplace_competition.sweep_scheduler import (
    run_marketplace_competition_sweep,
)

logger = logging.getLogger("bws.shopee.competition.scheduler")

DEFAULT_INTERVAL_MINUTES = 720  # 12 hours
DEFAULT_BATCH_SIZE = 20


async def run_competition_sweep(
    manager: JobManager,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    await run_marketplace_competition_sweep(
        manager,
        scraper_id="shopee_competition",
        snapshots_table="shopee_competition_snapshots",
        logger=logger,
        interval_minutes=interval_minutes,
        batch_size=batch_size,
    )
