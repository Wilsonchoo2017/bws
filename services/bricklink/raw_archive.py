"""Append-only raw DOM archive for BrickLink scrapes.

Every page the browser scraper fetches is stored here as a gzip-compressed
HTML file so we can retro-actively debug parser drift.  No pruning -- disk
usage is the tradeoff for having every raw page available.

Files are written flat under ``logs/bricklink_raw/`` with the naming
convention::

    {item_id}_{YYYYMMDDTHHMMSS}_{kind}.html.gz

where ``kind`` is one of ``v2`` (v2 catalog page) or ``pg`` (legacy
catalogPG.asp price guide page).
"""

from __future__ import annotations

import gzip
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("bws.bricklink.raw_archive")

RAW_DIR = Path("logs/bricklink_raw")


def save_raw_html(
    item_id: str,
    kind: str,
    html: str,
    *,
    timestamp: datetime | None = None,
) -> Path | None:
    """Persist raw HTML gzipped.  Returns the archive path (or None on IO error).

    Args:
        item_id: BrickLink item id (e.g. "10857-1"); used in filename.
        kind: Short label for the page type ("v2", "pg", "inv", ...).
        html: Raw HTML text.
        timestamp: Optional override for the filename timestamp.
    """
    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        ts = (timestamp or datetime.now()).strftime("%Y%m%dT%H%M%S")
        safe_kind = "".join(c for c in kind if c.isalnum() or c in "-_") or "page"
        path = RAW_DIR / f"{item_id}_{ts}_{safe_kind}.html.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)
        logger.debug(
            "Archived raw HTML: %s (%d bytes raw, %d bytes on disk)",
            path,
            len(html),
            path.stat().st_size,
        )
        return path
    except OSError as exc:
        logger.warning("Failed to archive raw HTML for %s (%s): %s", item_id, kind, exc)
        return None
