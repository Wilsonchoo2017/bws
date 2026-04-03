"""GWT tests for ShopeeWorker -- proves it handles the shopee data source."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from api.jobs import Job, JobManager
from api.workers.shopee import ShopeeWorker


class TestShopeeWorkerIdentity:
    """Given a ShopeeWorker, verify it identifies as the shopee source."""

    def test_given_shopee_worker_when_scraper_id_checked_then_matches_shopee(self):
        """Given a ShopeeWorker, when scraper_id checked, then it is 'shopee'."""
        worker = ShopeeWorker()
        assert worker.scraper_id == "shopee"


class TestShopeeWorkerRun:
    """Given a shopee job, verify the worker processes it correctly."""

    def test_given_shopee_job_when_processed_then_returns_items(self):
        """Given a shopee job, when worker runs, then returns WorkResult with items."""

        @dataclass
        class FakeItem:
            title: str = "LEGO 75192"
            price_display: str = "RM 99.90"
            sold_count: int = 10
            rating: float = 4.5
            shop_name: str = "Test Shop"
            product_url: str = "https://shopee.com.my/item"
            image_url: str = "https://img.example.com/img.jpg"

        worker = ShopeeWorker()
        mgr = JobManager()
        job = mgr.create_job("shopee", "https://shopee.com.my/legoshopmy")

        with (
            patch(
                "services.shopee.scraper.scrape_shop_page",
                new_callable=AsyncMock,
            ) as mock_scrape,
            patch("api.workers.shared.check_deal_signals", new_callable=AsyncMock),
            patch("api.workers.shared.queue_enrichment_for_scraped_items"),
        ):
            mock_scrape.return_value.success = True
            mock_scrape.return_value.items = [FakeItem(), FakeItem()]
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 2
        assert len(result.items) == 2
        assert result.items[0]["title"] == "LEGO 75192"

    def test_given_shopee_job_when_scrape_fails_then_raises(self):
        """Given a shopee job, when scrape fails, then RuntimeError raised."""
        worker = ShopeeWorker()
        mgr = JobManager()
        job = mgr.create_job("shopee", "https://shopee.com.my/legoshopmy")

        with patch(
            "services.shopee.scraper.scrape_shop_page",
            new_callable=AsyncMock,
        ) as mock_scrape:
            mock_scrape.return_value.success = False
            mock_scrape.return_value.error = "Connection timeout"

            try:
                asyncio.run(worker.run(job, mgr))
                assert False, "Expected RuntimeError"
            except RuntimeError as e:
                assert "Connection timeout" in str(e)
