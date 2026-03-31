"""GWT tests for BricklinkCatalogWorker -- proves it handles the bricklink_catalog source."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from api.jobs import JobManager
from api.workers.bricklink_catalog import BricklinkCatalogWorker


class TestBricklinkCatalogWorkerIdentity:
    """Given a BricklinkCatalogWorker, verify it identifies as the bricklink_catalog source."""

    def test_given_catalog_worker_when_scraper_id_checked_then_matches(self):
        """Given a BricklinkCatalogWorker, when scraper_id checked, then it is 'bricklink_catalog'."""
        worker = BricklinkCatalogWorker()
        assert worker.scraper_id == "bricklink_catalog"


class TestBricklinkCatalogWorkerRun:
    """Given a bricklink_catalog job, verify the worker processes it correctly."""

    def test_given_catalog_job_when_processed_then_returns_items(self):
        """Given a catalog job, when worker runs, then returns WorkResult with items."""

        @dataclass
        class FakeCatalogItem:
            item_id: str = "75192-1"
            item_type: str = "S"
            title: str = "Millennium Falcon"
            image_url: str = "https://img.bricklink.com/item.jpg"

        @dataclass
        class FakeResult:
            success: bool = True
            error: str | None = None
            items_found: int = 1
            items_inserted: int = 1
            items_skipped: int = 0
            items: list = None

            def __post_init__(self):
                if self.items is None:
                    self.items = [FakeCatalogItem()]

        worker = BricklinkCatalogWorker()
        mgr = JobManager()
        job = mgr.create_job(
            "bricklink_catalog",
            "https://www.bricklink.com/catalogList.asp?pg=1&itemYear=2020&catType=S&v=1",
        )

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.bricklink.scraper.scrape_catalog_list",
                new_callable=AsyncMock,
                return_value=FakeResult(),
            ),
        ):
            mock_conn.return_value.close = lambda: None
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 1
        assert "1 found" in result.log_summary

    def test_given_catalog_job_when_scrape_fails_then_raises(self):
        """Given a catalog job, when scrape fails, then RuntimeError raised."""

        @dataclass
        class FakeResult:
            success: bool = False
            error: str = "Page not found"
            items_found: int = 0
            items_inserted: int = 0
            items_skipped: int = 0
            items: list = None

            def __post_init__(self):
                if self.items is None:
                    self.items = []

        worker = BricklinkCatalogWorker()
        mgr = JobManager()
        job = mgr.create_job("bricklink_catalog", "https://example.com/bad")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.bricklink.scraper.scrape_catalog_list",
                new_callable=AsyncMock,
                return_value=FakeResult(),
            ),
        ):
            mock_conn.return_value.close = lambda: None

            try:
                asyncio.run(worker.run(job, mgr))
                assert False, "Expected RuntimeError"
            except RuntimeError as e:
                assert "Page not found" in str(e)
