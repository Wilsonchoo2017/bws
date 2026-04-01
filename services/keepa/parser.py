"""Keepa page data extraction.

Extracts price statistics and product info from the Keepa product page DOM.
Keepa loads chart data via a proprietary binary protocol (graph.keepa.com),
so we scrape the visible statistics tables and product info instead.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page

from services.keepa.types import KeepaDataPoint, KeepaProductData

logger = logging.getLogger("bws.keepa.parser")


def _parse_price(text: str) -> int | None:
    """Parse a price string like '$ 63.10' into cents."""
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if not match:
        return None
    price_str = match.group(1).replace(",", "")
    try:
        return int(float(price_str) * 100)
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    """Parse a date string like 'Nov 25, 2022' into ISO format."""
    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})",
        text,
    )
    if not match:
        return None
    months = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    month = months[match.group(1)]
    day = int(match.group(2))
    year = int(match.group(3))
    return f"{year:04d}-{month:02d}-{day:02d}"


async def extract_product_data(page: Page, set_number: str) -> KeepaProductData:
    """Extract all available product data from the Keepa product page DOM.

    Scrapes:
    - Product title, ASIN from header/URL
    - Buy Box and New prices from the info bar
    - Statistics table: lowest/current/highest for each price type
    - 90-day and 180-day averages
    - Price drop tracking alerts table
    """
    raw = await page.evaluate(_EXTRACT_JS)

    asin = raw.get("asin")
    title = raw.get("title")
    keepa_url = f"https://keepa.com/#!product/1-{asin}" if asin else page.url

    # Parse header prices
    buy_box_cents = _parse_price(raw.get("buyBox", ""))
    new_cents = _parse_price(raw.get("newPrice", ""))

    # Parse statistics rows
    stats = raw.get("stats", {})

    amazon_lowest = _parse_price(stats.get("amazon_lowest", ""))
    amazon_current = _parse_price(stats.get("amazon_current", ""))
    amazon_highest = _parse_price(stats.get("amazon_highest", ""))

    new_lowest = _parse_price(stats.get("new_lowest", ""))
    new_current = _parse_price(stats.get("new_current", ""))
    new_highest = _parse_price(stats.get("new_highest", ""))
    new_90d_avg = _parse_price(stats.get("new_90d_avg", ""))
    new_180d_avg = _parse_price(stats.get("new_180d_avg", ""))
    new_drops_per_month = stats.get("new_drops_per_month")

    used_lowest = _parse_price(stats.get("used_lowest", ""))
    used_current = _parse_price(stats.get("used_current", ""))
    used_highest = _parse_price(stats.get("used_highest", ""))

    # Build summary data points for lowest/current/highest
    amazon_points = _build_points(amazon_lowest, amazon_current, amazon_highest, stats, "amazon")
    new_points = _build_points(new_lowest, new_current, new_highest, stats, "new")
    used_points = _build_points(used_lowest, used_current, used_highest, stats, "used")

    # Buy Box stats
    bb_current = buy_box_cents
    bb_lowest_3m = _parse_price(stats.get("bb_lowest_3m", ""))
    bb_lowest_6m = _parse_price(stats.get("bb_lowest_6m", ""))
    bb_lowest_ever = _parse_price(stats.get("bb_lowest_ever", ""))
    bb_highest_ever = _parse_price(stats.get("bb_highest_ever", ""))
    bb_90d_avg = _parse_price(stats.get("bb_90d_avg", ""))
    bb_points = _build_points(bb_lowest_ever, bb_current, bb_highest_ever, stats, "bb")

    # FBA stats
    fba_current = _parse_price(stats.get("fba_current", ""))
    fba_lowest = _parse_price(stats.get("fba_lowest_ever", ""))
    fba_highest = _parse_price(stats.get("fba_highest_ever", ""))
    fba_points = _build_points(fba_lowest, fba_current, fba_highest, stats, "fba")

    # FBM stats
    fbm_current = _parse_price(stats.get("fbm_current", ""))
    fbm_lowest = _parse_price(stats.get("fbm_lowest_ever", ""))
    fbm_highest = _parse_price(stats.get("fbm_highest_ever", ""))
    fbm_points = _build_points(fbm_lowest, fbm_current, fbm_highest, stats, "fbm")

    # List price
    list_current = _parse_price(stats.get("list_current", ""))

    # Determine overall lowest/highest
    all_lows = [v for v in [amazon_lowest, new_lowest, bb_lowest_ever] if v]
    all_highs = [v for v in [amazon_highest, new_highest, bb_highest_ever] if v]

    # Parse rating, reviews, tracking
    rating = raw.get("rating")
    review_count = raw.get("reviewCount")
    tracking_users = raw.get("trackingUsers")

    return KeepaProductData(
        set_number=set_number,
        asin=asin,
        title=title,
        keepa_url=keepa_url,
        scraped_at=datetime.now(tz=timezone.utc),
        amazon_price=amazon_points,
        new_price=new_points,
        new_3p_fba=fba_points,
        new_3p_fbm=fbm_points,
        used_price=used_points,
        used_like_new=(),
        buy_box=bb_points,
        list_price=_build_points(list_current, list_current, list_current, stats, "list"),
        warehouse_deals=(),
        collectible=(),
        sales_rank=(),
        current_buy_box_cents=buy_box_cents,
        current_amazon_cents=amazon_current,
        current_new_cents=new_current or new_cents,
        lowest_ever_cents=min(all_lows) if all_lows else None,
        highest_ever_cents=max(all_highs) if all_highs else None,
        rating=rating,
        review_count=review_count,
        tracking_users=tracking_users,
    )


def _build_points(
    lowest: int | None,
    current: int | None,
    highest: int | None,
    stats: dict[str, Any],
    prefix: str,
) -> tuple[KeepaDataPoint, ...]:
    """Build data points from lowest/current/highest values."""
    points: list[KeepaDataPoint] = []
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    lowest_date = _parse_date(stats.get(f"{prefix}_lowest", ""))
    highest_date = _parse_date(stats.get(f"{prefix}_highest", ""))

    if lowest is not None:
        points.append(KeepaDataPoint(date=lowest_date or "unknown", value=lowest))
    if current is not None:
        points.append(KeepaDataPoint(date=today, value=current))
    if highest is not None and highest != current:
        points.append(KeepaDataPoint(date=highest_date or "unknown", value=highest))

    return tuple(points)


# JavaScript to extract data from the Keepa product page DOM
_EXTRACT_JS = """() => {
    const result = {};

    // ASIN from URL hash
    const hashMatch = window.location.hash.match(/product\\/\\d+-([A-Z0-9]{10})/);
    if (hashMatch) result.asin = hashMatch[1];

    // Product info text
    const infoBox = document.querySelector('#productInfoBox');
    if (infoBox) {
        const infoText = infoBox.textContent || '';

        // Title: text before the star rating
        const titleMatch = infoText.match(/^(.+?)\\s*\\d+\\.\\d+\\s*\\(/);
        if (titleMatch) result.title = titleMatch[1].trim();

        // Buy Box price
        const bbMatch = infoText.match(/Buy Box:\\s*\\$\\s*([\\d,.]+)/);
        if (bbMatch) result.buyBox = '$ ' + bbMatch[1];

        // New price
        const newMatch = infoText.match(/New:\\s*\\$\\s*([\\d,.]+)/);
        if (newMatch) result.newPrice = '$ ' + newMatch[1];
    }

    // Parse the statistics table
    // The table has rows like:
    //   | Amazon | New | Used | Sales Rank |
    //   | Lowest | $19.99 Nov 25, 2022 | $19.99 Nov 24, 2022 | ... |
    //   | Current | Out of stock | $49.99 | ... |
    //   | Highest | $29.99 | $64.00 | ... |
    //   | Average | - | $54.28 last 90 days | ... |
    const stats = {};
    const rows = document.querySelectorAll('tr');

    for (const row of rows) {
        if (!row.offsetParent) continue;
        const cells = Array.from(row.querySelectorAll('td, th'));
        if (cells.length < 2) continue;

        const firstCell = (cells[0].textContent || '').trim();

        // Header row: Amazon | New | Used | Sales Rank
        if (firstCell === 'Amazon' && cells.some(c => c.textContent.trim() === 'New')) {
            // This is the column header row - map column indices
            const colMap = {};
            cells.forEach((c, i) => {
                const t = c.textContent.trim();
                if (t) colMap[t] = i;
            });
            stats._colMap = colMap;
            continue;
        }

        // Data rows
        const colMap = stats._colMap || {};
        const amazonIdx = colMap['Amazon'];
        const newIdx = colMap['New'];
        const usedIdx = colMap['Used'];

        if (firstCell === 'Lowest') {
            if (amazonIdx !== undefined && cells[amazonIdx])
                stats.amazon_lowest = cells[amazonIdx].textContent.trim();
            if (newIdx !== undefined && cells[newIdx])
                stats.new_lowest = cells[newIdx].textContent.trim();
            if (usedIdx !== undefined && cells[usedIdx])
                stats.used_lowest = cells[usedIdx].textContent.trim();
        }

        if (firstCell === 'Current') {
            if (amazonIdx !== undefined && cells[amazonIdx])
                stats.amazon_current = cells[amazonIdx].textContent.trim();
            if (newIdx !== undefined && cells[newIdx])
                stats.new_current = cells[newIdx].textContent.trim();
            if (usedIdx !== undefined && cells[usedIdx])
                stats.used_current = cells[usedIdx].textContent.trim();
        }

        if (firstCell === 'Highest') {
            if (amazonIdx !== undefined && cells[amazonIdx])
                stats.amazon_highest = cells[amazonIdx].textContent.trim();
            if (newIdx !== undefined && cells[newIdx])
                stats.new_highest = cells[newIdx].textContent.trim();
            if (usedIdx !== undefined && cells[usedIdx])
                stats.used_highest = cells[usedIdx].textContent.trim();
        }

        if (firstCell === 'Average') {
            if (newIdx !== undefined && cells[newIdx]) {
                const avgText = cells[newIdx].textContent.trim();
                const m90 = avgText.match(/\\$\\s*([\\d,.]+).*last 90 days/);
                if (m90) stats.new_90d_avg = '$ ' + m90[1];
                const m180 = avgText.match(/\\$\\s*([\\d,.]+).*last 180 days/);
                if (m180) stats.new_180d_avg = '$ ' + m180[1];
            }
        }
    }

    // Parse Buy Box / FBA / FBM price tracking tables
    // These are separate tables with "Current | $XX | Discount | Price" format
    const trackingTables = document.querySelectorAll('tr');
    let currentSection = '';
    let sectionIndex = 0;

    for (const row of trackingTables) {
        if (!row.offsetParent) continue;
        const cells = Array.from(row.querySelectorAll('td'));
        if (cells.length < 2) continue;

        const firstText = (cells[0].textContent || '').trim();
        const secondText = (cells[1].textContent || '').trim();

        // Track which section we're in by counting "Current" rows
        if (firstText === 'Current' && secondText.includes('$')) {
            sectionIndex++;
            const price = secondText;

            // Section mapping based on order:
            // 1: Buy Box, 2: Amazon, 3: New, 4: FBA, 5: FBM
            if (sectionIndex === 1) stats.bb_current_track = price;
            if (sectionIndex === 4) stats.fba_current = price;
            if (sectionIndex === 5) stats.fbm_current = price;
        }

        if (firstText === 'Lowest ever') {
            const price = secondText;
            if (sectionIndex === 1) stats.bb_lowest_ever = price;
            if (sectionIndex === 4) stats.fba_lowest_ever = price;
            if (sectionIndex === 5) stats.fbm_lowest_ever = price;
        }

        if (firstText === 'Highest ever') {
            const price = secondText;
            if (sectionIndex === 1) stats.bb_highest_ever = price;
            if (sectionIndex === 4) stats.fba_highest_ever = price;
            if (sectionIndex === 5) stats.fbm_highest_ever = price;
        }

        if (firstText === 'Lowest 3 months') {
            if (sectionIndex === 1) stats.bb_lowest_3m = secondText;
        }

        if (firstText === 'Lowest 6 months') {
            if (sectionIndex === 1) stats.bb_lowest_6m = secondText;
        }

        if (firstText === '90 days average') {
            if (sectionIndex === 1) stats.bb_90d_avg = secondText;
        }
    }

    // Remove internal column map
    delete stats._colMap;
    result.stats = stats;

    // Rating and review count from header (e.g. "4.8 (2,731 reviews)")
    const fullText = document.querySelector('#productInfoBox')?.textContent || '';
    const ratingMatch = fullText.match(/(\\d+\\.\\d+)\\s*\\((\\d[\\d,]*)\\s*reviews?\\)/);
    if (ratingMatch) {
        result.rating = parseFloat(ratingMatch[1]);
        result.reviewCount = parseInt(ratingMatch[2].replace(/,/g, ''), 10);
    }

    // Tracking users (e.g. "41 users are tracking this product")
    const bodyText = document.body.textContent || '';
    const trackMatch = bodyText.match(/(\\d+)\\s+users?\\s+are\\s+tracking/);
    if (trackMatch) {
        result.trackingUsers = parseInt(trackMatch[1], 10);
    }

    // X-axis tick labels with positions for year inference
    const xTicks = [];
    const tickLabels = document.querySelectorAll('.tickLabel');
    for (const el of tickLabels) {
        const text = (el.textContent || '').trim();
        const rect = el.getBoundingClientRect();
        const m = text.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+(\\d{4})/);
        if (m) {
            xTicks.push({
                text: text,
                x: Math.round(rect.x + rect.width / 2),
                y: Math.round(rect.y),
                month: m[1],
                year: parseInt(m[2], 10),
            });
        }
    }
    result.xTicks = xTicks;

    // "All (1915 days)" -- extract total days for date range calculation
    const rangeCells = document.querySelectorAll('td.legendRange');
    for (const c of rangeCells) {
        const t = c.textContent.trim();
        const daysMatch = t.match(/All\\s*\\((\\d+)\\s*days?\\)/);
        if (daysMatch) {
            result.totalDays = parseInt(daysMatch[1], 10);
            break;
        }
    }

    return result;
}"""


async def click_all_date_range(page: Page) -> bool:
    """Click Year then All to load full price history.

    Keepa shows the 'All' option only after clicking 'Year' first.
    Uses JavaScript clicks to avoid Playwright timeouts.
    """
    try:
        # Click Year first
        await page.evaluate("""() => {
            const cells = document.querySelectorAll('td.legendRange');
            for (const c of cells) {
                if (c.textContent.trim() === 'Year') {
                    c.click();
                    return true;
                }
            }
            return false;
        }""")
        await page.wait_for_timeout(2_000)

        # Now click All
        clicked = await page.evaluate("""() => {
            const cells = document.querySelectorAll('td.legendRange');
            for (const c of cells) {
                if (c.textContent.trim().startsWith('All')) {
                    c.click();
                    return true;
                }
            }
            return false;
        }""")

        if clicked:
            logger.info("Selected 'All' date range")
        else:
            logger.warning("Could not find 'All' date range button")

        return bool(clicked)
    except Exception:
        logger.debug("Failed to click date range buttons")
        return False
