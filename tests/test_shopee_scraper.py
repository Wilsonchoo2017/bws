"""Tests for Shopee scraper pagination and orchestration."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.shopee.parser import ShopeeProduct
from services.shopee.scraper import (
    _click_next_page,
    _extract_shop_name,
    _scrape_all_pages,
    _scroll_to_load,
    _simulate_browsing,
    scrape_shop_page,
)


def _make_product(title: str, url: str) -> ShopeeProduct:
    return ShopeeProduct(
        title=title,
        price_display="RM100",
        product_url=url,
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _extract_shop_name
# ---------------------------------------------------------------------------

class TestExtractShopName:

    def test_shop_url(self) -> None:
        result = _extract_shop_name("https://shopee.com.my/legoshopmy?page=0&shopCollection=258084132")
        assert result == "legoshopmy"

    def test_product_url_returns_none(self) -> None:
        result = _extract_shop_name("https://shopee.com.my/some-lego-set-i.12345.67890")
        assert result is None

    def test_system_path_returns_none(self) -> None:
        result = _extract_shop_name("https://shopee.com.my/search")
        assert result is None

    def test_nested_path_returns_none(self) -> None:
        result = _extract_shop_name("https://shopee.com.my/shop/subcategory")
        assert result is None


# ---------------------------------------------------------------------------
# _scroll_to_load
# ---------------------------------------------------------------------------

class TestScrollToLoad:

    def test_stops_when_height_stable(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=[500, None, 500])

        with patch("services.shopee.scraper.human_delay", new_callable=AsyncMock):
            _run(_scroll_to_load(page, max_scrolls=5))

        assert page.evaluate.call_count == 3

    def test_scrolls_while_height_grows(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=[
            500, None, 1000,
            1000, None, 1000,
        ])

        with patch("services.shopee.scraper.human_delay", new_callable=AsyncMock):
            _run(_scroll_to_load(page, max_scrolls=5))

        assert page.evaluate.call_count == 6


# ---------------------------------------------------------------------------
# _click_next_page
# ---------------------------------------------------------------------------

class TestClickNextPage:

    def test_clicks_next_button(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=[True, None, None])
        mock_el = AsyncMock()
        page.query_selector = AsyncMock(return_value=mock_el)
        page.wait_for_load_state = AsyncMock()

        with patch("services.shopee.scraper.random_click_element", new_callable=AsyncMock) as mock_click, \
             patch("services.shopee.scraper.human_delay", new_callable=AsyncMock):
            result = _run(_click_next_page(page))

        assert result is True
        mock_click.assert_awaited_once_with(mock_el)

    def test_returns_false_when_no_button(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=False)

        result = _run(_click_next_page(page))
        assert result is False

    def test_returns_false_when_element_not_found(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=True)
        page.query_selector = AsyncMock(return_value=None)

        result = _run(_click_next_page(page))
        assert result is False


# ---------------------------------------------------------------------------
# _simulate_browsing
# ---------------------------------------------------------------------------

class TestSimulateBrowsing:

    def test_scrolls_incrementally_through_page(self) -> None:
        page = AsyncMock()
        scroll_positions: list[str] = []

        async def mock_evaluate(js, *_a, **_k):
            if "scrollTo(0, 0)" in js:
                return None
            if "scrollHeight" in js and "scrollTo" not in js:
                return 3000
            if "innerHeight" in js and "innerWidth" not in js:
                return 768
            if "innerWidth" in js:
                return 1366
            if "scrollTo" in js:
                scroll_positions.append(js)
                return None
            # card count / hover queries
            return 0

        page.evaluate = AsyncMock(side_effect=mock_evaluate)
        page.mouse = AsyncMock()
        page.mouse.move = AsyncMock()

        with patch("services.shopee.scraper.human_delay", new_callable=AsyncMock):
            _run(_simulate_browsing(page))

        # Should have scrolled multiple times (3-6 steps)
        assert len(scroll_positions) >= 3

    def test_short_page_skips_scrolling(self) -> None:
        page = AsyncMock()

        async def mock_evaluate(js, *_a, **_k):
            if "scrollHeight" in js:
                return 500
            if "innerHeight" in js:
                return 768  # viewport taller than page
            return None

        page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch("services.shopee.scraper.human_delay", new_callable=AsyncMock) as mock_delay:
            _run(_simulate_browsing(page))

        # Should still pause briefly, but not do the full scroll loop
        assert mock_delay.await_count <= 3


# ---------------------------------------------------------------------------
# _scrape_all_pages
# ---------------------------------------------------------------------------

class TestScrapeAllPages:

    def test_single_page_no_pagination(self) -> None:
        page = AsyncMock()
        products = (_make_product("Set A", "url-a"), _make_product("Set B", "url-b"))

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", new_callable=AsyncMock, return_value=products), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock), \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock, return_value=False):
            result = _run(_scrape_all_pages(page, max_items=50, max_pages=5))

        assert len(result) == 2
        assert result[0].title == "Set A"

    def test_multi_page_aggregation(self) -> None:
        page = AsyncMock()
        page1 = (_make_product("Set A", "url-a"),)
        page2 = (_make_product("Set B", "url-b"),)

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", new_callable=AsyncMock, side_effect=[page1, page2]), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock), \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock, side_effect=[True, False]):
            result = _run(_scrape_all_pages(page, max_items=50, max_pages=5))

        assert len(result) == 2
        assert result[0].title == "Set A"
        assert result[1].title == "Set B"

    def test_stops_at_max_items(self) -> None:
        page = AsyncMock()
        page1 = tuple(_make_product(f"Set {i}", f"url-{i}") for i in range(5))

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", new_callable=AsyncMock, return_value=page1), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock), \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock) as mock_next:
            result = _run(_scrape_all_pages(page, max_items=3, max_pages=10))

        assert len(result) == 3
        mock_next.assert_not_awaited()

    def test_stops_at_max_pages(self) -> None:
        page = AsyncMock()
        page1 = (_make_product("Set A", "url-a"),)
        page2 = (_make_product("Set B", "url-b"),)

        call_count = 0

        async def mock_parse(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", side_effect=mock_parse), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock), \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock, return_value=True) as mock_next:
            result = _run(_scrape_all_pages(page, max_items=100, max_pages=2))

        # Scraped exactly 2 pages, no more
        assert len(result) == 2
        assert call_count == 2

    def test_deduplicates_by_url(self) -> None:
        page = AsyncMock()
        page1 = (_make_product("Set A", "url-a"), _make_product("Set B", "url-b"))
        page2 = (_make_product("Set A dup", "url-a"), _make_product("Set C", "url-c"))

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", new_callable=AsyncMock, side_effect=[page1, page2]), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock), \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock, side_effect=[True, False]):
            result = _run(_scrape_all_pages(page, max_items=50, max_pages=5))

        assert len(result) == 3
        urls = [item.product_url for item in result]
        assert urls == ["url-a", "url-b", "url-c"]

    def test_simulate_browsing_called_between_pages(self) -> None:
        page = AsyncMock()
        page1 = (_make_product("Set A", "url-a"),)
        page2 = (_make_product("Set B", "url-b"),)

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", new_callable=AsyncMock, side_effect=[page1, page2]), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock) as mock_browse, \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock, side_effect=[True, False]):
            _run(_scrape_all_pages(page, max_items=50, max_pages=5))

        # Called before each _click_next_page attempt (once per page except the last)
        assert mock_browse.await_count == 2

    def test_simulate_browsing_not_called_when_max_items_reached(self) -> None:
        page = AsyncMock()
        products = tuple(_make_product(f"Set {i}", f"url-{i}") for i in range(5))

        with patch("services.shopee.scraper._scroll_to_load", new_callable=AsyncMock), \
             patch("services.shopee.scraper.parse_search_results", new_callable=AsyncMock, return_value=products), \
             patch("services.shopee.scraper._simulate_browsing", new_callable=AsyncMock) as mock_browse, \
             patch("services.shopee.scraper._click_next_page", new_callable=AsyncMock):
            _run(_scrape_all_pages(page, max_items=3, max_pages=10))

        mock_browse.assert_not_awaited()


# ---------------------------------------------------------------------------
# scrape_shop_page (integration)
# ---------------------------------------------------------------------------

class TestScrapeShopPage:

    def test_success_path(self) -> None:
        products = (_make_product("LEGO 75192", "url-1"),)
        mock_page = AsyncMock()
        mock_page.url = "https://shopee.com.my/testshop?shopCollection=123"

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        with patch("services.shopee.scraper.shopee_browser") as mock_ctx, \
             patch("services.shopee.scraper.setup_dialog_handler"), \
             patch("services.shopee.scraper.human_delay", new_callable=AsyncMock), \
             patch("services.shopee.scraper.dismiss_popups_loop", new_callable=AsyncMock), \
             patch("services.shopee.scraper.select_english", new_callable=AsyncMock), \
             patch("services.shopee.scraper._scrape_all_pages", new_callable=AsyncMock, return_value=products), \
             patch("services.shopee.scraper._save_to_db"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_browser)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = _run(scrape_shop_page("https://shopee.com.my/testshop?shopCollection=123"))

        assert result.success is True
        assert len(result.items) == 1
        assert result.items[0].shop_name == "testshop"

    def test_browser_error_returns_failure(self) -> None:
        with patch("services.shopee.scraper.shopee_browser") as mock_ctx, \
             patch("services.shopee.scraper._save_scrape_error"):
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("Browser crash"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = _run(scrape_shop_page("https://shopee.com.my/testshop"))

        assert result.success is False
        assert "Browser crash" in (result.error or "")

    def test_login_redirect_failure(self) -> None:
        mock_page = AsyncMock()
        mock_page.url = "https://shopee.com.my/buyer/login"

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        with patch("services.shopee.scraper.shopee_browser") as mock_ctx, \
             patch("services.shopee.scraper.setup_dialog_handler"), \
             patch("services.shopee.scraper.human_delay", new_callable=AsyncMock), \
             patch("services.shopee.scraper.dismiss_popups_loop", new_callable=AsyncMock), \
             patch("services.shopee.scraper.select_english", new_callable=AsyncMock), \
             patch("services.shopee.scraper.is_logged_in", new_callable=AsyncMock, return_value=False), \
             patch("services.shopee.scraper.login", new_callable=AsyncMock, return_value=False), \
             patch("services.shopee.scraper._save_scrape_error"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_browser)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = _run(scrape_shop_page("https://shopee.com.my/testshop"))

        assert result.success is False
        assert "Login failed" in (result.error or "")
