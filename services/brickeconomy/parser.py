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
    pieces: int | None = None
    minifigs: int | None = None
    availability: str | None = None
    image_url: str | None = None
    brickeconomy_url: str | None = None

    # Retail prices (cents)
    rrp_usd_cents: int | None = None
    rrp_gbp_cents: int | None = None
    rrp_eur_cents: int | None = None

    # Current market values (cents USD)
    value_new_cents: int | None = None
    value_used_cents: int | None = None

    # Metrics
    annual_growth_pct: float | None = None
    rating_value: str | None = None
    review_count: int | None = None

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
        m = re.search(r"(\d{4})", year_str)
        if m:
            result["year_released"] = int(m.group(1))

    result["availability"] = _get_after("Availability")

    pieces_str = _get_after("Pieces")
    if pieces_str:
        m = re.search(r"([\d,]+)", pieces_str)
        if m:
            result["pieces"] = int(m.group(1).replace(",", ""))

    minifigs_str = _get_after("Minifigs")
    if minifigs_str:
        m = re.search(r"(\d+)", minifigs_str)
        if m:
            result["minifigs"] = int(m.group(1))

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

    # Used value
    for i, tok in enumerate(tokens):
        if tok == "Used" and i + 2 < len(tokens) and tokens[i + 1] == "Value":
            m = _RE_DOLLAR_AMOUNT.search(tokens[i + 2])
            if m:
                result["value_used_cents"] = _dollars_to_cents(
                    float(m.group(1).replace(",", ""))
                )
            break

    # Annual growth
    annual_str = _get_after("Annual growth")
    if annual_str:
        m = re.search(r"([+-]?\d+\.?\d*)", annual_str)
        if m:
            result["annual_growth_pct"] = float(m.group(1))

    return result


def _parse_rrp_gbp_eur(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    """Extract GBP and EUR retail prices from the page."""
    text = soup.get_text()

    gbp_cents = None
    gbp_match = re.search(r"United Kingdom[^£]*£([\d,.]+)", text)
    if gbp_match:
        gbp_cents = _dollars_to_cents(float(gbp_match.group(1).replace(",", "")))

    eur_cents = None
    eur_match = re.search(r"Europe[^€]*€([\d,.]+)", text)
    if eur_match:
        eur_cents = _dollars_to_cents(float(eur_match.group(1).replace(",", "")))

    return gbp_cents, eur_cents


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

    # Chart data (from inline JS)
    value_chart = _parse_value_chart(html)
    sales_trend = _parse_sales_trend(html)
    candlestick = _parse_candlestick(html)
    dist_mean, dist_stddev = _parse_distribution(html)

    # Current value: prefer sidebar, then chart annotation, then meta
    value_new_cents = sidebar.get("value_new_cents")
    if value_new_cents is None:
        value_new_cents, _today_date = _parse_current_value(html)
    if value_new_cents is None:
        value_new_cents = _parse_value_from_meta(soup)

    # Future estimates are BrickEconomy forecasts, not real data -- skip
    future_cents, future_date = None, None

    # RRP: sidebar has USD RRP; GBP/EUR from the full page text
    rrp_usd = sidebar.get("rrp_usd_cents")
    rrp_gbp, rrp_eur = _parse_rrp_gbp_eur(soup)

    return BrickeconomySnapshot(
        set_number=set_number,
        scraped_at=now,
        title=title,
        theme=sidebar.get("theme"),
        subtheme=sidebar.get("subtheme"),
        year_released=sidebar.get("year_released"),
        pieces=sidebar.get("pieces"),
        minifigs=sidebar.get("minifigs"),
        availability=sidebar.get("availability"),
        image_url=image_url,
        brickeconomy_url=url,
        rrp_usd_cents=rrp_usd,
        rrp_gbp_cents=rrp_gbp,
        rrp_eur_cents=rrp_eur,
        value_new_cents=value_new_cents,
        value_used_cents=sidebar.get("value_used_cents"),
        annual_growth_pct=sidebar.get("annual_growth_pct"),
        rating_value=rating_value,
        review_count=review_count,
        future_estimate_cents=future_cents,
        future_estimate_date=future_date,
        distribution_mean_cents=dist_mean,
        distribution_stddev_cents=dist_stddev,
        value_chart=value_chart,
        sales_trend=sales_trend,
        candlestick=candlestick,
    )
