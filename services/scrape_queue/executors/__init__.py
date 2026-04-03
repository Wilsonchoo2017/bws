"""Scrape task executors -- one module per data source.

Importing this package triggers ``@executor`` decorator registration
for all executor modules, populating ``services.scrape_queue.registry.REGISTRY``.

Re-exports all executor functions and cooldown utilities so that
existing imports from ``services.scrape_queue.executors`` keep working.
"""

from services.scrape_queue.executors.brickeconomy import execute_brickeconomy
from services.scrape_queue.executors.bricklink import execute_bricklink_metadata
from services.scrape_queue.executors.google_trends import (
    execute_google_trends,
    get_trends_cooldown_remaining,
    get_trends_cooldown_snapshot,
    restore_trends_cooldown_snapshot,
)
from services.scrape_queue.executors.google_trends_theme import (
    execute_google_trends_theme,
)
from services.scrape_queue.executors.keepa import execute_keepa
from services.scrape_queue.executors.minifigures import execute_minifigures

__all__ = [
    "execute_brickeconomy",
    "execute_bricklink_metadata",
    "execute_google_trends",
    "execute_google_trends_theme",
    "execute_keepa",
    "execute_minifigures",
    "get_trends_cooldown_remaining",
    "get_trends_cooldown_snapshot",
    "restore_trends_cooldown_snapshot",
]
