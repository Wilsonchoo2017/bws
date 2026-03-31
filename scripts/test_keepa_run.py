"""Test run of the Keepa scraper."""

import asyncio
import sys
import logging

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(levelname)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

from services.keepa.scraper import scrape_keepa


async def main():
    result = await scrape_keepa("60305", headless=False)
    print("---")
    print(f"Success: {result.success}")
    print(f"Error: {result.error}")
    if result.product_data:
        d = result.product_data
        print(f"ASIN: {d.asin}")
        print(f"Title: {d.title}")
        print(f"URL: {d.keepa_url}")
        print(f"Buy Box: {d.current_buy_box_cents} cents")
        print(f"Amazon: {d.current_amazon_cents} cents")
        print(f"New: {d.current_new_cents} cents")
        print(f"Lowest: {d.lowest_ever_cents} cents")
        print(f"Highest: {d.highest_ever_cents} cents")
        print(f"Amazon price points: {len(d.amazon_price)}")
        print(f"New price points: {len(d.new_price)}")
        print(f"Buy Box points: {len(d.buy_box)}")
        print(f"Sales Rank points: {len(d.sales_rank)}")
        print(f"3P FBA points: {len(d.new_3p_fba)}")
        print(f"3P FBM points: {len(d.new_3p_fbm)}")
        print(f"Used points: {len(d.used_price)}")
        print(f"Warehouse Deals: {len(d.warehouse_deals)}")
        print(f"List Price: {len(d.list_price)}")
        print(f"Collectible: {len(d.collectible)}")

        # Show sample data points
        for name, series in [
            ("Amazon", d.amazon_price),
            ("New", d.new_price),
            ("Buy Box", d.buy_box),
            ("3P FBA", d.new_3p_fba),
            ("3P FBM", d.new_3p_fbm),
        ]:
            if series:
                print(f"\n  {name} ({len(series)} pts):")
                for p in series[:8]:
                    print(f"    {p.date}: ${p.value / 100:.2f}")
                if len(series) > 8:
                    print(f"    ... and {len(series) - 8} more")


asyncio.run(main())
