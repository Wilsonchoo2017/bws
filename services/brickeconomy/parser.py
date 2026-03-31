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

    # Future estimate
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

# Distribution: mean and stddev near drawSalesListChart
_RE_DISTRIBUTION_MEAN = re.compile(
    r"(?:mean|mu)\s*(?:=|:)\s*([\d.]+)", re.IGNORECASE
)
_RE_DISTRIBUTION_STDDEV = re.compile(
    r"(?:stddev|sigma|sd)\s*(?:=|:)\s*([\d.]+)", re.IGNORECASE
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
    """Extract Set Value (New/Sealed) time series from drawChart()."""
    match = _RE_VALUE_CHART.search(html)
    if not match:
        logger.debug("Value chart addRows block not found")
        return ()

    rows_block = match.group(1)
    points: list[tuple[str, int]] = []

    for m in _RE_DATE_PRICE.finditer(rows_block):
        year, month_0, day, price = (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            float(m.group(4)),
        )
        iso_date = _js_date_to_iso(year, month_0, day)
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
    """Extract Gaussian distribution mean and stddev from drawSalesListChart()."""
    # Look for the distribution function block
    dist_block_match = re.search(
        r"function\s+drawSalesListChart\s*\(\)\s*\{(.*?)\n\s*\}",
        html,
        re.DOTALL,
    )
    if not dist_block_match:
        return None, None

    block = dist_block_match.group(1)

    mean_match = _RE_DISTRIBUTION_MEAN.search(block)
    stddev_match = _RE_DISTRIBUTION_STDDEV.search(block)

    mean_cents = _dollars_to_cents(float(mean_match.group(1))) if mean_match else None
    stddev_cents = (
        _dollars_to_cents(float(stddev_match.group(1))) if stddev_match else None
    )

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


def _parse_set_details(soup: BeautifulSoup) -> dict:
    """Extract set metadata from HTML sections."""
    details: dict = {}

    # Look for detail rows (typically dt/dd or label/value pairs)
    for row in soup.select(".row.no-margin"):
        label_el = row.select_one(".col-xs-6:first-child, .text-muted")
        value_el = row.select_one(".col-xs-6:last-child, .col-xs-6 + .col-xs-6")
        if not label_el or not value_el:
            continue

        label = label_el.get_text(strip=True).lower()
        value = value_el.get_text(strip=True)

        if "piece" in label:
            match = re.search(r"([\d,]+)", value)
            if match:
                details["pieces"] = int(match.group(1).replace(",", ""))
        elif "minifig" in label:
            match = re.search(r"(\d+)", value)
            if match:
                details["minifigs"] = int(match.group(1))
        elif "theme" in label and "subtheme" not in label:
            details["theme"] = value
        elif "subtheme" in label:
            details["subtheme"] = value
        elif "year" in label:
            match = re.search(r"(\d{4})", value)
            if match:
                details["year_released"] = int(match.group(1))
        elif "availab" in label or "status" in label:
            details["availability"] = value

    # Fallback: look for availability in specific sections
    if "availability" not in details:
        avail_el = soup.find(string=re.compile(r"Retired|Available|Exclusive"))
        if avail_el:
            text = avail_el.strip()
            if text in ("Retired", "Available", "Exclusive"):
                details["availability"] = text

    return details


def _parse_retail_prices(soup: BeautifulSoup) -> dict:
    """Extract retail/RRP prices from the Retail Price section."""
    prices: dict = {}
    text = soup.get_text()

    # USD RRP
    usd_match = re.search(r"(?:RRP|MSRP|Retail)[^$]*\$([\d,.]+)", text)
    if usd_match:
        prices["rrp_usd_cents"] = _dollars_to_cents(
            float(usd_match.group(1).replace(",", ""))
        )

    # GBP RRP
    gbp_match = re.search(r"\xa3([\d,.]+)", text)
    if gbp_match:
        prices["rrp_gbp_cents"] = _dollars_to_cents(
            float(gbp_match.group(1).replace(",", ""))
        )

    # EUR RRP
    eur_match = re.search(r"\u20ac([\d,.]+)", text)
    if eur_match:
        prices["rrp_eur_cents"] = _dollars_to_cents(
            float(eur_match.group(1).replace(",", ""))
        )

    return prices


def _parse_annual_growth(soup: BeautifulSoup) -> float | None:
    """Extract annual growth percentage."""
    text = soup.get_text()
    match = re.search(r"([-+]?\d+\.?\d*)%\s*(?:annual|yearly|growth)", text, re.I)
    if match:
        return float(match.group(1))
    # Try reverse: "annual growth X%"
    match = re.search(r"(?:annual|yearly)\s+growth[^%]*?([-+]?\d+\.?\d*)%", text, re.I)
    if match:
        return float(match.group(1))
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
    image_url = ld.get("image")

    # Rating from JSON-LD
    agg_rating = ld.get("aggregateRating", {})
    rating_value = agg_rating.get("ratingValue")
    review_count_raw = agg_rating.get("reviewCount")
    review_count = int(review_count_raw) if review_count_raw else None

    # HTML metadata
    details = _parse_set_details(soup)
    retail = _parse_retail_prices(soup)

    # Chart data (from inline JS)
    value_chart = _parse_value_chart(html)
    sales_trend = _parse_sales_trend(html)
    candlestick = _parse_candlestick(html)
    dist_mean, dist_stddev = _parse_distribution(html)

    # Current value: prefer chart annotation, fallback to meta
    value_new_cents, _today_date = _parse_current_value(html)
    if value_new_cents is None:
        value_new_cents = _parse_value_from_meta(soup)

    # Future estimate
    future_cents, future_date = _parse_future_estimate(html)

    # Annual growth
    annual_growth = _parse_annual_growth(soup)

    return BrickeconomySnapshot(
        set_number=set_number,
        scraped_at=now,
        title=title,
        theme=details.get("theme"),
        subtheme=details.get("subtheme"),
        year_released=details.get("year_released"),
        pieces=details.get("pieces"),
        minifigs=details.get("minifigs"),
        availability=details.get("availability"),
        image_url=image_url,
        brickeconomy_url=url,
        rrp_usd_cents=retail.get("rrp_usd_cents"),
        rrp_gbp_cents=retail.get("rrp_gbp_cents"),
        rrp_eur_cents=retail.get("rrp_eur_cents"),
        value_new_cents=value_new_cents,
        value_used_cents=None,
        annual_growth_pct=annual_growth,
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
