"""Test script for HobbyDigi scraper -- direct Python, no API."""

import asyncio
import sys

sys.path.insert(0, ".")

from services.hobbydigi.scraper import scrape_all_lego


def on_progress(msg: str) -> None:
    print(f"  [progress] {msg}")


async def main() -> None:
    print("Starting HobbyDigi scrape (no DB, dry run)...")
    result = await scrape_all_lego(conn=None, on_progress=on_progress)

    print(f"\nSuccess: {result.success}")
    print(f"Total listed: {result.total_listed}")
    print(f"Pages fetched: {result.pages_fetched}")
    print(f"Products scraped: {len(result.products)}")

    if result.error:
        print(f"Error: {result.error}")

    if result.products:
        print("\nFirst 5 products:")
        for p in result.products[:5]:
            special = f" (was RM {p.original_price_myr})" if p.original_price_myr else ""
            tags = f" [{', '.join(p.tags)}]" if p.tags else ""
            stock = "In Stock" if p.available else "OUT OF STOCK"
            print(
                f"  [{p.product_id}] {p.name}\n"
                f"    RM {p.price_myr}{special} -- {stock}{tags}"
            )

        # Stats
        available = sum(1 for p in result.products if p.available)
        special = sum(1 for p in result.products if p.is_special_price)
        with_tags = sum(1 for p in result.products if p.tags)
        retired = sum(1 for p in result.products if "Retired" in p.tags)
        free_ship = sum(1 for p in result.products if "Free Shipping" in p.tags)
        new_tag = sum(1 for p in result.products if "New" in p.tags)

        print(f"\nStats:")
        print(f"  Available: {available}/{len(result.products)}")
        print(f"  Special price: {special}/{len(result.products)}")
        print(f"  With tags: {with_tags}/{len(result.products)}")
        print(f"  Retired: {retired}")
        print(f"  Free Shipping: {free_ship}")
        print(f"  New: {new_tag}")


if __name__ == "__main__":
    asyncio.run(main())
