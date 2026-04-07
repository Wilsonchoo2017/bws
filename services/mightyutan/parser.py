"""Mighty Utan product parser.

Extracts product data from Next.js RSC payloads embedded in the HTML
of mightyutan.com.my collection pages (SiteGiant platform).
"""

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MightyUtanProduct:
    """A single Mighty Utan LEGO product."""

    product_id: int
    sku: str
    name: str
    price_myr: str
    url: str
    image_url: str
    available: bool
    quantity: int
    total_sold: int
    original_price_myr: str | None = None
    is_special_price: bool = False
    rating: str | None = None
    rating_count: int = 0


@dataclass(frozen=True)
class PaginationInfo:
    """Pagination metadata from the collection page."""

    current_page: int
    last_page: int
    total: int
    per_page: int


_RSC_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[\d+,"(.*?)"\]\)', re.DOTALL)

_BASE_URL = "https://mightyutan.com.my"


def parse_page(html: str) -> tuple[tuple[MightyUtanProduct, ...], PaginationInfo | None]:
    """Parse products and pagination from a collection page.

    Extracts the productListingPagination JSON from the Next.js RSC
    push blocks embedded in the HTML.

    Returns:
        Tuple of (products, pagination_info). pagination_info is None
        if the data could not be extracted.
    """
    pagination_json = _extract_pagination_json(html)
    if pagination_json is None:
        return (), None

    try:
        pagination = json.loads(pagination_json)
    except json.JSONDecodeError:
        return (), None

    pagination_info = PaginationInfo(
        current_page=pagination.get("current_page", 0),
        last_page=pagination.get("last_page", 0),
        total=pagination.get("total", 0),
        per_page=pagination.get("per_page", 0),
    )

    raw_products = pagination.get("data", [])
    products = tuple(
        parsed
        for p in raw_products
        if (parsed := _parse_product(p)) is not None
    )

    return products, pagination_info


def _extract_pagination_json(html: str) -> str | None:
    """Extract the productListingPagination JSON string from RSC data."""
    for match in _RSC_PUSH_RE.finditer(html):
        content = match.group(1)
        if "productListingPagination" not in content:
            continue

        try:
            unescaped = content.encode().decode("unicode_escape")
        except (UnicodeDecodeError, ValueError):
            continue

        idx = unescaped.find('"productListingPagination":')
        if idx < 0:
            continue

        json_start = unescaped.find("{", idx + 25)
        if json_start < 0:
            continue

        end_pos = _find_matching_brace(unescaped, json_start)
        if end_pos > 0:
            return unescaped[json_start:end_pos]

    return None


def _find_matching_brace(text: str, start: int) -> int:
    """Find the position after the matching closing brace.

    Handles nested braces and JSON string escaping.
    """
    brace_count = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if not in_string:
            if c == "{":
                brace_count += 1
            elif c == "}":
                brace_count -= 1
                if brace_count == 0:
                    return i + 1

    return 0


def _parse_product(raw: dict) -> MightyUtanProduct | None:
    """Parse a single product dict from the pagination data."""
    name = raw.get("name")
    if not name:
        return None

    product_id = raw.get("id", 0)
    sku = raw.get("sku", "")
    quantity = raw.get("totalQty", 0) or 0
    total_sold = raw.get("total_sold") or 0

    seo = raw.get("seo") or raw.get("seoData") or {}
    url_handle = seo.get("url_handle", "")
    url = f"{_BASE_URL}/product/{url_handle}" if url_handle else ""

    images = raw.get("images", [])
    image_url = images[0].get("x420_url", "") if images else ""

    min_ori_price = raw.get("minOriPrice")
    min_price = raw.get("minPrice")
    is_special = raw.get("isSpecialPrice", False)

    # minPrice is the actual selling price (after discount).
    # minOriPrice / converted_price / price is the original RRP.
    # When there's no promotion, minPrice == minOriPrice.
    original_price_myr = None
    if is_special and min_ori_price and min_price:
        if float(min_ori_price) > float(min_price):
            original_price_myr = str(min_ori_price)
            price = str(min_price)
        else:
            price = raw.get("converted_price") or raw.get("price", "0")
    elif min_price and float(min_price) > 0:
        price = str(min_price)
    else:
        price = raw.get("converted_price") or raw.get("price", "0")

    return MightyUtanProduct(
        product_id=product_id,
        sku=sku,
        name=name,
        price_myr=str(price),
        url=url,
        image_url=image_url,
        available=quantity > 0,
        quantity=quantity,
        total_sold=total_sold,
        original_price_myr=original_price_myr,
        is_special_price=is_special,
        rating=raw.get("rating"),
        rating_count=raw.get("rating_count", 0) or 0,
    )
