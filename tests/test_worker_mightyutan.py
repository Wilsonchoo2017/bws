"""GWT tests for MightyutanWorker -- proves it handles the mightyutan data source."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from api.jobs import JobManager
from api.workers.mightyutan import MightyutanWorker


class TestMightyutanWorkerIdentity:
    """Given a MightyutanWorker, verify it identifies as the mightyutan source."""

    def test_given_mightyutan_worker_when_scraper_id_checked_then_matches_mightyutan(self):
        """Given a MightyutanWorker, when scraper_id checked, then it is 'mightyutan'."""
        worker = MightyutanWorker()
        assert worker.scraper_id == "mightyutan"


class TestMightyutanWorkerRun:
    """Given a mightyutan job, verify the worker processes it correctly."""

    def test_given_mightyutan_job_when_processed_then_returns_items(self):
        """Given a mightyutan job, when worker runs, then returns WorkResult with items."""

        @dataclass
        class FakeProduct:
            name: str = "LEGO City 60400"
            price_myr: float = 49.90
            total_sold: int = 25
            rating: float = 4.8
            url: str = "https://mightyutan.com.my/product"
            image_url: str = "https://img.example.com/img.jpg"

        worker = MightyutanWorker()
        mgr = JobManager()
        job = mgr.create_job("mightyutan", "https://mightyutan.com.my/collection/lego-1")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.mightyutan.scraper.scrape_all_lego",
                new_callable=AsyncMock,
            ) as mock_scrape,
            patch("services.notifications.deal_notifier.check_and_notify", return_value=0),
        ):
            mock_conn.return_value.close = lambda: None
            mock_scrape.return_value.success = True
            mock_scrape.return_value.products = [FakeProduct()]
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 1
        assert result.items[0]["title"] == "LEGO City 60400"
        assert result.items[0]["shop_name"] == "Mighty Utan Malaysia"

    def test_given_mightyutan_job_when_scrape_fails_then_raises(self):
        """Given a mightyutan job, when scrape fails, then RuntimeError raised."""
        worker = MightyutanWorker()
        mgr = JobManager()
        job = mgr.create_job("mightyutan", "https://mightyutan.com.my/collection/lego-1")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.mightyutan.scraper.scrape_all_lego",
                new_callable=AsyncMock,
            ) as mock_scrape,
        ):
            mock_conn.return_value.close = lambda: None
            mock_scrape.return_value.success = False
            mock_scrape.return_value.error = "Site unavailable"

            try:
                asyncio.run(worker.run(job, mgr))
                assert False, "Expected RuntimeError"
            except RuntimeError as e:
                assert "Site unavailable" in str(e)
