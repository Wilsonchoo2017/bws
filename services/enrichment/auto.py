"""Auto-enrichment helpers -- create persistent scrape tasks for discovered sets."""

import logging

from api.jobs import JobManager

logger = logging.getLogger("bws.enrichment.auto")


def queue_enrichment_if_needed(
    manager: JobManager,
    set_number: str,
) -> bool:
    """Create scrape tasks for a set if none are already active.

    Returns True if tasks were created, False if skipped (already active).
    The ``manager`` parameter is kept for API compatibility but is no longer
    used -- tasks go directly to the persistent database queue.
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.scrape_queue.repository import create_tasks_for_set

    conn = get_connection()
    try:
        init_schema(conn)
        tasks = create_tasks_for_set(conn, set_number, reason="auto: new item")
    finally:
        conn.close()

    if tasks:
        logger.info("Auto-created %d scrape tasks for %s", len(tasks), set_number)
        return True
    return False


def queue_enrichment_batch(
    manager: JobManager,
    set_numbers: list[str],
) -> int:
    """Create scrape tasks for multiple sets (dedup handled by repository).

    Returns count of sets that had tasks created.
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.scrape_queue.repository import create_tasks_for_set

    conn = get_connection()
    try:
        init_schema(conn)
        queued = 0
        for sn in set_numbers:
            tasks = create_tasks_for_set(conn, sn, reason="auto: new item batch")
            if tasks:
                queued += 1
    finally:
        conn.close()

    if queued > 0:
        logger.info("Auto-created scrape tasks for %d sets", queued)

    return queued
