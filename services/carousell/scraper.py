"""Carousell Malaysia search scraper with API interception.

Uses Playwright + Camoufox to load the search page, bypass Cloudflare,
and intercept the internal search API response for structured JSON data.
Sends an ntfy notification when a Cloudflare challenge requires human help.
"""

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Union

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import BrowserContext, Page, Response

from config.settings import CAROUSELL_CONFIG
from services.notifications.ntfy import NtfyMessage, send_notification

logger = logging.getLogger("bws.carousell.scraper")

CAROUSELL_BASE = "https://www.carousell.com.my"
CAROUSELL_SEARCH_API = "/api-service/filter/cf/4.0/search/"

# Cloudflare challenge indicators
CF_CHALLENGE_TITLES = ("just a moment", "attention required", "checking your browser")


@dataclass(frozen=True)
class CarousellListing:
    """A single Carousell listing."""

    listing_id: str
    title: str
    price: str
    condition: str | None
    seller_name: str | None
    image_url: str | None
    listing_url: str
    time_ago: str | None


@dataclass(frozen=True)
class CarousellScrapeResult:
    """Result of a Carousell scrape operation."""

    success: bool
    query: str
    listings: tuple[CarousellListing, ...] = ()
    total_count: int = 0
    error: str | None = None


async def _human_delay(min_ms: int = 800, max_ms: int = 2500) -> None:
    """Random delay to simulate human timing."""
    delay_s = (min_ms + secrets.randbelow(max_ms - min_ms + 1)) / 1000.0
    await asyncio.sleep(delay_s)


async def _carousell_browser() -> AsyncCamoufox:
    """Create a Camoufox browser context for Carousell."""
    user_data_path = Path(CAROUSELL_CONFIG.user_data_dir).expanduser()
    user_data_path.mkdir(parents=True, exist_ok=True)

    return AsyncCamoufox(
        headless=CAROUSELL_CONFIG.headless,
        geoip=True,
        locale=CAROUSELL_CONFIG.locale,
        os="macos",
        humanize=True,
        persistent_context=True,
        user_data_dir=str(user_data_path),
        window=(CAROUSELL_CONFIG.viewport_width, CAROUSELL_CONFIG.viewport_height),
    )


def _notify_captcha(query: str) -> None:
    """Send ntfy notification asking user to solve a Cloudflare challenge."""
    send_notification(
        NtfyMessage(
            title="Carousell: Cloudflare challenge",
            message=(
                f"Carousell search for '{query}' hit a Cloudflare challenge. "
                "Please open the browser window and solve the captcha."
            ),
            priority=5,
            tags=("warning", "robot"),
        )
    )


async def _detect_cloudflare(page: Page) -> bool:
    """Check if the current page is a Cloudflare challenge."""
    try:
        title = await page.title()
        return any(cf in title.lower() for cf in CF_CHALLENGE_TITLES)
    except Exception:
        return False


async def _wait_for_cloudflare(page: Page, query: str, timeout_s: int = 120) -> bool:
    """Wait for a Cloudflare challenge to be solved.

    Sends an ntfy notification, then polls until the challenge page
    is gone or the timeout is reached.

    Returns True if challenge was solved, False on timeout.
    """
    logger.warning("Cloudflare challenge detected for query: %s", query)
    _notify_captcha(query)

    elapsed = 0
    poll_interval = 3
    while elapsed < timeout_s:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        if not await _detect_cloudflare(page):
            logger.info("Cloudflare challenge solved after %ds", elapsed)
            return True

    logger.error("Cloudflare challenge timeout after %ds for query: %s", timeout_s, query)
    return False


def _parse_listing(card: dict[str, Any]) -> CarousellListing | None:
    """Parse a single listing card from the API response."""
    try:
        listing_card = card.get("listingCard") or card.get("listing") or card
        listing_id = str(
            listing_card.get("id")
            or listing_card.get("listingID")
            or listing_card.get("listing_id", "")
        )
        if not listing_id:
            return None

        title = listing_card.get("title", "")

        # Price can be in various locations
        price = (
            listing_card.get("price")
            or listing_card.get("formattedPrice")
            or listing_card.get("price_formatted")
            or ""
        )
        if isinstance(price, (int, float)):
            price = f"RM {price}"

        condition = listing_card.get("condition") or listing_card.get("conditionText")

        # Seller info
        seller = listing_card.get("seller") or listing_card.get("sellerProfile") or {}
        seller_name = seller.get("name") or seller.get("username")

        # Image
        photo = listing_card.get("photo") or listing_card.get("primaryPhoto") or {}
        image_url = photo.get("url") or photo.get("thumbnailUrl")
        if not image_url:
            photos = listing_card.get("photos") or listing_card.get("media") or []
            if photos and isinstance(photos, list):
                first = photos[0]
                image_url = first.get("url") or first if isinstance(first, str) else None

        listing_url = f"{CAROUSELL_BASE}/p/{listing_id}"

        time_ago = listing_card.get("timeAgo") or listing_card.get("time_ago")

        return CarousellListing(
            listing_id=listing_id,
            title=title,
            price=str(price),
            condition=condition,
            seller_name=seller_name,
            image_url=image_url,
            listing_url=listing_url,
            time_ago=time_ago,
        )
    except Exception as exc:
        logger.debug("Failed to parse listing card: %s", exc)
        return None


def _parse_api_response(body: dict[str, Any]) -> tuple[list[CarousellListing], int]:
    """Parse the Carousell search API JSON response.

    Returns (listings, total_count).
    """
    data = body.get("data", body)
    results = data.get("results") or data.get("listings") or data.get("cards") or []
    total = data.get("totalCount") or data.get("total") or len(results)

    listings: list[CarousellListing] = []
    for card in results:
        listing = _parse_listing(card)
        if listing:
            listings.append(listing)

    return listings, int(total)


async def search_carousell(
    query: str,
    *,
    max_items: int = 100,
    max_pages: int = 5,
) -> CarousellScrapeResult:
    """Search Carousell Malaysia and return structured listing data.

    Uses Playwright + Camoufox to load the search page. Intercepts the
    internal search API response for clean JSON. Sends ntfy notification
    if a Cloudflare challenge needs human intervention.

    Args:
        query: Search term (e.g. "40346" or "lego 40346")
        max_items: Maximum listings to collect
        max_pages: Maximum search result pages to scrape

    Returns:
        CarousellScrapeResult with parsed listings or error
    """
    collected: list[CarousellListing] = []
    seen_ids: set[str] = set()
    total_count = 0

    try:
        async with _carousell_browser() as browser:
            page = await browser.new_page()

            # Set up API response interceptor
            api_responses: list[dict[str, Any]] = []

            async def _on_response(response: Response) -> None:
                if CAROUSELL_SEARCH_API in response.url:
                    try:
                        body = await response.json()
                        api_responses.append(body)
                    except Exception:
                        pass

            page.on("response", _on_response)

            # Navigate to search page
            search_url = f"{CAROUSELL_BASE}/search/{query}"
            logger.info("Navigating to %s", search_url)
            await page.goto(search_url, wait_until="domcontentloaded")
            await _human_delay(3_000, 5_000)

            # Check for Cloudflare challenge
            if await _detect_cloudflare(page):
                solved = await _wait_for_cloudflare(page, query)
                if not solved:
                    return CarousellScrapeResult(
                        success=False,
                        query=query,
                        error="Cloudflare challenge not solved within timeout",
                    )
                # After challenge solved, reload the search
                await page.goto(search_url, wait_until="domcontentloaded")
                await _human_delay(3_000, 5_000)

            # Wait for content to load
            await page.wait_for_load_state("networkidle")
            await _human_delay(1_000, 2_000)

            # Process intercepted API responses from first page
            for body in api_responses:
                listings, count = _parse_api_response(body)
                if count > total_count:
                    total_count = count
                for listing in listings:
                    if listing.listing_id not in seen_ids:
                        seen_ids.add(listing.listing_id)
                        collected.append(listing)

            # Paginate by scrolling (Carousell uses infinite scroll)
            for page_num in range(1, max_pages):
                if len(collected) >= max_items:
                    break

                api_responses.clear()

                # Scroll to bottom to trigger next page load
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await _human_delay(2_000, 4_000)

                # Small additional scrolls to ensure trigger
                for _ in range(2):
                    await page.evaluate(
                        "window.scrollBy(0, window.innerHeight)"
                    )
                    await _human_delay(1_000, 2_000)

                # Check if new API responses came in
                if not api_responses:
                    # Wait a bit longer for slow responses
                    await _human_delay(2_000, 3_000)

                if not api_responses:
                    logger.info("No more results after page %d", page_num)
                    break

                for body in api_responses:
                    listings, count = _parse_api_response(body)
                    if count > total_count:
                        total_count = count
                    for listing in listings:
                        if listing.listing_id not in seen_ids:
                            seen_ids.add(listing.listing_id)
                            collected.append(listing)

                # Simulate human browsing between pages
                await _human_delay(1_500, 3_000)

            # If API interception yielded nothing, fall back to HTML parsing
            if not collected:
                logger.warning("API interception returned no results, trying HTML fallback")
                collected = await _parse_html_fallback(page, max_items)

        trimmed = tuple(collected[:max_items])
        logger.info(
            "Carousell search '%s': %d listings found (total: %d)",
            query, len(trimmed), total_count,
        )

        return CarousellScrapeResult(
            success=True,
            query=query,
            listings=trimmed,
            total_count=total_count or len(trimmed),
        )

    except Exception as exc:
        logger.exception("Carousell scrape failed for query: %s", query)
        return CarousellScrapeResult(
            success=False,
            query=query,
            error=str(exc),
        )


async def _parse_html_fallback(
    page: Page,
    max_items: int,
) -> list[CarousellListing]:
    """Fallback: parse listing cards from the HTML DOM.

    Used when API interception fails (e.g. response format changed).
    """
    listings: list[CarousellListing] = []

    cards = await page.evaluate("""() => {
        const results = [];
        // Carousell listing cards are typically links to /p/{id}
        const links = document.querySelectorAll('a[href*="/p/"]');
        for (const link of links) {
            const href = link.getAttribute('href') || '';
            const match = href.match(/\\/p\\/(\\d+)/);
            if (!match) continue;

            const id = match[1];
            const title = link.querySelector('[data-testid*="title"], h2, p')?.textContent?.trim() || '';
            const priceEl = link.querySelector('[data-testid*="price"], [class*="price"]');
            const price = priceEl?.textContent?.trim() || '';
            const img = link.querySelector('img');
            const imageUrl = img?.src || '';

            results.push({ id, title, price, imageUrl, href });
        }
        return results;
    }""")

    for card in cards[:max_items]:
        listings.append(
            CarousellListing(
                listing_id=card.get("id", ""),
                title=card.get("title", ""),
                price=card.get("price", ""),
                condition=None,
                seller_name=None,
                image_url=card.get("imageUrl"),
                listing_url=f"{CAROUSELL_BASE}{card.get('href', '')}",
                time_ago=None,
            )
        )

    return listings


def search_carousell_sync(
    query: str,
    *,
    max_items: int = 100,
    max_pages: int = 5,
) -> CarousellScrapeResult:
    """Synchronous wrapper for search_carousell."""
    return asyncio.run(
        search_carousell(query, max_items=max_items, max_pages=max_pages)
    )
