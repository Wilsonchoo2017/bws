"""GWT tests for ToysrusWorker -- proves it handles the toysrus data source."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from api.jobs import JobManager
from api.workers.toysrus import ToysrusWorker


class TestToysrusWorkerIdentity:
    """Given a ToysrusWorker, verify it identifies as the toysrus source."""

    def test_given_toysrus_worker_when_scraper_id_checked_then_matches_toysrus(self):
        """Given a ToysrusWorker, when scraper_id checked, then it is 'toysrus'."""
        worker = ToysrusWorker()
        assert worker.scraper_id == "toysrus"


class TestToysrusWorkerRun:
    """Given a toysrus job, verify the worker processes it correctly."""

    def test_given_toysrus_job_when_processed_then_returns_items(self):
        """Given a toysrus job, when worker runs, then returns WorkResult with items."""

        @dataclass
        class FakeProduct:
            name: str = "LEGO Star Wars 75192"
            price_myr: float = 299.90
            url: str = "https://toysrus.com.my/product"
            image_url: str = "https://img.example.com/img.jpg"

        worker = ToysrusWorker()
        mgr = JobManager()
        job = mgr.create_job("toysrus", "https://www.toysrus.com.my/lego/")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.toysrus.scraper.scrape_all_lego",
                new_callable=AsyncMock,
            ) as mock_scrape,
            patch("services.notifications.deal_notifier.check_and_notify", return_value=0),
        ):
            mock_conn.return_value.close = lambda: None
            mock_scrape.return_value.success = True
            mock_scrape.return_value.products = [FakeProduct()]
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 1
        assert result.items[0]["title"] == "LEGO Star Wars 75192"
        assert result.items[0]["shop_name"] == 'Toys"R"Us Malaysia'

    def test_given_toysrus_job_when_scrape_fails_then_raises(self):
        """Given a toysrus job, when scrape fails, then RuntimeError raised."""
        worker = ToysrusWorker()
        mgr = JobManager()
        job = mgr.create_job("toysrus", "https://www.toysrus.com.my/lego/")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.toysrus.scraper.scrape_all_lego",
                new_callable=AsyncMock,
            ) as mock_scrape,
        ):
            mock_conn.return_value.close = lambda: None
            mock_scrape.return_value.success = False
            mock_scrape.return_value.error = "Network error"

            try:
                asyncio.run(worker.run(job, mgr))
                assert False, "Expected RuntimeError"
            except RuntimeError as e:
                assert "Network error" in str(e)
