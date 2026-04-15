"""Backfill bricklink_items.wanted_count from archived item-page HTML.

Re-parses every `*_v2.html.gz` file in `logs/bricklink_raw/`, extracts the
"On N Wanted Lists" count using the same regex shipped with the parser, and
updates `bricklink_items` keyed by `item_id`. If multiple archives exist for
the same item, the most recent one wins.

No network calls — operates purely on local archives.
"""

from __future__ import annotations

import gzip
import logging
import re
from pathlib import Path

from sqlalchemy import text

from db.pg.engine import get_engine
from services.bricklink.parser import _extract_wanted_count

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path("logs/bricklink_raw")
FILENAME_RE = re.compile(r"^(?P<item_id>\d+-\d+)_(?P<ts>\d{8}T\d{6})_v2\.html\.gz$")


def _collect_latest_archives() -> dict[str, Path]:
    """Return {item_id: most-recent archive path} for every v2 HTML snapshot."""
    latest: dict[str, tuple[str, Path]] = {}
    for entry in ARCHIVE_DIR.iterdir():
        match = FILENAME_RE.match(entry.name)
        if not match:
            continue
        item_id = match.group("item_id")
        ts = match.group("ts")
        prev = latest.get(item_id)
        if prev is None or ts > prev[0]:
            latest[item_id] = (ts, entry)
    return {iid: path for iid, (_, path) in latest.items()}


def _parse_wanted(path: Path) -> int | None:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    return _extract_wanted_count(html)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not ARCHIVE_DIR.is_dir():
        logger.error("archive directory not found: %s", ARCHIVE_DIR)
        return

    latest = _collect_latest_archives()
    logger.info("found %d unique item archives", len(latest))

    rows: list[tuple[str, int]] = []
    missing = 0
    for item_id, path in latest.items():
        wanted = _parse_wanted(path)
        if wanted is None:
            missing += 1
            continue
        rows.append((item_id, wanted))

    logger.info("parsed %d wanted counts, %d had no marker", len(rows), missing)

    if not rows:
        return

    engine = get_engine()
    update_stmt = text(
        "UPDATE bricklink_items "
        "SET wanted_count = :wanted, updated_at = CURRENT_TIMESTAMP "
        "WHERE item_id = :item_id"
    )

    with engine.begin() as conn:
        updated = 0
        skipped = 0
        for item_id, wanted in rows:
            result = conn.execute(update_stmt, {"wanted": wanted, "item_id": item_id})
            if result.rowcount:
                updated += result.rowcount
            else:
                skipped += 1

    logger.info("updated %d bricklink_items rows (no match: %d)", updated, skipped)


if __name__ == "__main__":
    main()
