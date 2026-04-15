"""Periodic Carousell competition sweep.

Thin wrapper over the shared marketplace sweep loop in
`services.marketplace_competition.sweep_scheduler`. Carousell uses a
smaller batch than Shopee because the scraper is slower and
Cloudflare-gated.
"""

from __future__ import annotations

import logging

from api.jobs import JobManager
from services.marketplace_competition.sweep_scheduler import (
    run_marketplace_competition_sweep,
)

logger = logging.getLogger("bws.carousell.competition.scheduler")

DEFAULT_INTERVAL_MINUTES = 720  # 12 hours
DEFAULT_BATCH_SIZE = 12


async def run_competition_sweep(
    manager: JobManager,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    await run_marketplace_competition_sweep(
        manager,
        scraper_id="carousell_competition",
        snapshots_table="carousell_competition_snapshots",
        logger=logger,
        interval_minutes=interval_minutes,
        batch_size=batch_size,
    )
