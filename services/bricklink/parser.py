"""Bricklink HTML parser functions.

Pure functions for parsing Bricklink HTML pages to extract pricing data.
Ported from TypeScript BricklinkParser.ts.
"""

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from bws_types.models import (
    BricklinkData,
    Condition,
    MonthlySale,
    PriceData,
    PricingBox,
)
from bws_types.price import Cents, dollars_to_cents


# Valid Bricklink item types
VALID_ITEM_TYPES = ("P", "S", "M", "G", "C", "I", "O", "B")

# Timezone constant for datetime operations
_UTC = UTC

# Regular expressions for price extraction
RE_TIMES_SOLD = re.compile(r"Times Sold:\s*(\d+)", re.IGNORECASE)
RE_TOTAL_LOTS = re.compile(r"Total Lots:\s*(\d+)", re.IGNORECASE)
RE_TOTAL_QTY = re.compile(r"Total Qty:\s*(\d+)", re.IGNORECASE)
RE_MIN_PRICE = re.compile(r"Min Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)
RE_AVG_PRICE = re.compile(r"Avg Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)
RE_QTY_AVG_PRICE = re.compile(r"Qty Avg Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)
RE_MAX_PRICE = re.compile(r"Max Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)


def _parse_url_params(url: str) -> tuple[str, str] | None:
    """Parse URL parameters, returning item type and ID if found."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    for item_type in VALID_ITEM_TYPES:
        if item_type in params:
            item_id = params[item_type][0]
            return item_type, item_id
    return None


def parse_bricklink_url(url: str) -> tuple[str, str]:
    """Parse Bricklink URL to extract item type and ID.

    Args:
        url: Bricklink URL (e.g., https://www.bricklink.com/catalogPG.asp?S=75192-1)

    Returns:
        Tuple of (item_type, item_id)

    Raises:
        ValueError: If URL is invalid or item type/ID cannot be extracted
    """
    try:
        result = _parse_url_params(url)
    except Exception as e:
        msg = f"Invalid Bricklink URL: {e}"
        raise ValueError(msg) from e

    if result is None:
        msg = f"Could not extract item type and ID from URL. Expected one of: {', '.join(VALID_ITEM_TYPES)}"
        raise ValueError(msg)

    return result


def build_price_guide_url(item_type: str, item_id: str) -> str:
    """Build Bricklink price guide URL.

    Args:
        item_type: Item type (P, S, M, etc.)
        item_id: Item ID

    Returns:
        Price guide URL
    """
    return f"https://www.bricklink.com/catalogPG.asp?{item_type}={item_id}"


def build_item_url(item_type: str, item_id: str) -> str:
    """Build Bricklink catalog item URL.

    Args:
        item_type: Item type (P, S, M, etc.)
        item_id: Item ID

    Returns:
        Catalog item URL
    """
    return f"https://www.bricklink.com/v2/catalog/catalogitem.page?{item_type}={item_id}"


def _parse_price(currency: str, amount_str: str) -> PriceData:
    """Parse currency and amount into PriceData."""
    amount = float(amount_str.replace(",", ""))
    return PriceData(currency=currency.upper(), amount=dollars_to_cents(amount))


def extract_price_box(box_text: str) -> PricingBox | None:
    """Extract pricing box data from box element text.

    Args:
        box_text: Text content of pricing box

    Returns:
        PricingBox or None if no data found
    """
    # Check if box has "(unavailable)" - means no sales, not missing data
    if "(unavailable)" in box_text.lower():
        return PricingBox(times_sold=0, total_lots=0, total_qty=0)

    times_sold: int | None = None
    total_lots: int | None = None
    total_qty: int | None = None
    min_price: PriceData | None = None
    avg_price: PriceData | None = None
    qty_avg_price: PriceData | None = None
    max_price: PriceData | None = None

    # Extract counts
    if match := RE_TIMES_SOLD.search(box_text):
        times_sold = int(match.group(1))
    if match := RE_TOTAL_LOTS.search(box_text):
        total_lots = int(match.group(1))
    if match := RE_TOTAL_QTY.search(box_text):
        total_qty = int(match.group(1))

    # Extract prices
    if match := RE_MIN_PRICE.search(box_text):
        min_price = _parse_price(match.group(1), match.group(2))
    if match := RE_AVG_PRICE.search(box_text):
        avg_price = _parse_price(match.group(1), match.group(2))
    if match := RE_QTY_AVG_PRICE.search(box_text):
        qty_avg_price = _parse_price(match.group(1), match.group(2))
    if match := RE_MAX_PRICE.search(box_text):
        max_price = _parse_price(match.group(1), match.group(2))

    # Return None if no data found
    if all(
        v is None
        for v in [times_sold, total_lots, total_qty, min_price, avg_price, qty_avg_price, max_price]
    ):
        return None

    return PricingBox(
        times_sold=times_sold,
        total_lots=total_lots,
        total_qty=total_qty,
        min_price=min_price,
        avg_price=avg_price,
        qty_avg_price=qty_avg_price,
        max_price=max_price,
    )


def _extract_parts_count(soup: BeautifulSoup) -> int | None:
    """Extract parts count from HTML.

    BrickLink shows parts count in a span like '305 Parts' within the item info section.
    """
    # Look for text matching "N Parts" pattern in the page
    parts_pattern = re.compile(r"(\d[\d,]*)\s+Parts?", re.IGNORECASE)
    for text_node in soup.find_all(string=parts_pattern):
        match = parts_pattern.search(text_node)
        if match:
            count = int(match.group(1).replace(",", ""))
            if 1 <= count <= 20_000:
                return count
    return None


def _extract_theme(soup: BeautifulSoup) -> str | None:
    """Extract theme from the catalog item page.

    BrickLink embeds itemType and itemCatName in JavaScript variables on the page.
    Falls back to breadcrumb links containing the theme.
    """
    # Try JavaScript variable: catString or itemCatName
    scripts = soup.find_all("script")
    for script in scripts:
        text = script.string or ""
        match = re.search(r"var\s+catString\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match:
            theme = match.group(1).strip()
            if theme:
                return theme
        match = re.search(r"itemCatName\s*[:=]\s*['\"]([^'\"]+)['\"]", text)
        if match:
            theme = match.group(1).strip()
            if theme:
                return theme

    # Fallback: breadcrumb links after "Sets" category
    breadcrumbs = soup.select("div#content-area a, nav a")
    found_sets = False
    for link in breadcrumbs:
        text = link.get_text(strip=True)
        if text == "Sets":
            found_sets = True
            continue
        if found_sets and text and text not in ("Catalog", "Items", ""):
            return text

    return None


def _extract_year_released(html: str) -> int | None:
    """Extract year released from HTML."""
    match = re.search(r"Year Released:.*?(\d{4})", html, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        current_year = datetime.now(tz=_UTC).year
        if 1949 <= year <= current_year + 2:
            return year
    return None


def _normalize_image_url(url: str) -> str:
    """Normalize Bricklink image URL."""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.bricklink.com{url}"
    return url


def _extract_image_url(soup: BeautifulSoup) -> str | None:
    """Extract image URL from parsed HTML."""
    # Try various selectors
    selectors = [
        "img#ItemEditForm\\:largeImg",
        "img[id*='largeImg']",
        "div#item-image-block img",
        "div.item-image img",
    ]

    for selector in selectors:
        img = soup.select_one(selector)
        if img and img.get("src"):
            return _normalize_image_url(str(img["src"]))

    # Fallback: find images containing bricklink image URLs
    for img in soup.find_all("img"):
        src = img.get("src", "")
        is_bricklink_img = src and ("img.bricklink.com" in src or "brickimg" in src)
        is_not_thumbnail = "/icon/" not in src and "_thumb" not in src and "small" not in src
        if is_bricklink_img and is_not_thumbnail:
            return _normalize_image_url(src)

    return None


def parse_item_info(html: str) -> dict[str, str | int | None]:
    """Parse item information from HTML.

    Args:
        html: HTML content from catalog item page

    Returns:
        Dict with title, weight, year_released, image_url
    """
    soup = BeautifulSoup(html, "lxml")

    title_elem = soup.select_one("h1#item-name-title")
    title = title_elem.get_text(strip=True) if title_elem else None

    weight_elem = soup.select_one("span#item-weight-info")
    weight = weight_elem.get_text(strip=True) if weight_elem else None

    year_released = _extract_year_released(html)
    image_url = _extract_image_url(soup)
    parts_count = _extract_parts_count(soup)
    theme = _extract_theme(soup)

    return {
        "title": title,
        "weight": weight,
        "year_released": year_released,
        "image_url": image_url,
        "parts_count": parts_count,
        "theme": theme,
    }


def parse_price_guide(html: str) -> dict[str, PricingBox | None]:
    """Parse price guide from HTML.

    Args:
        html: HTML content from price guide page

    Returns:
        Dict with six_month_new, six_month_used, current_new, current_used

    Raises:
        ValueError: If page structure is invalid or item not found
    """
    soup = BeautifulSoup(html, "lxml")

    # Check for error page
    title = soup.select_one("title")
    if title and "not found" in title.get_text().lower():
        msg = "Price guide page not found - item may not exist on Bricklink"
        raise ValueError(msg)

    if "notFound.asp" in html:
        msg = "Price guide page not found - item may not exist on Bricklink"
        raise ValueError(msg)

    # Find pricing boxes (4 boxes in row with bgcolor="#C0C0C0")
    price_boxes = soup.select('tr[bgcolor="#C0C0C0"] > td')

    if not price_boxes:
        msg = "Price guide table structure not found. Page may have been redirected or Bricklink's HTML structure has changed."
        raise ValueError(msg)

    result: dict[str, PricingBox | None] = {
        "six_month_new": None,
        "six_month_used": None,
        "current_new": None,
        "current_used": None,
    }

    if len(price_boxes) >= 4:
        result["six_month_new"] = extract_price_box(price_boxes[0].get_text())
        result["six_month_used"] = extract_price_box(price_boxes[1].get_text())
        result["current_new"] = extract_price_box(price_boxes[2].get_text())
        result["current_used"] = extract_price_box(price_boxes[3].get_text())

    return result


def parse_monthly_sales(html: str) -> list[MonthlySale]:
    """Parse monthly sales data from Bricklink HTML.

    Args:
        html: HTML content from price guide page

    Returns:
        List of MonthlySale records
    """
    soup = BeautifulSoup(html, "lxml")
    summaries: list[MonthlySale] = []

    # Month name to number mapping
    month_map = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }

    current_month: tuple[int, int] | None = None  # (year, month)
    current_condition: Condition | None = None

    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        first_row_text = rows[0].get_text(strip=True) if rows else ""

        # Skip "Currently Available" section
        if "Currently Available" in first_row_text:
            current_month = None
            continue

        # Check for month header (e.g., "November 2025")
        month_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})"
        month_match = re.search(month_pattern, first_row_text)

        if month_match:
            month_name = month_match.group(1)
            year = int(month_match.group(2))
            current_month = (year, month_map[month_name])
            continue

        # Check if this is a sales data table
        header_text = first_row_text.lower()
        if "qty" in header_text and "each" in header_text:
            if not current_month:
                continue

            # Determine condition from parent element bgcolor
            parent_td = table.find_parent("td")
            if parent_td:
                bgcolor = parent_td.get("bgcolor", "").lower()
                if bgcolor == "eeeeee":
                    current_condition = Condition.NEW
                elif bgcolor == "dddddd":
                    current_condition = Condition.USED
                else:
                    current_condition = Condition.NEW  # Default
            else:
                current_condition = Condition.NEW

            # Parse sales rows
            prices: list[Cents] = []
            quantities: list[int] = []
            currency = "USD"

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                cell_texts = [c.get_text(strip=True) for c in cells]
                row_text = " ".join(cell_texts)

                # Skip summary rows
                if any(
                    skip in row_text
                    for skip in [
                        "Times Sold:",
                        "Total Lots:",
                        "Total Qty:",
                        "Avg:",
                        "Min:",
                        "Max:",
                    ]
                ):
                    continue

                # Find quantity and price
                qty_text = ""
                price_text = ""

                for text in cell_texts:
                    if not qty_text and re.match(r"^\d+$", text):
                        qty_text = text
                    elif not price_text and re.search(r"([A-Z]{2,3})\s+([\d,\.]+)", text):
                        price_text = text

                if not qty_text:
                    continue

                qty = int(qty_text)

                # Parse price
                price_match = re.search(r"~?\s*([A-Z]{2,3})\s+([\d,\.]+)", price_text)
                if not price_match:
                    continue

                currency = price_match.group(1).upper()
                amount = float(price_match.group(2).replace(",", ""))
                prices.append(dollars_to_cents(amount))
                quantities.append(qty)

            # Create summary if we have data
            if prices:
                year, month = current_month
                total_qty = sum(quantities)
                min_price_cents = min(prices)
                max_price_cents = max(prices)
                avg_price_cents = Cents(sum(prices) // len(prices))

                summary = MonthlySale(
                    item_id="",  # Will be set by caller
                    year=year,
                    month=month,
                    condition=current_condition,
                    times_sold=len(prices),
                    total_quantity=total_qty,
                    min_price=PriceData(currency=currency, amount=min_price_cents),
                    max_price=PriceData(currency=currency, amount=max_price_cents),
                    avg_price=PriceData(currency=currency, amount=avg_price_cents),
                    currency=currency,
                )
                summaries.append(summary)

    # Deduplicate by month+condition
    seen: set[tuple[int, int, str]] = set()
    unique_summaries: list[MonthlySale] = []
    for s in summaries:
        key = (s.year, s.month, s.condition.value)
        if key not in seen:
            seen.add(key)
            unique_summaries.append(s)

    return unique_summaries


def parse_full_item(
    item_html: str,
    price_guide_html: str,
    item_type: str,
    item_id: str,
) -> BricklinkData:
    """Parse complete item data from both HTML pages.

    Args:
        item_html: HTML from catalog item page
        price_guide_html: HTML from price guide page
        item_type: Item type (P, S, M, etc.)
        item_id: Item ID

    Returns:
        Complete BricklinkData
    """
    item_info = parse_item_info(item_html)
    pricing = parse_price_guide(price_guide_html)

    return BricklinkData(
        item_id=item_id,
        item_type=item_type,
        title=item_info.get("title"),  # type: ignore[arg-type]
        weight=item_info.get("weight"),  # type: ignore[arg-type]
        year_released=item_info.get("year_released"),  # type: ignore[arg-type]
        image_url=item_info.get("image_url"),  # type: ignore[arg-type]
        parts_count=item_info.get("parts_count"),  # type: ignore[arg-type]
        theme=item_info.get("theme"),  # type: ignore[arg-type]
        six_month_new=pricing.get("six_month_new"),
        six_month_used=pricing.get("six_month_used"),
        current_new=pricing.get("current_new"),
        current_used=pricing.get("current_used"),
    )


def is_valid_bricklink_url(url: str) -> bool:
    """Check if URL is a valid Bricklink URL.

    Args:
        url: URL to validate

    Returns:
        True if valid Bricklink URL
    """
    try:
        parse_bricklink_url(url)
    except ValueError:
        return False
    else:
        return True
