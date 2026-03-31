"""Shared post-scrape helpers used by multiple source workers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.jobs import JobManager

logger = logging.getLogger("bws.worker")


def queue_enrichment_for_scraped_items(
    manager: JobManager,
    items: list[dict],
) -> None:
    """Extract set numbers from scraped items and queue enrichment jobs."""
    from services.enrichment.auto import queue_enrichment_batch
    from services.items.set_number import extract_set_number

    set_numbers: list[str] = []
    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        sn = extract_set_number(title)
        if sn:
            set_numbers.append(sn)

    if set_numbers:
        queued = queue_enrichment_batch(manager, set_numbers)
        if queued > 0:
            logger.info(
                "Post-scrape: queued enrichment for %d/%d sets",
                queued,
                len(set_numbers),
            )


def queue_enrichment_for_catalog_items(
    manager: JobManager,
    set_numbers: list[str],
) -> None:
    """Queue enrichment jobs for newly discovered catalog items."""
    from services.enrichment.auto import queue_enrichment_batch

    if not set_numbers:
        return

    queued = queue_enrichment_batch(manager, set_numbers)
    if queued > 0:
        logger.info(
            "Post-catalog: queued enrichment for %d/%d sets",
            queued,
            len(set_numbers),
        )


async def check_deal_signals() -> None:
    """Run signal check and send Ntfy notifications for strong deals."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.notifications.deal_notifier import check_and_notify

    try:
        conn = get_connection()
        init_schema(conn)
        try:
            sent = await asyncio.to_thread(check_and_notify, conn)
            if sent:
                logger.info("Deal check: sent %d notifications", sent)
        finally:
            conn.close()
    except Exception:
        logger.exception("Deal signal check failed")
