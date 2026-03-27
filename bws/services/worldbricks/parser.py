"""WorldBricks HTML parser functions.

Pure functions for parsing WorldBricks.com HTML pages to extract LEGO set metadata.
Ported from TypeScript WorldBricksParser.ts.

Key data extracted:
- year_released (HIGH PRIORITY)
- year_retired (HIGH PRIORITY)
- parts_count
- dimensions
"""

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class WorldBricksData:
    """Complete WorldBricks LEGO set data."""

    set_number: str
    set_name: str | None = None
    year_released: int | None = None
    year_retired: int | None = None
    parts_count: int | None = None
    dimensions: str | None = None
    image_url: str | None = None


def construct_search_url(set_number: str) -> str:
    """Construct WorldBricks search URL from set number.

    Args:
        set_number: LEGO set number (e.g., "7834")

    Returns:
        Search URL for WorldBricks
    """
    return f"https://www.worldbricks.com/en/all.html?search={set_number}"


def parse_search_results(html: str, set_number: str) -> str | None:
    """Parse search results page to extract product URL.

    Looks for links matching the set number in search results.

    Args:
        html: Raw HTML from search results page
        set_number: LEGO set number being searched for

    Returns:
        Product page URL or None if not found
    """
    soup = BeautifulSoup(html, "lxml")

    # Look for links to product pages that match the set number
    links = soup.select('a[href*="lego-set"]')

    pattern = re.compile(rf"/{set_number}-[^/]+\.html", re.IGNORECASE)

    for link in links:
        href = link.get("href")
        if href and pattern.search(str(href)):
            # Convert relative URL to absolute
            href_str = str(href)
            if href_str.startswith("/"):
                return f"https://www.worldbricks.com{href_str}"
            return href_str

    return None


def _extract_json_ld_product(soup: BeautifulSoup) -> dict | None:
    """Extract and parse JSON-LD Product schema.

    Args:
        soup: Parsed HTML document

    Returns:
        Parsed Product schema dict or None
    """
    scripts = soup.select('script[type="application/ld+json"]')

    for script in scripts:
        content = script.string
        if not content:
            continue

        try:
            data = json.loads(content)
            if data.get("@type") == "Product":
                return data
        except json.JSONDecodeError:
            continue

    return None


def _extract_set_number(soup: BeautifulSoup, source_url: str) -> str | None:
    """Extract LEGO set number from page.

    Checks: JSON-LD, meta tags, URL pattern.

    Args:
        soup: Parsed HTML document
        source_url: Original URL for fallback extraction

    Returns:
        Set number or None
    """
    # Try JSON-LD structured data first
    json_ld = _extract_json_ld_product(soup)
    if json_ld and json_ld.get("productID"):
        return str(json_ld["productID"])

    # Try meta tags
    twitter_title = soup.select_one('meta[name="twitter:title"]')
    if twitter_title:
        content = twitter_title.get("content", "")
        match = re.search(r"\b(\d{4,5})\b", str(content))
        if match:
            return match.group(1)

    # Try URL pattern: /31009-Small-Cottage.html
    url_match = re.search(r"/(\d{4,5})-[^/]+\.html$", source_url)
    if url_match:
        return url_match.group(1)

    return None


def _extract_set_name(soup: BeautifulSoup) -> str | None:
    """Extract set name from page.

    Checks: Meta tags, title, JSON-LD.

    Args:
        soup: Parsed HTML document

    Returns:
        Set name or None
    """
    # Try meta description
    meta_desc = soup.select_one('meta[name="twitter:description"]')
    if meta_desc:
        content = meta_desc.get("content", "")
        match = re.search(r"\d+\s+([^,]+)", str(content))
        if match:
            return match.group(1).strip()

    # Try page title
    title = soup.select_one("title")
    if title and title.string:
        match = re.search(r"\d+\s+([^-]+)", title.string)
        if match:
            return match.group(1).strip()

    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    """Extract product description.

    Looks for .tab-value div containing description text.

    Args:
        soup: Parsed HTML document

    Returns:
        Description text or None
    """
    # Look for description in tab content
    desc_div = soup.select_one(".tab-value")
    if desc_div:
        return desc_div.get_text(strip=True) or None

    # Fallback to meta description
    meta_desc = soup.select_one('meta[name="description"]')
    if meta_desc:
        content = meta_desc.get("content")
        if content:
            return str(content).strip() or None

    return None


def _extract_lego_year_field(soup: BeautifulSoup) -> str | None:
    """Extract LEGO year field which contains release and/or retirement year.

    Located in: <h3>LEGO year:</h3> followed by <div class="tab-value">

    Args:
        soup: Parsed HTML document

    Returns:
        Year field text or None
    """
    headings = soup.select("h3.body_title")

    for heading in headings:
        text = heading.get_text(strip=True)
        if text and "lego year" in text.lower():
            # Get the next sibling with class tab-value
            sibling = heading.find_next_sibling()
            while sibling:
                if isinstance(sibling, Tag) and "tab-value" in (sibling.get("class") or []):
                    return sibling.get_text(strip=True) or None
                sibling = sibling.find_next_sibling()

    return None


def extract_year_released(soup: BeautifulSoup) -> int | None:
    """Extract year released (HIGH PRIORITY).

    Checks multiple sources:
    1. LEGO year field: "YYYY - Retired YYYY" (extracts first year)
    2. LEGO year field: "YYYY" (single year)
    3. Description: "Released in YYYY"

    Args:
        soup: Parsed HTML document

    Returns:
        Year released or None
    """
    # First check LEGO year field
    lego_year = _extract_lego_year_field(soup)
    if lego_year:
        # Look for "YYYY - Retired YYYY" pattern (e.g., "1980 - Retired 1982")
        retired_match = re.search(r"(\d{4})\s*-\s*Retired\s*(\d{4})", lego_year, re.IGNORECASE)
        if retired_match:
            return int(retired_match.group(1))

        # Look for single year
        year_match = re.search(r"(\d{4})", lego_year)
        if year_match:
            return int(year_match.group(1))

    # Fallback to description
    description = _extract_description(soup)
    if description:
        # Look for "Released in 2013" pattern
        released_match = re.search(r"Released in (\d{4})", description, re.IGNORECASE)
        if released_match:
            return int(released_match.group(1))

    return None


def extract_year_retired(soup: BeautifulSoup) -> int | None:
    """Extract year retired (HIGH PRIORITY).

    Checks LEGO year field for "YYYY - Retired YYYY" pattern.
    Returns None if not found (many sets don't have retirement year).

    Args:
        soup: Parsed HTML document

    Returns:
        Year retired or None
    """
    lego_year = _extract_lego_year_field(soup)
    if lego_year:
        # Look for "YYYY - Retired YYYY" pattern (e.g., "1980 - Retired 1982")
        match = re.search(r"(\d{4})\s*-\s*Retired\s*(\d{4})", lego_year, re.IGNORECASE)
        if match:
            return int(match.group(2))  # Return the second year (retirement year)

    return None


def extract_parts_count(soup: BeautifulSoup) -> int | None:
    """Extract parts count.

    Parses description for "XXX pieces" pattern.

    Args:
        soup: Parsed HTML document

    Returns:
        Parts count or None
    """
    description = _extract_description(soup)

    if description:
        # Look for "271 pieces" pattern
        match = re.search(r"(\d+)\s+pieces", description, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def _extract_dimensions(soup: BeautifulSoup) -> str | None:
    """Extract dimensions from JSON-LD Product schema.

    Returns formatted string: "WxDxH cm"

    Args:
        soup: Parsed HTML document

    Returns:
        Dimensions string or None
    """
    json_ld = _extract_json_ld_product(soup)

    if json_ld and json_ld.get("width") and json_ld.get("height") and json_ld.get("depth"):
        width = json_ld["width"].get("value", "")
        depth = json_ld["depth"].get("value", "")
        height = json_ld["height"].get("value", "")
        unit_code = json_ld["width"].get("unitCode", "CMT")
        unit = "cm" if unit_code == "CMT" else unit_code

        return f"{width}x{depth}x{height} {unit}"

    return None


def _extract_image_url(soup: BeautifulSoup) -> str | None:
    """Extract image URL.

    Checks: Meta tags (Open Graph), JSON-LD.

    Args:
        soup: Parsed HTML document

    Returns:
        Image URL or None
    """
    # Try Open Graph secure URL first
    og_image = soup.select_one('meta[property="og:image:secure_url"]')
    if og_image:
        content = og_image.get("content")
        if content:
            return str(content)

    # Try Twitter image
    twitter_image = soup.select_one('meta[name="twitter:image"]')
    if twitter_image:
        content = twitter_image.get("content")
        if content:
            return str(content)

    # Try JSON-LD
    json_ld = _extract_json_ld_product(soup)
    if json_ld and json_ld.get("image"):
        image_url = str(json_ld["image"])
        # Add https: if protocol-relative
        if image_url.startswith("//"):
            return f"https:{image_url}"
        return image_url

    return None


def parse_worldbricks_page(html: str, set_number: str) -> WorldBricksData:
    """Parse WorldBricks HTML to extract LEGO set data.

    Pure function - no side effects.

    Args:
        html: Raw HTML string from WorldBricks page
        set_number: Expected set number for validation

    Returns:
        Parsed LEGO set data

    Raises:
        ValueError: If page cannot be parsed or set number doesn't match
    """
    soup = BeautifulSoup(html, "lxml")

    # Extract set number from page for validation
    extracted_set_number = _extract_set_number(soup, "")

    # Use provided set_number if extraction failed
    final_set_number = extracted_set_number or set_number

    return WorldBricksData(
        set_number=final_set_number,
        set_name=_extract_set_name(soup),
        year_released=extract_year_released(soup),
        year_retired=extract_year_retired(soup),
        parts_count=extract_parts_count(soup),
        dimensions=_extract_dimensions(soup),
        image_url=_extract_image_url(soup),
    )


def is_valid_worldbricks_page(html: str) -> bool:
    """Validate if HTML appears to be a valid WorldBricks product page.

    Checks for presence of key elements.

    Args:
        html: Raw HTML string

    Returns:
        True if appears to be valid product page
    """
    return (
        "worldbricks.com" in html
        and "LEGO" in html
        and ("djcatalog2" in html or "Instructions" in html)
    )
