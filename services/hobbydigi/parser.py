"""HobbyDigi product parser.

Extracts product data from Magento catalog pages rendered in the browser.
Uses Playwright page.evaluate() to pull structured data from the DOM.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HobbyDigiProduct:
    """A single HobbyDigi LEGO product."""

    product_id: str
    name: str
    price_myr: str
    url: str
    image_url: str
    available: bool
    original_price_myr: str | None = None
    is_special_price: bool = False
    rating_pct: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PaginationInfo:
    """Pagination metadata from the toolbar."""

    current_page: int
    last_page: int
    total: int
    per_page: int


# JavaScript executed inside the browser to extract all products from the DOM.
EXTRACT_PRODUCTS_JS = """
() => {
    const items = document.querySelectorAll('li.product-item');
    const results = [];
    for (const el of items) {
        const nameLink = el.querySelector('.product-item-link');
        const img = el.querySelector('.product-image-photo');
        const gaId = el.getAttribute('data-ga-product-id') || '';

        // Price extraction via data-price-amount attributes (most reliable)
        const finalPriceEl = el.querySelector('[data-price-type="finalPrice"]');
        const oldPriceEl = el.querySelector('[data-price-type="oldPrice"]');

        const finalPrice = finalPriceEl
            ? finalPriceEl.getAttribute('data-price-amount')
            : null;
        const oldPrice = oldPriceEl
            ? oldPriceEl.getAttribute('data-price-amount')
            : null;

        const hasSpecialPrice = el.querySelector('.special-price') !== null;

        // Stock: out-of-stock via .stock.unavailable or missing add-to-cart
        const stockUnavail = el.querySelector('.stock.unavailable');
        const outOfStockEl = el.querySelector('[title="Out of stock"]');
        const addToCart = el.querySelector('.action.tocart');
        const available = !stockUnavail && !outOfStockEl && addToCart !== null;

        const ratingEl = el.querySelector('.rating-result');
        const ratingPct = ratingEl ? ratingEl.getAttribute('title') : null;

        // Product tags (e.g. "Free Shipping", "Retired", "New")
        const tagEls = el.querySelectorAll('.product_tag');
        const tags = [];
        tagEls.forEach(t => tags.push(t.textContent.trim()));

        // Clean the product URL (strip banner redirect wrapper)
        let rawUrl = nameLink ? nameLink.href : '';
        if (rawUrl.includes('banner/redirect')) {
            try {
                const u = new URL(rawUrl);
                const inner = u.searchParams.get('url');
                if (inner) rawUrl = inner;
            } catch(e) {}
        }

        results.push({
            product_id: gaId,
            name: nameLink ? nameLink.textContent.trim() : '',
            final_price: finalPrice,
            old_price: oldPrice,
            is_special_price: hasSpecialPrice,
            url: rawUrl,
            image_url: img ? img.src : '',
            available: available,
            rating_pct: ratingPct,
            tags: tags,
        });
    }
    return results;
}
"""

# JavaScript to extract pagination info from the Magento toolbar.
EXTRACT_PAGINATION_JS = """
() => {
    const amountEl = document.querySelector('.toolbar-amount');
    if (!amountEl) return null;

    const text = amountEl.textContent.trim();
    // "Items 1-28 of 2665"
    const match = text.match(/Items\\s+(\\d+)-(\\d+)\\s+of\\s+(\\d+)/i);
    if (!match) return null;

    const rangeStart = parseInt(match[1]);
    const rangeEnd = parseInt(match[2]);
    const total = parseInt(match[3]);
    const perPage = rangeEnd - rangeStart + 1;
    const currentPage = Math.ceil(rangeStart / perPage);
    const lastPage = Math.ceil(total / perPage);

    return {
        current_page: currentPage,
        last_page: lastPage,
        total: total,
        per_page: perPage,
    };
}
"""


def parse_raw_products(raw_items: list[dict]) -> tuple[HobbyDigiProduct, ...]:
    """Convert raw JS-extracted dicts into frozen dataclass instances."""
    products: list[HobbyDigiProduct] = []
    for raw in raw_items:
        name = raw.get("name", "").strip()
        if not name:
            continue

        final_price = raw.get("final_price")
        old_price = raw.get("old_price")
        is_special = raw.get("is_special_price", False)

        price_myr = str(final_price) if final_price else "0"
        original_price_myr = None
        if is_special and old_price and final_price:
            if float(old_price) > float(final_price):
                original_price_myr = str(old_price)

        raw_tags = raw.get("tags", [])
        tags = tuple(t for t in raw_tags if t)

        products.append(
            HobbyDigiProduct(
                product_id=raw.get("product_id", ""),
                name=name,
                price_myr=price_myr,
                url=raw.get("url", ""),
                image_url=raw.get("image_url", ""),
                available=raw.get("available", True),
                original_price_myr=original_price_myr,
                is_special_price=is_special,
                rating_pct=raw.get("rating_pct"),
                tags=tags,
            )
        )

    return tuple(products)


def parse_raw_pagination(raw: dict | None) -> PaginationInfo | None:
    """Convert raw JS-extracted pagination dict into a frozen dataclass."""
    if raw is None:
        return None
    return PaginationInfo(
        current_page=raw.get("current_page", 0),
        last_page=raw.get("last_page", 0),
        total=raw.get("total", 0),
        per_page=raw.get("per_page", 0),
    )
