"""Tests for Shopee product parser."""

import asyncio
from unittest.mock import AsyncMock

from services.shopee.parser import parse_search_results


def _run(coro):
    return asyncio.run(coro)


class TestParseSearchResults:

    def test_parses_products(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[
            {
                "title": "LEGO Star Wars 75192",
                "price_display": "RM2,399.00",
                "sold_count": "8 sold",
                "rating": "5.0",
                "product_url": "https://shopee.com.my/product-i.123.456",
                "image_url": "https://img.shopee.com.my/abc.jpg",
                "is_sold_out": False,
            },
            {
                "title": "LEGO City 60337",
                "price_display": "RM399.00",
                "sold_count": None,
                "rating": "4.9",
                "product_url": "https://shopee.com.my/product-i.789.012",
                "image_url": None,
                "is_sold_out": False,
            },
        ])

        result = _run(parse_search_results(page, max_items=10))

        assert len(result) == 2
        assert result[0].title == "LEGO Star Wars 75192"
        assert result[0].price_display == "RM2,399.00"
        assert result[0].rating == "5.0"
        assert result[0].is_sold_out is False
        assert result[1].title == "LEGO City 60337"

    def test_detects_sold_out_products(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[
            {
                "title": "LEGO Icons Ferrari F2004",
                "price_display": "RM379.90",
                "sold_count": "38 sold",
                "rating": "5.0",
                "product_url": "https://shopee.com.my/product-i.111.222",
                "image_url": None,
                "is_sold_out": True,
            },
            {
                "title": "LEGO City 60337",
                "price_display": "RM399.00",
                "sold_count": "10 sold",
                "rating": "4.9",
                "product_url": "https://shopee.com.my/product-i.333.444",
                "image_url": None,
                "is_sold_out": False,
            },
        ])

        result = _run(parse_search_results(page, max_items=10))

        assert len(result) == 2
        assert result[0].is_sold_out is True
        assert result[0].sold_count == "38 sold"
        assert result[1].is_sold_out is False

    def test_empty_results(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[])

        result = _run(parse_search_results(page, max_items=10))
        assert result == ()

    def test_filters_items_without_title(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[
            {
                "title": "",
                "price_display": "RM100",
                "sold_count": None,
                "rating": None,
                "product_url": "url-1",
                "image_url": None,
            },
            {
                "title": "Valid Product",
                "price_display": "RM200",
                "sold_count": None,
                "rating": None,
                "product_url": "url-2",
                "image_url": None,
            },
        ])

        result = _run(parse_search_results(page, max_items=10))

        assert len(result) == 1
        assert result[0].title == "Valid Product"
