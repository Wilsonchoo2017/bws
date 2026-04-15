"""Carousell Malaysia search scraper with API interception.

Uses Playwright + Camoufox to load the search page, bypass Cloudflare,
and intercept the internal search API response for structured JSON data.
Sends an ntfy notification when a Cloudflare challenge requires human help.
"""

import asyncio
import json
import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Union

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import BrowserContext, Page

from config.settings import CAROUSELL_CONFIG
from services.notifications.ntfy import NtfyMessage, send_notification

logger = logging.getLogger("bws.carousell.scraper")

CAROUSELL_BASE = "https://www.carousell.com.my"

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
    price_cents: int | None = None
    shop_id: str | None = None
    is_sold: bool = False
    is_reserved: bool = False


_MYR_PRICE_RE = re.compile(
    r"(?:RM|MYR)?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _parse_myr_price_cents(price_display: str | None) -> int | None:
    """Parse 'RM 1,234.50' / 'RM219.90' / '219.90' into integer cents.

    More permissive than the Shopee parser because Carousell's
    `formattedPrice` may or may not include the currency prefix and
    may include thousands separators or whitespace.
    """
    if not price_display:
        return None
    match = _MYR_PRICE_RE.search(price_display)
    if not match:
        return None
    cleaned = match.group(1).replace(",", "")
    if not cleaned or cleaned == ".":
        return None
    try:
        return int(round(float(cleaned) * 100))
    except ValueError:
        return None


_SOLD_STATES = {"sold", "s"}
_RESERVED_STATES = {"reserved", "r"}
_SOLD_TOKENS = ("sold", "sold out")
_RESERVED_TOKENS = ("reserved", "reserved by")


def _extract_listing_state(listing_card: dict[str, Any]) -> tuple[bool, bool]:
    """Return (is_sold, is_reserved) for a Carousell listing card.

    Carousell exposes state via multiple fields across API versions:
    `state`, `status`, `marketplace` sub-dict, or a pill badge under
    `overlayText`/`stickerLabel`. Check all of them so we don't miss
    transitions.
    """
    candidates: list[str] = []
    for key in ("state", "status", "listingStatus", "stickerLabel", "overlayText"):
        val = listing_card.get(key)
        if isinstance(val, str):
            candidates.append(val.lower())

    marketplace = listing_card.get("marketplace") or {}
    if isinstance(marketplace, dict):
        mp_state = marketplace.get("state") or marketplace.get("status")
        if isinstance(mp_state, str):
            candidates.append(mp_state.lower())

    is_sold = any(c.strip() in _SOLD_STATES for c in candidates) or any(
        tok in c for c in candidates for tok in _SOLD_TOKENS
    )
    is_reserved = any(c.strip() in _RESERVED_STATES for c in candidates) or any(
        tok in c for c in candidates for tok in _RESERVED_TOKENS
    )
    return is_sold, is_reserved


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


def _carousell_browser() -> AsyncCamoufox:
    """Build a Camoufox browser context for Carousell.

    Returned unstarted; callers use `async with _carousell_browser() as browser`
    since AsyncCamoufox is itself an async context manager.
    """
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
        shop_id_raw = (
            seller.get("id")
            or seller.get("sellerID")
            or seller.get("user_id")
            or seller_name
        )
        shop_id = str(shop_id_raw) if shop_id_raw else None

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

        price_str = str(price)
        price_cents = _parse_myr_price_cents(price_str)
        is_sold, is_reserved = _extract_listing_state(listing_card)

        return CarousellListing(
            listing_id=listing_id,
            title=title,
            price=price_str,
            condition=condition,
            seller_name=seller_name,
            image_url=image_url,
            listing_url=listing_url,
            time_ago=time_ago,
            price_cents=price_cents,
            shop_id=shop_id,
            is_sold=is_sold,
            is_reserved=is_reserved,
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


async def search_carousell_on_browser(
    browser: Any,
    query: str,
    *,
    max_items: int = 100,
    max_pages: int = 5,
) -> CarousellScrapeResult:
    """Run a Carousell search on an already-open Camoufox browser.

    Carousell's Malaysia search is fully SSR'd through Next.js -- the
    search page arrives with listings already baked into the DOM, and
    no internal JSON search API is called. We parse the hydrated HTML
    directly. `max_pages` drives how many scroll-to-bottom cycles we
    run to lazy-load additional cards.

    The caller owns `browser`, so multiple queries in a batch can
    share one Camoufox instance (saving launch cost and persisting
    Cloudflare cookies across queries). Each call opens its own page
    so there is no state bleed between searches.
    """
    page: Page | None = None

    try:
        page = await browser.new_page()

        search_url = f"{CAROUSELL_BASE}/search/{query}/"
        logger.info("Navigating to %s", search_url)
        await page.goto(search_url, wait_until="domcontentloaded")
        await _human_delay(3_000, 5_000)

        if await _detect_cloudflare(page):
            solved = await _wait_for_cloudflare(page, query)
            if not solved:
                return CarousellScrapeResult(
                    success=False,
                    query=query,
                    error="Cloudflare challenge not solved within timeout",
                )
            await page.goto(search_url, wait_until="domcontentloaded")
            await _human_delay(3_000, 5_000)

        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            # networkidle isn't critical -- the SSR content is already
            # present at domcontentloaded time. Don't fail the query.
            pass
        await _human_delay(1_000, 2_000)

        collected = await _parse_search_cards(page, max_items=max_items)

        # Lazy-load more cards by scrolling. Carousell paginates by
        # extending the results grid as the user scrolls.
        for page_num in range(1, max_pages):
            if len(collected) >= max_items:
                break

            before = len(collected)

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await _human_delay(2_000, 4_000)

            for _ in range(2):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await _human_delay(1_000, 2_000)

            collected = await _parse_search_cards(page, max_items=max_items)

            if len(collected) == before:
                logger.info(
                    "Carousell search '%s': no new cards after scroll %d, stopping",
                    query, page_num,
                )
                break

            await _human_delay(1_500, 3_000)

        trimmed = tuple(collected[:max_items])
        logger.info(
            "Carousell search '%s': %d listings parsed",
            query, len(trimmed),
        )

        return CarousellScrapeResult(
            success=True,
            query=query,
            listings=trimmed,
            total_count=len(trimmed),
        )

    except Exception as exc:
        logger.exception("Carousell scrape failed for query: %s", query)
        return CarousellScrapeResult(
            success=False,
            query=query,
            error=str(exc),
        )
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass


async def search_carousell(
    query: str,
    *,
    max_items: int = 100,
    max_pages: int = 5,
) -> CarousellScrapeResult:
    """Search Carousell Malaysia and return structured listing data.

    Standalone single-query entrypoint: launches a fresh Camoufox
    browser, runs one search, and tears it down. For batches, use
    `search_carousell_on_browser` with a shared browser instead.
    """
    try:
        async with _carousell_browser() as browser:
            return await search_carousell_on_browser(
                browser, query, max_items=max_items, max_pages=max_pages,
            )
    except Exception as exc:
        logger.exception("Carousell scrape failed for query: %s", query)
        return CarousellScrapeResult(
            success=False,
            query=query,
            error=str(exc),
        )


_CONDITION_RE = re.compile(
    r"^(brand new|like new|lightly used|well used|heavily used|used)$",
    re.IGNORECASE,
)
# Strict: only 1-3 digits. A Carousell time-ago badge will never say
# "9999 years ago" -- if we see a big number it's because we failed to
# strip the username prefix and ate its trailing digits.
_TIME_AGO_STRICT_RE = re.compile(
    r"^\d{1,3}\s*(?:sec|min|hour|hr|day|week|month|year)s?\s*ago$",
    re.IGNORECASE,
)
# Trailing numeric ID in a slug URL: /p/some-slug-with-words-1425664817/
_LISTING_ID_RE = re.compile(r"/p/[^/]*?-(\d+)/?(?:[?#]|$)")
# Seller username in a /u/{username}/ URL
_SELLER_USERNAME_RE = re.compile(r"/u/([^/?#]+)")


def _extract_listing_id(href: str) -> str | None:
    """Return the trailing numeric ID from a Carousell /p/<slug>-<id>/ URL."""
    match = _LISTING_ID_RE.search(href)
    return match.group(1) if match else None


def _extract_seller_username(href: str | None) -> str | None:
    """Return the username from a Carousell /u/<username>/ URL, or None."""
    if not href:
        return None
    match = _SELLER_USERNAME_RE.search(href)
    return match.group(1) if match else None


def _extract_time_ago(
    anchor_text: str | None, username: str | None,
) -> str | None:
    """Return the time-ago suffix from a seller anchor's text, if any.

    The seller anchor renders `{username}{time_ago}` in a single flat
    textContent, e.g. `"yapph1 year ago"` or `"david_971 year ago"`
    (where the username itself ends in digits). Strip the known
    URL-derived username off the front first, then verify the
    remainder is a plausible time-ago badge. This avoids the greedy
    regex trap where `"vera85 1 year ago"` wrongly becomes
    `"852 years ago"` because a broad `\\d+` match ate a username digit.
    """
    if not anchor_text:
        return None
    text = anchor_text.strip()
    if username and text.lower().startswith(username.lower()):
        remainder = text[len(username):].strip()
    else:
        remainder = text
    if not remainder:
        return None
    return remainder if _TIME_AGO_STRICT_RE.match(remainder) else None


async def _parse_search_cards(
    page: Page,
    *,
    max_items: int,
) -> list[CarousellListing]:
    """Extract listing cards from the hydrated search-results DOM.

    Carousell serves search results via Next.js SSR -- each card is a
    `<a href="/p/<slug>-<id>/">` whose descendant `<p>` elements hold
    [optional "Buyer Protection", Title, "RM<price>", Condition] in
    order. Dedupe by trailing ID and skip any links without the
    expected shape (header nav, footer links, etc).
    """
    cards = await page.evaluate("""(maxItems) => {
        const out = [];
        const seen = new Set();
        const links = Array.from(document.querySelectorAll('a[href*="/p/"]'));

        for (const link of links) {
            if (out.length >= maxItems) break;

            const href = link.getAttribute('href') || '';
            // Trailing numeric segment: /p/foo-bar-1234567890/
            const idMatch = href.match(/\\/p\\/[^/]*?-(\\d+)\\/?(?:[?#]|$)/);
            if (!idMatch) continue;
            const id = idMatch[1];
            if (seen.has(id)) continue;
            seen.add(id);

            // Walk up to a card container that holds BOTH the product
            // anchor AND a sibling seller anchor (/u/<username>/). The
            // seller anchor lives at the top of each result card, so
            // stop climbing as soon as we see it.
            let card = link;
            for (let i = 0; i < 12 && card && card.parentElement; i++) {
                const sellerCandidate = card.querySelector('a[href*="/u/"]');
                if (sellerCandidate) break;
                card = card.parentElement;
            }
            card = card || link;

            const paras = Array.from(card.querySelectorAll('p'))
                .map(el => (el.textContent || '').trim())
                .filter(t => t && t.toLowerCase() !== 'buyer protection');

            const allText = Array.from(card.querySelectorAll('*'))
                .map(el => (el.textContent || '').trim().toLowerCase())
                .filter(t => t.length > 0 && t.length < 40);

            const img = card.querySelector('img');
            const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';

            // Seller: first /u/<username>/ anchor inside the card.
            const sellerAnchor = card.querySelector('a[href*="/u/"]');
            const sellerHref = sellerAnchor ? (sellerAnchor.getAttribute('href') || '') : '';
            const sellerText = sellerAnchor ? (sellerAnchor.textContent || '').trim() : '';

            out.push({
                id,
                href,
                paras,
                allText,
                imageUrl,
                sellerHref,
                sellerText,
            });
        }
        return out;
    }""", max_items)

    listings: list[CarousellListing] = []
    for card in cards:
        paras: list[str] = [p for p in (card.get("paras") or []) if p]
        if not paras:
            continue

        price_idx = next(
            (i for i, t in enumerate(paras) if t.upper().startswith("RM")),
            -1,
        )
        price = paras[price_idx] if price_idx >= 0 else ""

        # Title = longest paragraph that isn't the price, a condition,
        # or a time-ago badge. Short listing titles like "LEGO 42115"
        # can otherwise lose the longest-wins race to a "3 days ago"
        # badge that also shows up in a <p>.
        title_candidates = [
            t for i, t in enumerate(paras)
            if i != price_idx
            and not _CONDITION_RE.match(t)
            and not _TIME_AGO_STRICT_RE.match(t)
        ]
        if not title_candidates:
            continue
        title = max(title_candidates, key=len)

        condition: str | None = next(
            (t for t in paras if _CONDITION_RE.match(t)),
            None,
        )

        all_text = [t for t in (card.get("allText") or []) if t]
        is_sold = any(t == "sold" or t.startswith("sold ") for t in all_text)
        is_reserved = any("reserved" in t for t in all_text)

        seller_href = card.get("sellerHref") or None
        seller_username = _extract_seller_username(seller_href)
        seller_text = card.get("sellerText") or None
        # Canonical seller name is the URL username -- stable, unique,
        # and immune to the `{username}{time_ago}` concatenation that
        # lives in the flat anchor text.
        seller_name = seller_username
        time_ago = _extract_time_ago(seller_text, seller_username)

        href = card.get("href", "")
        listing_url = (
            href if href.startswith("http") else f"{CAROUSELL_BASE}{href}"
        )

        listings.append(
            CarousellListing(
                listing_id=card.get("id", ""),
                title=title,
                price=price,
                condition=condition,
                seller_name=seller_name,
                image_url=card.get("imageUrl") or None,
                listing_url=listing_url,
                time_ago=time_ago,
                price_cents=_parse_myr_price_cents(price),
                shop_id=seller_username,
                is_sold=is_sold,
                is_reserved=is_reserved,
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
