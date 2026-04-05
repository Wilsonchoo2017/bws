"""
17 - Enqueue theme-level Google Trends tasks into the scrape queue.

Queries distinct themes with >= 3 retired sets from the training data
and creates GOOGLE_TRENDS_THEME tasks for each. The dispatcher will
pick them up and process them via the theme GT executor.

Run with: python research/17_enqueue_theme_gt.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from db.schema import init_schema
from services.scrape_queue.models import TaskType
from services.scrape_queue.repository import create_task


def main() -> None:
    conn = get_connection()
    init_schema(conn)

    # Get themes with sufficient training data
    themes = conn.execute("""
        SELECT
            li.theme,
            COUNT(*) AS n_sets
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
        GROUP BY li.theme
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
    """).fetchall()

    print(f"Found {len(themes)} themes with >= 3 retired sets")
    print()

    created = 0
    skipped = 0

    for theme_name, n_sets in themes:
        # set_number field stores the theme name for this task type
        task = create_task(conn, theme_name, TaskType.GOOGLE_TRENDS_THEME)
        if task:
            print(f"  Queued: {theme_name:30s} ({n_sets} sets)")
            created += 1
        else:
            print(f"  Skip:  {theme_name:30s} (already queued or recently completed)")
            skipped += 1

    print()
    print(f"Created {created} tasks, skipped {skipped}")

    conn.close()


if __name__ == "__main__":
    main()
