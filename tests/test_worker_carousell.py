"""Tests for the Carousell worker and scraper module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from api.workers.carousell import CarousellWorker
from api.workers.transforms import carousell_listing_to_dict
from services.carousell.scraper import (
    CarousellListing,
    CarousellScrapeResult,
    _parse_api_response,
    _parse_listing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_listing(**overrides) -> CarousellListing:
    defaults = {
        "listing_id": "123456",
        "title": "LEGO 40346 LEGOland Park",
        "price": "RM 150",
        "condition": "Brand new",
        "seller_name": "brickfan99",
        "image_url": "https://media.carousell.com/img.jpg",
        "listing_url": "https://www.carousell.com.my/p/123456",
        "time_ago": "2 hours ago",
    }
    return CarousellListing(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Transform tests
# ---------------------------------------------------------------------------

class TestCarousellListingToDict:
    def test_transforms_all_fields(self) -> None:
        listing = _make_listing()
        result = carousell_listing_to_dict(listing)

        assert result["title"] == "LEGO 40346 LEGOland Park"
        assert result["price_display"] == "RM 150"
        assert result["shop_name"] == "brickfan99"
        assert result["product_url"] == "https://www.carousell.com.my/p/123456"
        assert result["image_url"] == "https://media.carousell.com/img.jpg"
        assert result["condition"] == "Brand new"
        assert result["time_ago"] == "2 hours ago"
        assert result["sold_count"] is None
        assert result["rating"] is None

    def test_missing_seller_defaults_to_carousell(self) -> None:
        listing = _make_listing(seller_name=None)
        result = carousell_listing_to_dict(listing)
        assert result["shop_name"] == "Carousell"


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseListing:
    def test_parses_listing_card(self) -> None:
        card = {
            "listingCard": {
                "id": "789",
                "title": "LEGO 40346",
                "price": "RM 120",
                "condition": "Like new",
                "seller": {"name": "seller1"},
                "photo": {"url": "https://img.com/1.jpg"},
                "timeAgo": "1 day ago",
            }
        }
        listing = _parse_listing(card)
        assert listing is not None
        assert listing.listing_id == "789"
        assert listing.title == "LEGO 40346"
        assert listing.price == "RM 120"
        assert listing.seller_name == "seller1"

    def test_parses_flat_card(self) -> None:
        card = {
            "id": "100",
            "title": "Some LEGO set",
            "formattedPrice": "RM 200",
        }
        listing = _parse_listing(card)
        assert listing is not None
        assert listing.listing_id == "100"
        assert listing.price == "RM 200"

    def test_returns_none_for_missing_id(self) -> None:
        card = {"title": "No ID here"}
        listing = _parse_listing(card)
        assert listing is None

    def test_numeric_price_formatted(self) -> None:
        card = {"id": "1", "title": "Set", "price": 99.5}
        listing = _parse_listing(card)
        assert listing is not None
        assert listing.price == "RM 99.5"


class TestParseApiResponse:
    def test_parses_results_list(self) -> None:
        body = {
            "data": {
                "results": [
                    {"listingCard": {"id": "1", "title": "A"}},
                    {"listingCard": {"id": "2", "title": "B"}},
                ],
                "totalCount": 42,
            }
        }
        listings, total = _parse_api_response(body)
        assert len(listings) == 2
        assert total == 42

    def test_empty_results(self) -> None:
        body = {"data": {"results": [], "totalCount": 0}}
        listings, total = _parse_api_response(body)
        assert len(listings) == 0
        assert total == 0


# ---------------------------------------------------------------------------
# Worker tests
# ---------------------------------------------------------------------------

class TestCarousellWorker:
    def test_scraper_id(self) -> None:
        worker = CarousellWorker()
        assert worker.scraper_id == "carousell"
        assert worker.max_concurrency == 1

    def test_run_success(self) -> None:
        worker = CarousellWorker()
        mock_result = CarousellScrapeResult(
            success=True,
            query="40346",
            listings=(_make_listing(),),
            total_count=1,
        )

        job = AsyncMock()
        job.url = "40346"
        mgr = AsyncMock()

        with patch(
            "services.carousell.scraper.search_carousell",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 1
        assert len(result.items) == 1
        assert result.items[0]["title"] == "LEGO 40346 LEGOland Park"

    def test_run_failure_raises(self) -> None:
        worker = CarousellWorker()
        mock_result = CarousellScrapeResult(
            success=False,
            query="40346",
            error="Cloudflare blocked",
        )

        job = AsyncMock()
        job.url = "40346"
        mgr = AsyncMock()

        with patch(
            "services.carousell.scraper.search_carousell",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            with pytest.raises(RuntimeError, match="Cloudflare blocked"):
                asyncio.run(worker.run(job, mgr))
