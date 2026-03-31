"""GWT tests for ShopeeSaturationWorker -- proves it handles the shopee_saturation source."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from api.jobs import JobManager
from api.workers.shopee_saturation import ShopeeSaturationWorker


class TestShopeeSaturationWorkerIdentity:
    """Given a ShopeeSaturationWorker, verify it identifies as the shopee_saturation source."""

    def test_given_saturation_worker_when_scraper_id_checked_then_matches(self):
        """Given a ShopeeSaturationWorker, when scraper_id checked, then it is 'shopee_saturation'."""
        worker = ShopeeSaturationWorker()
        assert worker.scraper_id == "shopee_saturation"


class TestShopeeSaturationWorkerRun:
    """Given a shopee_saturation job, verify the worker processes it correctly."""

    def test_given_batch_job_when_no_items_need_checking_then_returns_zero(self):
        """Given a batch saturation job, when no items need checking, then returns 0 items."""
        worker = ShopeeSaturationWorker()
        mgr = JobManager()
        job = mgr.create_job("shopee_saturation", "batch")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.shopee.saturation_repository.get_items_needing_saturation_check",
                return_value=[],
            ),
        ):
            mock_conn.return_value.close = lambda: None
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 0

    def test_given_batch_job_when_items_found_then_returns_count(self):
        """Given a batch saturation job, when items processed, then returns successful count."""

        @dataclass
        class FakeBatchResult:
            successful: int = 3
            failed: int = 1
            skipped: int = 0
            total_items: int = 4

        worker = ShopeeSaturationWorker()
        mgr = JobManager()
        job = mgr.create_job("shopee_saturation", "batch")

        with (
            patch("db.connection.get_connection") as mock_conn,
            patch("db.schema.init_schema"),
            patch(
                "services.shopee.saturation_repository.get_items_needing_saturation_check",
                return_value=[{"set_number": "75192", "title": "Test", "rrp_cents": 100}],
            ),
            patch(
                "services.shopee.saturation_scraper.run_saturation_batch",
                new_callable=AsyncMock,
                return_value=FakeBatchResult(),
            ),
        ):
            mock_conn.return_value.close = lambda: None
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 3
        assert "3/4 successful" in result.log_summary
