"""Pure parsing functions for BrickEconomy set pages.

Extracts metadata, price charts, sale trends, and distribution stats
from server-rendered HTML containing inline Google Charts JavaScript
and JSON-LD structured data.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from bs4 import BeautifulSoup

logger = logging.getLogger("bws.brickeconomy.parser")

# Packaging types that indicate non-standard sets we don't want to track.
# Standard sets have "Box" or no packaging field at all.
EXCLUDED_PACKAGING: frozenset[str] = frozenset({
    "Foil Pack",
    "Polybag",
    "Bucket",
    "Bag",
    "Tub",
    "Canister",
})


def is_excluded_packaging(packaging: str | None) -> bool:
    """Return True if the set has non-standard packaging we want to skip."""
    if packaging is None:
        return False
    return packaging.strip() in EXCLUDED_PACKAGING


@dataclass(frozen=True)
class BrickeconomySnapshot:
    """Point-in-time snapshot of a BrickEconomy set page."""

    set_number: str
    scraped_at: datetime

    # Metadata
    title: str | None = None
    theme: str | None = None
    subtheme: str | None = None
    year_released: int | None = None
    year_retired: int | None = None
    release_date: str | None = None  # ISO month "2025-01" from "January 2025"
    retired_date: str | None = None  # ISO month "2021-10" from "October 2021"
    pieces: int | None = None
    minifigs: int | None = None
    minifig_value_cents: int | None = None  # total minifig value USD cents
    exclusive_minifigs: bool | None = None  # "All exclusive" indicator
    availability: str | None = None
    retiring_soon: bool | None = None
    image_url: str | None = None
    packaging: str | None = None  # e.g. "Box", "Foil Pack", "Polybag"
    brickeconomy_url: str | None = None

    # Identifiers
    upc: str | None = None
    ean: str | None = None
    designer: str | None = None  # comma-separated if multiple

    # Retail prices (cents)
    rrp_usd_cents: int | None = None
    rrp_gbp_cents: int | None = None
    rrp_eur_cents: int | None = None
    rrp_cad_cents: int | None = None
    rrp_aud_cents: int | None = None

    # Current market values (cents USD)
    value_new_cents: int | None = None
    value_used_cents: int | None = None
    used_value_low_cents: int | None = None
    used_value_high_cents: int | None = None

    # Metrics
    annual_growth_pct: float | None = None
    total_growth_pct: float | None = None
    rolling_growth_pct: float | None = None  # previous 12 months
    growth_90d_pct: float | None = None
    rating_value: str | None = None
    review_count: int | None = None

    # Theme/subtheme context
    theme_rank: int | None = None  # community rank within theme/subtheme
    subtheme_avg_growth_pct: float | None = None

    # Future estimate (not scraped -- BrickEconomy forecast, not real data)
    future_estimate_cents: int | None = None
    future_estimate_date: str | None = None

    # Distribution
    distribution_mean_cents: int | None = None
    distribution_stddev_cents: int | None = None

    # Time series (stored as JSON in DB)
    value_chart: tuple[tuple[str, int], ...] = ()
    sales_trend: tuple[tuple[str, int], ...] = ()
    candlestick: tuple[tuple[str, int, int, int, int], ...] = ()


# ---------------------------------------------------------------------------
# Regex patterns for extracting Google Charts inline JS data
# ---------------------------------------------------------------------------

# Value chart: data.addRows([...]) inside drawChart()
_RE_VALUE_CHART = re.compile(
    r"function\s+drawChart\s*\(\)\s*\{.*?addRows\(\s*\[(.*?)\]\s*\)",
    re.DOTALL,
)

# Individual date+price row: new Date(year, month, day), price
_RE_DATE_PRICE = re.compile(
    r"\[new Date\((\d+),\s*(\d+),\s*(\d+)\)\s*,\s*([\d.]+)"
)

# Sales trend chart: drawSalesChart()
_RE_SALES_CHART = re.compile(
    r"function\s+drawSalesChart\s*\(\)\s*\{.*?addRows\(\s*\[(.*?)\]\s*\)",
    re.DOTALL,
)

# Sales trend row: [new Date(y, m, d), count]
_RE_DATE_COUNT = re.compile(
    r"\[new Date\((\d+),\s*(\d+),\s*(\d+)\)\s*,\s*(\d+)\s*\]"
)

# Candlestick chart: drawSalesChartMonth()
_RE_CANDLESTICK_CHART = re.compile(
    r"function\s+drawSalesChartMonth\s*\(\)\s*\{.*?addRows\(\s*\[(.*?)\]\s*\)",
    re.DOTALL,
)

# Candlestick row: [new Date(y,m,d), low, open, close, high, 'tooltip']
_RE_CANDLESTICK_ROW = re.compile(
    r"\[new Date\((\d+),\s*(\d+),\s*(\d+)\)\s*,"
    r"\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)"
)

# Distribution: mean and stddev passed as args to density() call in the for loop
# Pattern: density(i, 148.718..., 32.676...)
_RE_DENSITY_CALL = re.compile(
    r"density\(\w+\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)"
)

# Sparkline growth data (90-day)
_RE_SPARKLINE = re.compile(r"createSparkline\(\[([\d.,\s]+)\]")

# Price from dollar string like "$126.42"
_RE_DOLLAR_AMOUNT = re.compile(r"\$([\d,]+\.?\d*)")

# Annotation rows with "Today" or "Estimate"
_RE_TODAY_ANNOTATION = re.compile(
    r"\[new Date\((\d+),\s*(\d+),\s*(\d+)\)\s*,\s*([\d.]+)\s*,"
    r"\s*'[^']*'\s*,\s*'Today[^']*'"
)
_RE_ESTIMATE_ANNOTATION = re.compile(
    r"\[new Date\((\d+),\s*(\d+),\s*(\d+)\)\s*,\s*([\d.]+)\s*,"
    r"\s*'[^']*'\s*,\s*'Estimate'"
)


_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_month_year(text: str) -> str | None:
    """Parse 'January 2025' or 'October 2021' to ISO month '2025-01'."""
    m = re.match(r"(\w+)\s+(\d{4})", text.strip())
    if not m:
        return None
    month_num = _MONTH_NAMES.get(m.group(1).lower())
    if month_num is None:
        return None
    return f"{int(m.group(2)):04d}-{month_num:02d}"


def _dollars_to_cents(value: float) -> int:
    """Convert a dollar float to integer cents."""
    return round(value * 100)


def _js_date_to_iso(year: int, month_0: int, day: int) -> str:
    """Convert JS Date args (0-indexed month) to ISO date string."""
    return f"{year:04d}-{month_0 + 1:02d}-{day:02d}"


def _js_month_to_iso(year: int, month_0: int) -> str:
    """Convert JS Date year+month (0-indexed) to ISO month string."""
    return f"{year:04d}-{month_0 + 1:02d}"


# ---------------------------------------------------------------------------
# JSON-LD parsing
# ---------------------------------------------------------------------------


def _parse_json_ld(soup: BeautifulSoup) -> dict:
    """Extract JSON-LD structured data from the page."""
    tag = soup.find("script", type="application/ld+json")
    if not tag or not tag.string:
        return {}
    try:
        data = json.loads(tag.string)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    return item
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse JSON-LD")
        return {}


# ---------------------------------------------------------------------------
# Chart data extraction
# ---------------------------------------------------------------------------


def _parse_value_chart(html: str) -> tuple[tuple[str, int], ...]:
    """Extract Set Value (New/Sealed) time series from drawChart().

    Filters out future/forecast data points (dates beyond today).
    """
    match = _RE_VALUE_CHART.search(html)
    if not match:
        logger.debug("Value chart addRows block not found")
        return ()

    rows_block = match.group(1)
    points: list[tuple[str, int]] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for m in _RE_DATE_PRICE.finditer(rows_block):
        year, month_0, day, price = (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            float(m.group(4)),
        )
        iso_date = _js_date_to_iso(year, month_0, day)
        if iso_date > today:
            continue
        points.append((iso_date, _dollars_to_cents(price)))

    return tuple(points)


def _parse_sales_trend(html: str) -> tuple[tuple[str, int], ...]:
    """Extract monthly sale counts from drawSalesChart()."""
    match = _RE_SALES_CHART.search(html)
    if not match:
        logger.debug("Sales trend addRows block not found")
        return ()

    rows_block = match.group(1)
    points: list[tuple[str, int]] = []

    for m in _RE_DATE_COUNT.finditer(rows_block):
        year, month_0, _day, count = (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            int(m.group(4)),
        )
        iso_month = _js_month_to_iso(year, month_0)
        points.append((iso_month, count))

    return tuple(points)


def _parse_candlestick(html: str) -> tuple[tuple[str, int, int, int, int], ...]:
    """Extract monthly OHLC price ranges from drawSalesChartMonth()."""
    match = _RE_CANDLESTICK_CHART.search(html)
    if not match:
        logger.debug("Candlestick addRows block not found")
        return ()

    rows_block = match.group(1)
    points: list[tuple[str, int, int, int, int]] = []

    for m in _RE_CANDLESTICK_ROW.finditer(rows_block):
        year, month_0 = int(m.group(1)), int(m.group(2))
        low = _dollars_to_cents(float(m.group(4)))
        open_ = _dollars_to_cents(float(m.group(5)))
        close = _dollars_to_cents(float(m.group(6)))
        high = _dollars_to_cents(float(m.group(7)))
        iso_month = _js_month_to_iso(year, month_0)
        points.append((iso_month, low, open_, close, high))

    return tuple(points)


def _synthesize_candlestick_from_value_chart(
    value_chart: tuple[tuple[str, int], ...],
) -> tuple[tuple[str, int, int, int, int], ...]:
    """Synthesize monthly OHLC candles from daily/weekly value chart data.

    Groups value_chart points by month and computes open/high/low/close
    for each month. This provides candlestick-equivalent data when the
    old drawSalesChartMonth() function is not present on the page.

    Each output tuple is (iso_month, low, open, close, high) in cents,
    matching the format from _parse_candlestick.
    """
    if not value_chart:
        return ()

    # Group by year-month
    monthly: dict[str, list[int]] = {}
    for date_str, price_cents in value_chart:
        month_key = date_str[:7]  # "YYYY-MM"
        monthly.setdefault(month_key, []).append(price_cents)

    if not monthly:
        return ()

    candles: list[tuple[str, int, int, int, int]] = []
    for month_key in sorted(monthly):
        prices = monthly[month_key]
        open_price = prices[0]
        close_price = prices[-1]
        high_price = max(prices)
        low_price = min(prices)
        # Match old format: (month, low, open, close, high)
        candles.append((month_key, low_price, open_price, close_price, high_price))

    return tuple(candles)


def _parse_distribution(html: str) -> tuple[int | None, int | None]:
    """Extract Gaussian distribution mean and stddev from drawSalesListChart().

    The density function is called as: density(i, MEAN, STDDEV) inside a for loop.
    """
    # Look for the density() call with mean and stddev as literal arguments
    match = _RE_DENSITY_CALL.search(html)
    if not match:
        logger.debug("Distribution density() call not found")
        return None, None

    mean_cents = _dollars_to_cents(float(match.group(1)))
    stddev_cents = _dollars_to_cents(float(match.group(2)))

    return mean_cents, stddev_cents


def _parse_current_value(html: str) -> tuple[int | None, str | None]:
    """Extract today's value and date from chart annotation."""
    match = _RE_TODAY_ANNOTATION.search(html)
    if match:
        price = _dollars_to_cents(float(match.group(4)))
        iso_date = _js_date_to_iso(
            int(match.group(1)), int(match.group(2)), int(match.group(3))
        )
        return price, iso_date
    return None, None


def _parse_future_estimate(html: str) -> tuple[int | None, str | None]:
    """Extract the first future estimate from chart annotations."""
    match = _RE_ESTIMATE_ANNOTATION.search(html)
    if match:
        price = _dollars_to_cents(float(match.group(4)))
        iso_date = _js_date_to_iso(
            int(match.group(1)), int(match.group(2)), int(match.group(3))
        )
        return price, iso_date
    return None, None


# ---------------------------------------------------------------------------
# HTML metadata extraction
# ---------------------------------------------------------------------------


def _parse_sidebar(soup: BeautifulSoup) -> dict:
    """Extract all data from the col-md-4 sidebar containing Set Details.

    The sidebar has a clear key|value sequence after "Set Details":
    Set number, Name, Theme, Subtheme, Year, Availability, Pieces, Minifigs,
    then Set Pricing section with retail price, value, growth, etc.
    """
    result: dict = {}

    sidebar = None
    for div in soup.find_all("div", class_="col-md-4"):
        text = div.get_text("|", strip=True)
        if "Set Details" in text:
            sidebar = text
            break

    if not sidebar:
        logger.debug("Sidebar with Set Details not found")
        return result

    tokens = [t.strip() for t in sidebar.split("|") if t.strip()]

    def _get_after(label: str) -> str | None:
        """Get the token immediately after a label."""
        for i, tok in enumerate(tokens):
            if tok.lower() == label.lower() and i + 1 < len(tokens):
                return tokens[i + 1]
        return None

    # Set details
    result["theme"] = _get_after("Theme")
    result["subtheme"] = _get_after("Subtheme")

    year_str = _get_after("Year")
    if year_str:
        # BrickEconomy shows "2021" for active sets, "2021 - 2023" for retired
        years = re.findall(r"(\d{4})", year_str)
        if years:
            result["year_released"] = int(years[0])
        if len(years) >= 2:
            result["year_retired"] = int(years[1])

    # Release/retired month+year: "Released" -> "January 2025"
    released_str = _get_after("Released")
    if released_str:
        result["release_date"] = _parse_month_year(released_str)

    retired_str = _get_after("Retired")
    if retired_str:
        result["retired_date"] = _parse_month_year(retired_str)

    availability = _get_after("Availability")
    result["availability"] = availability
    if availability:
        avail_lower = availability.lower()
        if "retiring" in avail_lower:
            result["retiring_soon"] = True
        elif avail_lower == "retired":
            result["retiring_soon"] = False

    result["packaging"] = _get_after("Packaging")

    pieces_str = _get_after("Pieces")
    if pieces_str:
        m = re.search(r"([\d,]+)", pieces_str)
        if m:
            result["pieces"] = int(m.group(1).replace(",", ""))

    # Minifigs count + value + exclusivity
    minifigs_str = _get_after("Minifigs")
    if minifigs_str:
        m = re.search(r"(\d+)", minifigs_str)
        if m:
            result["minifigs"] = int(m.group(1))

    # Minifig value appears after minifig count: "(Value $17.73)"
    # Exclusive indicator: "(All exclusive)" or "(X exclusive)"
    for i, tok in enumerate(tokens):
        if tok == "Minifigs" and i + 1 < len(tokens):
            # Scan subsequent tokens for value and exclusivity
            for j in range(i + 1, min(i + 5, len(tokens))):
                val_match = re.search(r"Value\s+\$([\d,.]+\d)", tokens[j])
                if val_match:
                    result["minifig_value_cents"] = _dollars_to_cents(
                        float(val_match.group(1).replace(",", ""))
                    )
                if "exclusive" in tokens[j].lower():
                    result["exclusive_minifigs"] = True
            break

    # Retail price (USD) -- appears after "Retail price" or "retail price"
    retail_str = _get_after("Retail price")
    if not retail_str:
        retail_str = _get_after("retail price")
    if retail_str:
        m = _RE_DOLLAR_AMOUNT.search(retail_str)
        if m:
            result["rrp_usd_cents"] = _dollars_to_cents(
                float(m.group(1).replace(",", ""))
            )

    # Current new/sealed value
    # Look for "New/Sealed" then "Value" then price
    for i, tok in enumerate(tokens):
        if tok == "New/Sealed" and i + 2 < len(tokens) and tokens[i + 1] == "Value":
            m = _RE_DOLLAR_AMOUNT.search(tokens[i + 2])
            if m:
                result["value_new_cents"] = _dollars_to_cents(
                    float(m.group(1).replace(",", ""))
                )
            break

    # Total growth: "+60.01%" after "Growth" (before "Annual growth")
    growth_str = _get_after("Growth")
    if growth_str:
        m = re.search(r"([+-]?\d+\.?\d*)", growth_str)
        if m:
            result["total_growth_pct"] = float(m.group(1))

    # Annual growth
    annual_str = _get_after("Annual growth")
    if annual_str:
        m = re.search(r"([+-]?\d+\.?\d*)", annual_str)
        if m:
            result["annual_growth_pct"] = float(m.group(1))

    # Rolling growth (previous 12 months)
    rolling_str = _get_after("Rolling growth")
    if rolling_str:
        m = re.search(r"([+-]?\d+\.?\d*)", rolling_str)
        if m:
            result["rolling_growth_pct"] = float(m.group(1))

    # 90-day change
    change_90d_str = _get_after("90-day change")
    if change_90d_str:
        m = re.search(r"([+-]?\d+\.?\d*)", change_90d_str)
        if m:
            result["growth_90d_pct"] = float(m.group(1))

    # Used value + range
    for i, tok in enumerate(tokens):
        if tok == "Used" and i + 2 < len(tokens) and tokens[i + 1] == "Value":
            m = _RE_DOLLAR_AMOUNT.search(tokens[i + 2])
            if m:
                result["value_used_cents"] = _dollars_to_cents(
                    float(m.group(1).replace(",", ""))
                )
            break

    # Used value range: "Range" -> "$104.90 - $134.50"
    range_str = _get_after("Range")
    if range_str:
        prices = _RE_DOLLAR_AMOUNT.findall(range_str)
        if len(prices) >= 2:
            result["used_value_low_cents"] = _dollars_to_cents(
                float(prices[0].replace(",", ""))
            )
            result["used_value_high_cents"] = _dollars_to_cents(
                float(prices[1].replace(",", ""))
            )

    return result


def _safe_price_cents(match: re.Match[str] | None) -> int | None:
    """Convert a regex price match to cents, tolerating trailing dots."""
    if match is None:
        return None
    raw = match.group(1).replace(",", "").rstrip(".")
    try:
        return _dollars_to_cents(float(raw))
    except ValueError:
        return None


def _parse_regional_prices(
    soup: BeautifulSoup,
) -> dict[str, int | None]:
    """Extract all regional retail prices from the page."""
    text = soup.get_text()
    prices: dict[str, int | None] = {}

    prices["gbp"] = _safe_price_cents(
        re.search(r"United Kingdom[^£]*£([\d,.]+\d)", text)
    )
    prices["eur"] = _safe_price_cents(
        re.search(r"Europe[^€]*€([\d,.]+\d)", text)
    )
    # Canada uses $ symbol -- look for "Canada" then next dollar amount
    prices["cad"] = _safe_price_cents(
        re.search(r"Canada[^$]*\$([\d,.]+\d)", text)
    )
    # Australia uses $ symbol
    prices["aud"] = _safe_price_cents(
        re.search(r"Australia[^$]*\$([\d,.]+\d)", text)
    )

    return prices


def _parse_barcodes(sidebar_tokens: list[str]) -> tuple[str | None, str | None]:
    """Extract UPC and EAN barcodes from sidebar tokens."""
    upc = None
    ean = None
    for i, tok in enumerate(sidebar_tokens):
        if tok == "UPC" and i + 1 < len(sidebar_tokens):
            m = re.match(r"(\d{10,14})", sidebar_tokens[i + 1])
            if m:
                upc = m.group(1)
        elif tok == "EAN" and i + 1 < len(sidebar_tokens):
            m = re.match(r"(\d{10,14})", sidebar_tokens[i + 1])
            if m:
                ean = m.group(1)
    return upc, ean


def _parse_designer(sidebar_tokens: list[str]) -> str | None:
    """Extract designer name(s) from sidebar tokens.

    Pattern: "... was designed by LEGO designer(s)" followed by name tokens,
    possibly with "and" between multiple designers, ending with ".".
    """
    # Find the "designed by" anchor
    for i, tok in enumerate(sidebar_tokens):
        if "designed by" in tok.lower():
            names: list[str] = []
            for j in range(i + 1, min(i + 6, len(sidebar_tokens))):
                t = sidebar_tokens[j].strip().rstrip(".")
                if t == "and":
                    continue
                if t == "." or not t:
                    break
                # Stop at tokens that don't look like names
                if t.startswith("The ") or t.startswith("Regional"):
                    break
                names.append(t)
            return ", ".join(names) if names else None
    return None


def _parse_theme_rank(sidebar_tokens: list[str]) -> int | None:
    """Extract community rank within theme/subtheme.

    Pattern: "... currently ranks #3 out of ..."
    """
    for tok in sidebar_tokens:
        m = re.search(r"currently ranks #(\d+)", tok)
        if m:
            return int(m.group(1))
    return None


def _parse_subtheme_avg_growth(sidebar_tokens: list[str]) -> float | None:
    """Extract subtheme/theme average annual growth.

    Pattern: "(this set +11.02%)" is the set's own, but before it
    there's the subtheme avg like "+12.41%".
    Look for "Annual growth" in the Subtheme Analysis section.
    """
    # The subtheme analysis has tokens like:
    # "Annual growth", "+12.41%", "(this set +11.02%)"
    in_subtheme = False
    for i, tok in enumerate(sidebar_tokens):
        if "Analysis" in tok:
            in_subtheme = True
        if in_subtheme and tok == "Annual growth" and i + 1 < len(sidebar_tokens):
            m = re.search(r"([+-]?\d+\.?\d*)", sidebar_tokens[i + 1])
            if m:
                return float(m.group(1))
    return None


def _parse_value_from_meta(soup: BeautifulSoup) -> int | None:
    """Extract current value from meta description as fallback."""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        match = _RE_DOLLAR_AMOUNT.search(meta["content"])
        if match:
            return _dollars_to_cents(float(match.group(1).replace(",", "")))
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_brickeconomy_page(
    html: str,
    set_number: str,
    *,
    url: str | None = None,
) -> BrickeconomySnapshot:
    """Parse a BrickEconomy set page and extract all available data.

    Args:
        html: Raw HTML of the page.
        set_number: LEGO set number (e.g. "40346-1").
        url: The final URL after redirects (stored as brickeconomy_url).

    Returns:
        BrickeconomySnapshot with all extracted fields.
    """
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now(timezone.utc)

    # JSON-LD structured data
    ld = _parse_json_ld(soup)
    title = ld.get("name")
    image_raw = ld.get("image")
    # image can be a string or a list of strings
    if isinstance(image_raw, list):
        image_url = image_raw[0] if image_raw else None
    else:
        image_url = image_raw

    # Rating from JSON-LD
    agg_rating = ld.get("aggregateRating", {})
    rating_value = agg_rating.get("ratingValue")
    review_count_raw = agg_rating.get("reviewCount")
    review_count = int(review_count_raw) if review_count_raw else None

    # Sidebar metadata (set details, pricing, growth)
    sidebar = _parse_sidebar(soup)

    # Sidebar tokens for secondary parsers (barcodes, designer, rank, growth)
    sidebar_tokens: list[str] = []
    for div in soup.find_all("div", class_="col-md-4"):
        text = div.get_text("|", strip=True)
        if "Set Details" in text:
            sidebar_tokens = [t.strip() for t in text.split("|") if t.strip()]
            break

    # Chart data (from inline JS)
    value_chart = _parse_value_chart(html)
    sales_trend = _parse_sales_trend(html)
    candlestick = _parse_candlestick(html)

    # Fallback: synthesize candlestick from value chart when the old
    # drawSalesChartMonth() function is absent (newer BE pages).
    if not candlestick and value_chart:
        candlestick = _synthesize_candlestick_from_value_chart(value_chart)
        if candlestick:
            logger.debug(
                "Synthesized %d monthly candles from value chart for %s",
                len(candlestick), set_number,
            )

    dist_mean, dist_stddev = _parse_distribution(html)

    # Current value: prefer sidebar, then chart annotation, then meta
    value_new_cents = sidebar.get("value_new_cents")
    if value_new_cents is None:
        value_new_cents, _today_date = _parse_current_value(html)
    if value_new_cents is None:
        value_new_cents = _parse_value_from_meta(soup)

    # Future estimates are BrickEconomy forecasts, not real data -- skip
    future_cents, future_date = None, None

    # Regional retail prices (GBP, EUR, CAD, AUD)
    rrp_usd = sidebar.get("rrp_usd_cents")
    regional = _parse_regional_prices(soup)

    # Barcodes, designer, theme rank, subtheme growth
    upc, ean = _parse_barcodes(sidebar_tokens)
    designer = _parse_designer(sidebar_tokens)
    theme_rank = _parse_theme_rank(sidebar_tokens)
    subtheme_avg_growth = _parse_subtheme_avg_growth(sidebar_tokens)

    return BrickeconomySnapshot(
        set_number=set_number,
        scraped_at=now,
        title=title,
        theme=sidebar.get("theme"),
        subtheme=sidebar.get("subtheme"),
        year_released=sidebar.get("year_released"),
        year_retired=sidebar.get("year_retired"),
        release_date=sidebar.get("release_date"),
        retired_date=sidebar.get("retired_date"),
        pieces=sidebar.get("pieces"),
        minifigs=sidebar.get("minifigs"),
        minifig_value_cents=sidebar.get("minifig_value_cents"),
        exclusive_minifigs=sidebar.get("exclusive_minifigs"),
        availability=sidebar.get("availability"),
        retiring_soon=sidebar.get("retiring_soon"),
        packaging=sidebar.get("packaging"),
        image_url=image_url,
        brickeconomy_url=url,
        upc=upc,
        ean=ean,
        designer=designer,
        rrp_usd_cents=rrp_usd,
        rrp_gbp_cents=regional["gbp"],
        rrp_eur_cents=regional["eur"],
        rrp_cad_cents=regional["cad"],
        rrp_aud_cents=regional["aud"],
        value_new_cents=value_new_cents,
        value_used_cents=sidebar.get("value_used_cents"),
        used_value_low_cents=sidebar.get("used_value_low_cents"),
        used_value_high_cents=sidebar.get("used_value_high_cents"),
        annual_growth_pct=sidebar.get("annual_growth_pct"),
        total_growth_pct=sidebar.get("total_growth_pct"),
        rolling_growth_pct=sidebar.get("rolling_growth_pct"),
        growth_90d_pct=sidebar.get("growth_90d_pct"),
        rating_value=rating_value,
        review_count=review_count,
        theme_rank=theme_rank,
        subtheme_avg_growth_pct=subtheme_avg_growth,
        future_estimate_cents=future_cents,
        future_estimate_date=future_date,
        distribution_mean_cents=dist_mean,
        distribution_stddev_cents=dist_stddev,
        value_chart=value_chart,
        sales_trend=sales_trend,
        candlestick=candlestick,
    )
