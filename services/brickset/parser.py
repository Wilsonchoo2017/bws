"""Parse Brickset set page HTML for metadata extraction.

Brickset uses <section class="featurebox"><h2>Details</h2> containing
a <dl> with <dt> labels and <dd> values.

Example:
    <dt>RRP</dt>
    <dd>£169.99, $199.99, €199.99</dd>
    <dt>Launch/exit</dt>
    <dd>01 Jan 20 - 31 Dec 23</dd>
"""

import html as html_mod
import re
from dataclasses import dataclass

from bws_types.price import dollars_to_cents


@dataclass(frozen=True)
class BricksetData:
    """Parsed metadata from a Brickset set page."""

    set_number: str
    title: str | None = None
    theme: str | None = None
    subtheme: str | None = None
    year_released: int | None = None
    year_retired: int | None = None
    pieces: int | None = None
    minifigs: int | None = None
    rrp_usd_cents: int | None = None
    rrp_gbp_cents: int | None = None
    rrp_eur_cents: int | None = None
    image_url: str | None = None


def parse_brickset_page(html: str, set_number: str) -> BricksetData:
    """Parse a Brickset set page HTML into structured data."""
    fields = _extract_all_fields(html)

    title = fields.get("Name")
    theme = fields.get("Theme")
    subtheme = fields.get("Subtheme")

    year_released = _parse_year(fields.get("Year released"))
    pieces = _parse_int(fields.get("Pieces"))
    minifigs = _parse_int(fields.get("Minifigs"))
    image_url = _extract_image(html)

    # RRP from comma-separated currencies: "£169.99, $199.99, €199.99"
    rrp_raw = fields.get("RRP", "")
    rrp_usd_cents = _parse_currency_amount(rrp_raw, "$")
    rrp_gbp_cents = _parse_currency_amount(rrp_raw, "\u00a3")
    rrp_eur_cents = _parse_currency_amount(rrp_raw, "\u20ac")

    # Retirement year from "Launch/exit": "01 Jan 20 - 31 Dec 23"
    year_retired = _parse_exit_year(fields.get("Launch/exit"))

    return BricksetData(
        set_number=set_number,
        title=title,
        theme=theme,
        subtheme=subtheme,
        year_released=year_released,
        year_retired=year_retired,
        pieces=pieces,
        minifigs=minifigs,
        rrp_usd_cents=rrp_usd_cents,
        rrp_gbp_cents=rrp_gbp_cents,
        rrp_eur_cents=rrp_eur_cents,
        image_url=image_url,
    )


def _extract_all_fields(html: str) -> dict[str, str]:
    """Extract all dt/dd pairs from the featurebox Details section."""
    # Find the Details featurebox
    match = re.search(
        r'<section class="featurebox[^"]*">\s*<h2>Details</h2>(.*?)</section>',
        html,
        re.DOTALL,
    )
    if not match:
        return {}

    section = match.group(1)

    # Extract all dt/dd pairs, stripping HTML tags from values
    pairs = re.findall(
        r"<dt>([^<]+)</dt>\s*<dd[^>]*>(.*?)</dd>",
        section,
        re.DOTALL,
    )
    return {
        label.strip(): html_mod.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for label, value in pairs
    }


def _parse_year(val: str | None) -> int | None:
    """Extract a 4-digit year from a string."""
    if not val:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", val)
    return int(match.group(0)) if match else None


def _parse_int(val: str | None) -> int | None:
    """Extract the leading integer from a string (handles commas in numbers).

    "2504" -> 2504
    "7,541" -> 7541
    "5, all unique to this set" -> 5
    """
    if not val:
        return None
    # Match leading number with optional comma-separated thousands
    match = re.match(r"([\d,]+)", val.strip())
    if not match:
        return None
    cleaned = match.group(1).replace(",", "")
    return int(cleaned) if cleaned else None


def _parse_currency_amount(rrp_str: str, symbol: str) -> int | None:
    """Extract a specific currency amount from an RRP string.

    Input: "£169.99, $199.99, €199.99"
    With symbol="$" -> 19999 (cents)
    """
    escaped = re.escape(symbol)
    match = re.search(rf"{escaped}([\d,]+(?:\.\d{{1,2}})?)(?:\s|,|$)", rrp_str)
    if not match:
        return None
    amount_str = match.group(1).replace(",", "")
    try:
        return dollars_to_cents(float(amount_str))
    except (ValueError, TypeError):
        return None


def _parse_exit_year(launch_exit: str | None) -> int | None:
    """Parse exit year from Launch/exit field.

    Input formats:
        "01 Jan 20 - 31 Dec 23"  -> 2023
        "01 Oct 17 - {t.b.a}"    -> None (not retired)
        "2020 - 2023"            -> 2023
    """
    if not launch_exit:
        return None

    # Skip if not yet retired
    if "{t.b.a}" in launch_exit or "t.b.a" in launch_exit.lower():
        return None

    # Try full date format: "DD Mon YY - DD Mon YY"
    match = re.search(
        r"-\s*\d{1,2}\s+\w+\s+(\d{2,4})\s*$",
        launch_exit.strip(),
    )
    if match:
        year_str = match.group(1)
        year = int(year_str)
        if year < 100:
            year += 2000
        return year

    # Try year-only format: "2020 - 2023"
    match = re.search(r"-\s*(20\d{2})\s*$", launch_exit.strip())
    if match:
        return int(match.group(1))

    return None


def _extract_image(html: str) -> str | None:
    """Extract main set image URL from og:image meta tag."""
    match = re.search(
        r'<meta\s+property="og:image"\s+content="([^"]+)"',
        html,
    )
    if match:
        return match.group(1)
    return None
