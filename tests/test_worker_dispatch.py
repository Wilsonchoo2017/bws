"""GWT tests for worker scraper dispatch — ensures all scraper IDs are handled."""

import asyncio
from unittest.mock import AsyncMock, patch

from api.jobs import JobManager
from api.schemas import JobStatus
from api.worker import run_worker


def _run_worker_once(manager: JobManager) -> None:
    """Run the worker loop just long enough to process one queued job."""

    async def _process():
        task = asyncio.create_task(run_worker(manager))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_process())


class TestWorkerDispatch:
    """Given a queued job, verify the worker dispatches to the correct scraper."""

    def test_given_unknown_scraper_when_processed_then_marked_failed(self):
        """Given unknown scraper_id, when worker processes it, then job fails."""
        manager = JobManager()
        job = manager.create_job("nonexistent", "https://example.com")

        _run_worker_once(manager)

        updated = manager.get_job(job.job_id)
        assert updated.status == JobStatus.FAILED
        assert "Unknown scraper" in updated.error

    def test_given_toysrus_scraper_when_processed_then_not_unknown(self):
        """Given toysrus scraper_id, when worker processes it, then NOT rejected as unknown."""
        manager = JobManager()
        job = manager.create_job("toysrus", "https://www.toysrus.com.my/lego/")

        with patch(
            "api.worker._run_toysrus_scrape",
            new_callable=AsyncMock,
            return_value=[{"title": "Test Set", "price_display": "RM 99.90"}],
        ):
            _run_worker_once(manager)

        updated = manager.get_job(job.job_id)
        assert updated.status == JobStatus.COMPLETED
        assert updated.items_found == 1

    def test_given_shopee_scraper_when_processed_then_not_unknown(self):
        """Given shopee scraper_id, when worker processes it, then NOT rejected as unknown."""
        manager = JobManager()
        job = manager.create_job("shopee", "https://shopee.com.my/legoshopmy")

        with patch(
            "api.worker._run_shopee_scrape",
            new_callable=AsyncMock,
            return_value=[{"title": "Test Set", "price_display": "RM 50.00"}],
        ):
            _run_worker_once(manager)

        updated = manager.get_job(job.job_id)
        assert updated.status == JobStatus.COMPLETED
        assert updated.items_found == 1


class TestRouteWorkerConsistency:
    """Given route and worker registries, verify they stay in sync."""

    def test_given_route_scrapers_when_compared_to_worker_then_all_handled(self):
        """Given all scraper IDs in the route registry, when checking worker,
        then each ID has a handler (not falling through to 'Unknown scraper')."""
        from api.routes.scrape import VALID_SCRAPER_IDS

        # These are the IDs the worker explicitly handles
        worker_handled_ids = {"shopee", "toysrus", "enrichment", "shopee_saturation", "bricklink_catalog", "mightyutan"}

        for scraper_id in VALID_SCRAPER_IDS:
            assert scraper_id in worker_handled_ids, (
                f"Scraper '{scraper_id}' is registered in the route but has no "
                f"handler in the worker — jobs will fail with 'Unknown scraper'"
            )
