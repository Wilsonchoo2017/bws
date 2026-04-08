"""Check out-of-stock detection and additional metadata on hobbydigi."""

import asyncio
import json

from services.browser.helpers import stealth_browser, new_page, human_delay


async def main() -> None:
    async with stealth_browser(headless=False, profile_name="hobbydigi") as browser:
        page = await new_page(browser)

        # Go to a page that likely has out-of-stock items (later pages)
        url = "https://www.hobbydigi.com/my/lego?p=30&product_list_limit=80"
        print(f"Navigating to {url} ...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await human_delay(3000, 5000)

        # Check all product items for stock status and additional metadata
        result = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('li.product-item');
                const results = [];
                for (const el of items) {
                    const name = el.querySelector('.product-item-link');
                    const stockEl = el.querySelector('.stock');
                    const stockUnavail = el.querySelector('.stock.unavailable');
                    const addToCart = el.querySelector('.action.tocart');
                    const outOfStock = el.querySelector('[title="Out of stock"]');

                    // Check for any badges/tags
                    const tags = el.querySelectorAll('.product_tag');
                    const tagTexts = [];
                    tags.forEach(t => tagTexts.push(t.textContent.trim()));

                    // Check for review count
                    const reviewEl = el.querySelector('.reviews-actions');
                    const reviewText = reviewEl ? reviewEl.textContent.trim() : null;

                    results.push({
                        name: name ? name.textContent.trim().substring(0, 60) : '',
                        stock_text: stockEl ? stockEl.textContent.trim() : null,
                        stock_class: stockEl ? stockEl.className : null,
                        has_unavail: stockUnavail !== null,
                        has_add_to_cart: addToCart !== null,
                        has_out_of_stock: outOfStock !== null,
                        tags: tagTexts,
                        review: reviewText,
                    });
                }
                return results;
            }
        """)

        print(f"\nProducts on page: {len(result)}")
        for i, p in enumerate(result[:20]):
            stock_status = "OUT OF STOCK" if (p['has_unavail'] or p['has_out_of_stock']) else "IN STOCK"
            tags = ', '.join(p['tags']) if p['tags'] else ''
            print(f"  {i+1}. {p['name'][:50]} -- {stock_status} -- stock_text={p['stock_text']} -- tags=[{tags}]")

        # Count stock statuses
        out_of_stock = sum(1 for p in result if p['has_unavail'] or p['has_out_of_stock'])
        print(f"\nIn stock: {len(result) - out_of_stock}, Out of stock: {out_of_stock}")

        # Also check full product HTML for one out-of-stock item if any
        oos = [p for p in result if p['has_unavail'] or p['has_out_of_stock']]
        if oos:
            print(f"\nFirst OOS item: {oos[0]['name']}")
            print(f"  stock_class: {oos[0]['stock_class']}")

        print("\nDone.")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
