"""ToysRUs product HTML parser.

Extracts product data from Demandware Search-ShowAjax HTML responses.
"""


import json
import re
from dataclasses import dataclass
from html import unescape


@dataclass(frozen=True)
class ToysRUsProduct:
    """A single ToysRUs LEGO product."""

    sku: str
    name: str
    price_myr: str
    brand: str
    category: str
    age_range: str
    url: str
    image_url: str
    available: bool
    original_price_myr: str | None = None


_METADATA_PATTERN = re.compile(r"data-metadata='({[^']*})'")
_URL_PATTERN = re.compile(r'href="(/[^"]*\.html)"[^>]*data-gtm-product-link')
_IMAGE_PATTERN = re.compile(r'data-src="(https://www\.toysrus\.com\.my/dw/image/[^"]*)"')
_STATUS_PATTERN = re.compile(r'<div class="status">(\w+)</div>')
_OUT_OF_STOCK_PATTERN = re.compile(r'class="[^"]*(?:out-of-stock|sold-out|unavailable)[^"]*"', re.IGNORECASE)
_ADD_TO_CART_PATTERN = re.compile(r'class="[^"]*add-to-cart[^"]*"')
_ORIGINAL_PRICE_PATTERN = re.compile(
    r'class="strike-through\s+list">\s*<span\s+class="value"\s+content="([\d.]+)"'
)
_TOTAL_PATTERN = re.compile(r"(\d+)\s+products")
_BADGE_PATTERN = re.compile(r'class="badge[^"]*">\s*(\d+)\s*<')


def parse_total_count(html: str) -> int:
    """Extract total product count from page HTML."""
    match = _TOTAL_PATTERN.search(html)
    if match:
        return int(match.group(1))
    match = _BADGE_PATTERN.search(html)
    if match:
        return int(match.group(1))
    return 0


def parse_products(html: str) -> tuple[ToysRUsProduct, ...]:
    """Parse all products from a page of HTML.

    Returns:
        Tuple of ToysRUsProduct (frozen, immutable).
    """
    tiles = html.split('class="col-6 col-md-4 col-lg-3 product-tile-wrapper"')
    if len(tiles) < 2:
        return ()

    products: list[ToysRUsProduct] = []
    for tile in tiles[1:]:
        product = _parse_tile(tile)
        if product is not None:
            products.append(product)

    return tuple(products)


def _parse_tile(tile_html: str) -> ToysRUsProduct | None:
    """Parse a single product tile."""
    metadata_match = _METADATA_PATTERN.search(tile_html)
    if metadata_match is None:
        return None

    raw_json = unescape(metadata_match.group(1))
    try:
        meta = json.loads(raw_json)
    except json.JSONDecodeError:
        return None

    url_match = _URL_PATTERN.search(tile_html)
    url = f"https://www.toysrus.com.my{url_match.group(1)}" if url_match else ""

    image_match = _IMAGE_PATTERN.search(tile_html)
    image_url = image_match.group(1) if image_match else ""

    status_match = _STATUS_PATTERN.search(tile_html)
    if status_match:
        available = status_match.group(1) != "unavailable"
    elif _OUT_OF_STOCK_PATTERN.search(tile_html):
        available = False
    else:
        # Default to unavailable when we can't determine status —
        # only products with a confirmed available status get through
        has_add_to_cart = _ADD_TO_CART_PATTERN.search(tile_html) is not None
        available = has_add_to_cart

    # Extract original/undiscounted price from strike-through HTML
    original_match = _ORIGINAL_PRICE_PATTERN.search(tile_html)
    original_price_myr = original_match.group(1) if original_match else None

    return ToysRUsProduct(
        sku=meta.get("sku", ""),
        name=unescape(meta.get("name", "")),
        price_myr=meta.get("price", ""),
        brand=meta.get("brand", ""),
        category=meta.get("category", ""),
        age_range=meta.get("akeneo_ageRangeYears", ""),
        url=url,
        image_url=image_url,
        available=available,
        original_price_myr=original_price_myr,
    )
