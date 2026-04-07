"""Bootstrap the backtest universe with metadata and price data.

Usage:
    python -m services.backtesting.bootstrap metadata   # Scrape Brickset for metadata
    python -m services.backtesting.bootstrap check       # Check current coverage
"""

import sys
from typing import Any


def check_coverage(conn: Any) -> None:
    """Print current data coverage for the backtest universe."""
    from config.backtest_universe import BACKTEST_SETS

    total = len(BACKTEST_SETS)
    print(f"\nBacktest universe: {total} sets")

    # Check lego_items metadata
    placeholders = ",".join(["?"] * total)
    result = conn.execute(
        f"""
        SELECT
            COUNT(*) as total_found,
            COUNT(year_retired) as has_year_retired,
            COUNT(rrp_cents) as has_rrp,
            COUNT(theme) as has_theme,
            COUNT(parts_count) as has_parts
        FROM lego_items
        WHERE set_number IN ({placeholders})
        """,
        list(BACKTEST_SETS),
    ).fetchone()

    found, has_retired, has_rrp, has_theme, has_parts = result
    print(f"\nMetadata coverage ({found}/{total} sets in lego_items):")
    print(f"  year_retired:  {has_retired:4d}/{total} ({has_retired/total*100:.0f}%)")
    print(f"  rrp_cents:     {has_rrp:4d}/{total} ({has_rrp/total*100:.0f}%)")
    print(f"  theme:         {has_theme:4d}/{total} ({has_theme/total*100:.0f}%)")
    print(f"  parts_count:   {has_parts:4d}/{total} ({has_parts/total*100:.0f}%)")

    # Check monthly sales data
    bl_ids = [f"{s}-1" for s in BACKTEST_SETS]
    placeholders_bl = ",".join(["?"] * len(bl_ids))
    sales_result = conn.execute(
        f"""
        SELECT
            COUNT(DISTINCT item_id) as items_with_sales,
            COUNT(*) as total_rows,
            COUNT(DISTINCT item_id) FILTER (
                WHERE item_id IN (
                    SELECT item_id FROM bricklink_monthly_sales
                    WHERE item_id IN ({placeholders_bl})
                    GROUP BY item_id HAVING COUNT(*) >= 6
                )
            ) as items_6plus,
            COUNT(DISTINCT item_id) FILTER (
                WHERE item_id IN (
                    SELECT item_id FROM bricklink_monthly_sales
                    WHERE item_id IN ({placeholders_bl})
                    GROUP BY item_id HAVING COUNT(*) >= 12
                )
            ) as items_12plus,
            COUNT(DISTINCT item_id) FILTER (
                WHERE item_id IN (
                    SELECT item_id FROM bricklink_monthly_sales
                    WHERE item_id IN ({placeholders_bl})
                    GROUP BY item_id HAVING COUNT(*) >= 24
                )
            ) as items_24plus
        FROM bricklink_monthly_sales
        WHERE item_id IN ({placeholders_bl})
        """,
        bl_ids + bl_ids + bl_ids + bl_ids,
    ).fetchone()

    items_sales, total_rows, items_6, items_12, items_24 = sales_result
    print(f"\nSales data coverage ({items_sales}/{total} sets have sales data):")
    print(f"  Total rows:    {total_rows}")
    print(f"  6+ months:     {items_6}")
    print(f"  12+ months:    {items_12}")
    print(f"  24+ months:    {items_24}")


def bootstrap_metadata(
    conn: Any,
    *,
    headless: bool = True,
    limit: int | None = None,
) -> None:
    """Scrape Brickset for metadata and populate lego_items.

    Only scrapes sets that are missing year_retired or rrp_cents.
    """
    from config.backtest_universe import BACKTEST_SETS
    from services.brickset.scraper import scrape_batch_sync
    from services.items.repository import get_or_create_item

    # Find sets that need metadata
    sets_needing_metadata = _find_sets_needing_metadata(conn, BACKTEST_SETS)

    if not sets_needing_metadata:
        print("All sets already have metadata. Nothing to do.")
        return

    if limit is not None:
        sets_needing_metadata = sets_needing_metadata[:limit]

    print(f"Scraping metadata for {len(sets_needing_metadata)} sets from Brickset...")

    def on_progress(current: int, total: int, result: object) -> None:
        status = "OK" if result.success else f"FAIL: {result.error}"
        data = result.data
        if data:
            extras = []
            if data.rrp_usd_cents:
                extras.append(f"RRP=${data.rrp_usd_cents/100:.0f}")
            if data.year_retired:
                extras.append(f"retired={data.year_retired}")
            if data.theme:
                extras.append(f"theme={data.theme}")
            extra_str = f" [{', '.join(extras)}]" if extras else ""
            print(f"  [{current}/{total}] {result.set_number}: {status}{extra_str}")
        else:
            print(f"  [{current}/{total}] {result.set_number}: {status}")

    results = scrape_batch_sync(
        sets_needing_metadata,
        headless=headless,
        progress_callback=on_progress,
    )

    # Store results
    stored = 0
    for result in results:
        if not result.success or result.data is None:
            continue

        data = result.data
        # Convert USD RRP to cents (already in cents from parser)
        rrp_cents = data.rrp_usd_cents
        rrp_currency = "USD" if rrp_cents else None

        get_or_create_item(
            conn,
            data.set_number,
            title=data.title,
            theme=data.theme or data.subtheme,
            year_released=data.year_released,
            year_retired=data.year_retired,
            parts_count=data.pieces,
            image_url=data.image_url,
            rrp_cents=rrp_cents,
            rrp_currency=rrp_currency,
        )
        stored += 1

    print(f"\nStored metadata for {stored}/{len(results)} sets.")


def _find_sets_needing_metadata(
    conn: Any,
    all_sets: tuple[str, ...],
) -> list[str]:
    """Find sets missing year_retired or rrp_cents in lego_items."""
    placeholders = ",".join(["?"] * len(all_sets))

    # Get sets that already have complete metadata
    complete = conn.execute(
        f"""
        SELECT set_number
        FROM lego_items
        WHERE set_number IN ({placeholders})
          AND year_retired IS NOT NULL
          AND rrp_cents IS NOT NULL
        """,
        list(all_sets),
    ).fetchall()
    complete_set = {row[0] for row in complete}

    return [s for s in all_sets if s not in complete_set]


def main() -> None:
    """CLI entry point."""
    from db.connection import get_connection

    if len(sys.argv) < 2:
        print("Usage: python -m services.backtesting.bootstrap <command>")
        print()
        print("Commands:")
        print("  metadata   Scrape Brickset for year_retired, RRP, theme, pieces")
        print("  check      Check current data coverage for backtest universe")
        print()
        print("Options:")
        print("  --visible  Show browser window (default: headless)")
        print("  --limit N  Only scrape first N sets")
        sys.exit(1)

    command = sys.argv[1]
    headless = "--visible" not in sys.argv
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    conn = get_connection()

    if command == "check":
        check_coverage(conn)
    elif command == "metadata":
        bootstrap_metadata(conn, headless=headless, limit=limit)
        print()
        check_coverage(conn)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
