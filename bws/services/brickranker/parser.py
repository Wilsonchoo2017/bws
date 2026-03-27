"""BrickRanker HTML parser functions.

Pure functions for parsing BrickRanker.com retirement tracker HTML.
Ported from TypeScript BrickRankerParser.ts.

Key data extracted:
- Set number and name
- Year released
- Retiring soon status
- Expected retirement date
- Theme
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class RetirementItem:
    """Retirement item data from BrickRanker."""

    set_number: str
    set_name: str
    year_released: int | None = None
    retiring_soon: bool = False
    expected_retirement_date: str | None = None
    theme: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class BrickRankerParseResult:
    """Parse result containing all items from all themes."""

    items: tuple[RetirementItem, ...]
    themes: tuple[str, ...]


def _find_theme_for_table(table: Tag) -> str | None:
    """Find the theme name associated with a table.

    Looks for headings (h2, h3, h4) before the table.

    Args:
        table: The table element

    Returns:
        Theme name or None
    """
    current = table.find_previous_sibling()

    while current:
        if isinstance(current, Tag) and current.name in ("h2", "h3", "h4"):
            return current.get_text(strip=True) or None
        current = current.find_previous_sibling()

    return None


def _extract_set_name(name_cell: Tag) -> str | None:
    """Extract set name from name cell.

    Args:
        name_cell: Cell containing set name/link

    Returns:
        Set name or None
    """
    # Try to find all links in the cell
    links = name_cell.find_all("a")

    for link in links:
        text = link.get_text(strip=True)
        # Skip empty links and "Buy now" type links
        if text and len(text) > 0 and "buy" not in text.lower():
            return text

    # Fallback to cell text, but clean it up
    text = name_cell.get_text(strip=True)

    # Remove common noise
    text = re.sub(r"Buy now", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Retiring soon!", "", text, flags=re.IGNORECASE)
    text = text.strip()

    return text if text else None


def _extract_set_number(name_cell: Tag, set_name: str) -> str | None:
    """Extract LEGO set number from name cell or set name.

    Args:
        name_cell: Cell containing set info
        set_name: Set name text

    Returns:
        Set number or None
    """
    # Try to extract from link href
    link = name_cell.find("a")
    if link:
        href = link.get("href", "")
        if href:
            href_str = str(href)

            # Pattern 1: /XXXXX-X/set-name (most common on BrickRanker)
            match = re.search(r"/(\d{4,5})-\d+/", href_str)
            if match:
                return match.group(1)

            # Pattern 2: /sets/XXXXX
            match = re.search(r"/sets/(\d{4,5})", href_str)
            if match:
                return match.group(1)

            # Pattern 3: Any 4-5 digit number in URL
            match = re.search(r"(\d{4,5})", href_str)
            if match:
                return match.group(1)

    # Try to extract from set name
    match = re.search(r"\b(\d{4,5})\b", set_name)
    if match:
        return match.group(1)

    # Try to extract from any text in the cell
    cell_text = name_cell.get_text()
    match = re.search(r"\b(\d{4,5})\b", cell_text)
    if match:
        return match.group(1)

    return None


def _extract_year(year_cell: Tag) -> int | None:
    """Extract year from year cell.

    Args:
        year_cell: Cell containing year

    Returns:
        Year as number or None
    """
    text = year_cell.get_text(strip=True)
    if not text:
        return None

    # Extract 4-digit year (2000-2099)
    match = re.search(r"\b(20\d{2})\b", text)
    if match:
        return int(match.group(1))

    # Try direct parsing
    try:
        year = int(text)
        if 2000 <= year <= 2030:
            return year
    except ValueError:
        pass

    return None


def _extract_retirement_date(date_cell: Tag) -> str | None:
    """Extract retirement date from retirement date cell.

    Args:
        date_cell: Cell containing retirement date

    Returns:
        Retirement date string or None
    """
    text = date_cell.get_text(strip=True)

    if not text or text in ("-", "N/A", ""):
        return None

    return text


def _check_retiring_soon_tag(row: Tag) -> bool:
    """Check if row has "Retiring Soon!" tag.

    Args:
        row: Table row element

    Returns:
        True if retiring soon tag is present
    """
    text = row.get_text()
    return "retiring soon" in text.lower()


def _normalize_image_url(url: str) -> str:
    """Normalize image URL to absolute URL.

    Args:
        url: Relative or absolute URL

    Returns:
        Absolute URL
    """
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://brickranker.com{url}"
    return f"https://brickranker.com/{url}"


def _extract_image_url(name_cell: Tag) -> str | None:
    """Extract image URL from name cell.

    Args:
        name_cell: Cell containing product image and name

    Returns:
        Image URL or None
    """
    img = name_cell.find("img")
    if not img:
        return None

    # Try src attribute
    src = img.get("src")
    if src:
        return _normalize_image_url(str(src))

    # Try data-src (lazy loading)
    data_src = img.get("data-src")
    if data_src:
        return _normalize_image_url(str(data_src))

    return None


def _parse_table_row(row: Tag, theme: str) -> RetirementItem | None:
    """Parse a single table row to extract retirement item data.

    Args:
        row: Table row element
        theme: Theme name for this row

    Returns:
        Parsed item data or None if invalid
    """
    cells = row.find_all("td")

    if len(cells) < 3:
        return None

    # BrickRanker structure (4 columns):
    # Column 0: Product image/name (with link)
    # Column 1: Year released
    # Column 2: Expected retirement date
    # Column 3: Buy now button (optional)

    name_cell = cells[0]
    year_cell = cells[1]
    date_cell = cells[2]

    # Extract set name
    set_name = _extract_set_name(name_cell)
    if not set_name:
        return None

    # Extract set number
    set_number = _extract_set_number(name_cell, set_name)
    if not set_number:
        return None

    # Extract other fields
    year_released = _extract_year(year_cell)
    expected_retirement_date = _extract_retirement_date(date_cell)
    retiring_soon = _check_retiring_soon_tag(row)
    image_url = _extract_image_url(name_cell)

    return RetirementItem(
        set_number=set_number,
        set_name=set_name,
        year_released=year_released,
        retiring_soon=retiring_soon,
        expected_retirement_date=expected_retirement_date,
        theme=theme,
        image_url=image_url,
    )


def parse_retirement_tracker_page(html: str) -> BrickRankerParseResult:
    """Parse the main HTML document to extract retirement tracker data.

    Pure function - no side effects.

    Args:
        html: HTML content from BrickRanker retirement tracker page

    Returns:
        Parsed retirement item data

    Raises:
        ValueError: If document cannot be parsed
    """
    soup = BeautifulSoup(html, "lxml")

    items: list[RetirementItem] = []
    themes: set[str] = set()

    # Find all tables on the page (each theme has its own table)
    tables = soup.find_all("table")

    for table in tables:
        if not isinstance(table, Tag):
            continue

        # Find the theme name
        theme = _find_theme_for_table(table)
        if theme:
            themes.add(theme)

        # Parse all rows in the table (skip header row)
        rows = table.find_all("tr")

        for i, row in enumerate(rows):
            if i == 0:  # Skip header row
                continue

            if not isinstance(row, Tag):
                continue

            item = _parse_table_row(row, theme or "Unknown")
            if item:
                items.append(item)

    return BrickRankerParseResult(
        items=tuple(items),
        themes=tuple(sorted(themes)),
    )


def is_valid_brickranker_url(url: str) -> bool:
    """Validate BrickRanker retirement tracker URL.

    Args:
        url: URL to validate

    Returns:
        True if valid BrickRanker retirement tracker URL
    """
    return "brickranker.com" in url and "retirement-tracker" in url


BRICKRANKER_URL = "https://brickranker.com/retirement-tracker"
