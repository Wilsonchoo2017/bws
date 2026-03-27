"""Extract product data from Shopee search results page."""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page


@dataclass(frozen=True)
class ShopeeProduct:
    """A single Shopee product listing."""

    title: str
    price_display: str
    sold_count: str | None = None
    rating: str | None = None
    shop_name: str | None = None
    product_url: str | None = None
    image_url: str | None = None


async def parse_search_results(
    page: Page,
    max_items: int = 50,
) -> tuple[ShopeeProduct, ...]:
    """Parse product cards from the current search results page.

    Shopee renders products as <a class="contents" href="...-i.xxx.yyy">
    links inside [data-sqe="item"] containers. We extract data via JS
    in the browser context.

    Args:
        page: Playwright page with search results loaded
        max_items: Maximum number of products to extract

    Returns:
        Tuple of ShopeeProduct frozen dataclasses
    """
    raw_items = await page.evaluate(
        """(maxItems) => {
            const cards = document.querySelectorAll('a[href*="-i."].contents');
            const results = [];
            for (let i = 0; i < Math.min(cards.length, maxItems); i++) {
                const card = cards[i];
                const text = card.textContent || '';
                const imgEl = card.querySelector('img');
                const href = card.getAttribute('href') || '';

                // Extract price -- look for RM followed by digits
                const priceMatch = text.match(/RM[\\d,]+\\.?\\d*/);
                const price = priceMatch ? priceMatch[0] : '';

                // Extract rating and sold count.
                // Shopee concatenates them as "{rating}{soldCount} sold"
                // e.g. "5.08 sold" = rating 5.0, sold 8
                //      "4.9563 sold" = rating 4.9, sold 563
                //      "5.01.2k sold" = rating 5.0, sold 1.2k
                // Rating is always one digit, dot, one digit (X.X)
                // Sold count follows immediately after.
                let rating = null;
                let sold = null;

                const ratingAndSoldMatch = text.match(/(\\d\\.\\d)(\\d[\\d.]*[kK]?)\\s*sold/);
                if (ratingAndSoldMatch) {
                    rating = ratingAndSoldMatch[1];
                    sold = ratingAndSoldMatch[2] + ' sold';
                } else {
                    // Fallback: just a sold count without rating
                    const soldOnlyMatch = text.match(/(\\d[\\d,.]*[kK]?)\\s*sold/);
                    if (soldOnlyMatch) {
                        sold = soldOnlyMatch[1] + ' sold';
                    }
                }

                // Title is the text before the price
                const allText = text.split('RM')[0].trim();

                results.push({
                    title: allText || '',
                    price_display: price,
                    sold_count: sold,
                    rating: rating,
                    product_url: href.startsWith('http')
                        ? href
                        : 'https://shopee.com.my' + href,
                    image_url: imgEl
                        ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || null)
                        : null,
                });
            }
            return results;
        }""",
        max_items,
    )

    return tuple(
        ShopeeProduct(
            title=item.get("title", ""),
            price_display=item.get("price_display", ""),
            sold_count=item.get("sold_count"),
            rating=item.get("rating"),
            product_url=item.get("product_url"),
            image_url=item.get("image_url"),
        )
        for item in raw_items
        if item.get("title")
    )
