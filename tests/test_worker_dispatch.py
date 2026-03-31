"""GWT tests for worker dispatch, registry consistency, and concurrency."""

import asyncio
from unittest.mock import AsyncMock, patch

from api.jobs import JobManager
from api.schemas import JobStatus
from api.worker import run_worker, _build_semaphores, _process_job, _WorkerSlots
from api.workers import WORKER_REGISTRY


def _run_worker_once(manager: JobManager) -> None:
    """Run the worker loop just long enough to process one queued job."""

    async def _process():
        task = asyncio.create_task(run_worker(manager))
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_process())


class TestWorkerDispatch:
    """Given a queued job, verify the worker dispatches to the correct handler."""

    def test_given_unknown_scraper_when_processed_then_marked_failed(self):
        """Given unknown scraper_id, when worker processes it, then job fails."""
        manager = JobManager()
        job = manager.create_job("nonexistent", "https://example.com")

        _run_worker_once(manager)

        updated = manager.get_job(job.job_id)
        assert updated.status == JobStatus.FAILED
        assert "Unknown scraper" in updated.error

    def test_given_toysrus_scraper_when_processed_then_completed(self):
        """Given toysrus scraper_id, when worker processes it, then completed."""
        manager = JobManager()
        manager.create_job("toysrus", "https://www.toysrus.com.my/lego/")

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
            mock_scrape.return_value.products = []
            _run_worker_once(manager)

        jobs = manager.list_jobs()
        assert jobs[0].status == JobStatus.COMPLETED

    def test_given_shopee_scraper_when_processed_then_completed(self):
        """Given shopee scraper_id, when worker processes it, then completed."""
        manager = JobManager()
        manager.create_job("shopee", "https://shopee.com.my/legoshopmy")

        with (
            patch(
                "services.shopee.scraper.scrape_shop_page",
                new_callable=AsyncMock,
            ) as mock_scrape,
            patch("services.notifications.deal_notifier.check_and_notify", return_value=0),
        ):
            mock_scrape.return_value.success = True
            mock_scrape.return_value.items = []
            _run_worker_once(manager)

        jobs = manager.list_jobs()
        assert jobs[0].status == JobStatus.COMPLETED


class TestWorkerRegistry:
    """Given the worker registry, verify it covers all registered scrapers."""

    def test_given_registry_when_checked_then_all_route_scrapers_have_workers(self):
        """Given WORKER_REGISTRY, when compared to route VALID_SCRAPER_IDS,
        then every route scraper has a registered worker."""
        from api.routes.scrape import VALID_SCRAPER_IDS

        for scraper_id in VALID_SCRAPER_IDS:
            assert scraper_id in WORKER_REGISTRY, (
                f"Scraper '{scraper_id}' is in routes but has no worker in WORKER_REGISTRY"
            )

    def test_given_registry_when_iterated_then_each_scraper_id_matches_key(self):
        """Given WORKER_REGISTRY, when iterated, then each worker's scraper_id
        matches its registry key."""
        for key, worker in WORKER_REGISTRY.items():
            assert worker.scraper_id == key, (
                f"Registry key '{key}' does not match worker.scraper_id '{worker.scraper_id}'"
            )

    def test_given_registry_when_counted_then_has_expected_workers(self):
        """Given WORKER_REGISTRY, when counted, then it has at least 6 workers."""
        assert len(WORKER_REGISTRY) >= 6

    def test_given_registry_when_checked_then_all_workers_have_max_concurrency(self):
        """Given WORKER_REGISTRY, when iterated, then each worker declares max_concurrency."""
        for key, worker in WORKER_REGISTRY.items():
            assert hasattr(worker, "max_concurrency"), (
                f"Worker '{key}' missing max_concurrency attribute"
            )
            assert isinstance(worker.max_concurrency, int)
            assert worker.max_concurrency >= 1


class TestConcurrency:
    """Given source workers with max_concurrency, verify semaphore-based dispatch."""

    def test_given_bricklink_catalog_when_checked_then_max_concurrency_is_two(self):
        """Given BricklinkCatalogWorker, when max_concurrency checked, then it is 2."""
        worker = WORKER_REGISTRY["bricklink_catalog"]
        assert worker.max_concurrency == 2

    def test_given_enrichment_when_checked_then_max_concurrency_is_two(self):
        """Given EnrichmentWorker, when max_concurrency checked, then it is 2."""
        worker = WORKER_REGISTRY["enrichment"]
        assert worker.max_concurrency == 2

    def test_given_single_concurrency_workers_when_checked_then_max_concurrency_is_one(self):
        """Given single-concurrency workers, when max_concurrency checked, then it is 1."""
        multi = {"bricklink_catalog", "enrichment"}
        for scraper_id, worker in WORKER_REGISTRY.items():
            if scraper_id in multi:
                continue
            assert worker.max_concurrency == 1, (
                f"Worker '{scraper_id}' should have max_concurrency=1, got {worker.max_concurrency}"
            )

    def test_given_registry_when_semaphores_built_then_one_per_source(self):
        """Given WORKER_REGISTRY, when _build_semaphores called, then returns one per source."""
        semaphores = _build_semaphores()

        assert set(semaphores.keys()) == set(WORKER_REGISTRY.keys())

    def test_given_semaphores_when_bricklink_checked_then_allows_two(self):
        """Given built semaphores, when bricklink_catalog checked, then semaphore limit is 2."""
        semaphores = _build_semaphores()
        sem = semaphores["bricklink_catalog"]

        # Semaphore._value is the internal counter (initial value = max_concurrency)
        assert sem._value == 2

    def test_given_semaphores_when_shopee_checked_then_allows_one(self):
        """Given built semaphores, when shopee checked, then semaphore limit is 1."""
        semaphores = _build_semaphores()
        sem = semaphores["shopee"]

        assert sem._value == 1

    def test_given_two_bricklink_jobs_when_dispatched_then_both_run_concurrently(self):
        """Given 2 bricklink_catalog jobs, when dispatched, then both run at the same time."""
        timestamps: list[tuple[str, str]] = []

        async def _test():
            manager = JobManager()
            job1 = manager.create_job("bricklink_catalog", "https://example.com/page1")
            job2 = manager.create_job("bricklink_catalog", "https://example.com/page2")

            # Create a fake worker whose run() records start/end times
            class FakeCatalogWorker:
                scraper_id = "bricklink_catalog"
                max_concurrency = 2

                async def run(self, job, mgr):
                    from api.workers.base import WorkResult
                    timestamps.append((job.job_id, "start"))
                    await asyncio.sleep(0.05)
                    timestamps.append((job.job_id, "end"))
                    return WorkResult(items_found=0, items=[], log_summary="test")

            fake_worker = FakeCatalogWorker()
            sem = asyncio.Semaphore(2)
            slots = _WorkerSlots()

            # Dispatch both concurrently
            t1 = asyncio.create_task(_process_job(manager, job1, fake_worker, sem, slots))
            t2 = asyncio.create_task(_process_job(manager, job2, fake_worker, sem, slots))
            await asyncio.gather(t1, t2)

            return manager, job1, job2

        manager, job1, job2 = asyncio.run(_test())

        # Both should have started before either ended (concurrent)
        events = [(jid, evt) for jid, evt in timestamps]
        start_indices = [i for i, (_, evt) in enumerate(events) if evt == "start"]
        end_indices = [i for i, (_, evt) in enumerate(events) if evt == "end"]

        # Both starts should come before both ends
        assert max(start_indices) < min(end_indices), (
            f"Expected concurrent execution but got sequential: {events}"
        )

        assert manager.get_job(job1.job_id).status == JobStatus.COMPLETED
        assert manager.get_job(job2.job_id).status == JobStatus.COMPLETED

    def test_given_semaphore_of_one_when_two_jobs_then_sequential(self):
        """Given a semaphore(1), when 2 jobs dispatched, then they run sequentially."""
        timestamps: list[tuple[str, str]] = []

        async def _test():
            manager = JobManager()
            job1 = manager.create_job("shopee", "https://example.com/1")
            job2 = manager.create_job("shopee", "https://example.com/2")

            class FakeShopeeWorker:
                scraper_id = "shopee"
                max_concurrency = 1

                async def run(self, job, mgr):
                    from api.workers.base import WorkResult
                    timestamps.append((job.job_id, "start"))
                    await asyncio.sleep(0.05)
                    timestamps.append((job.job_id, "end"))
                    return WorkResult(items_found=0, items=[], log_summary="test")

            fake_worker = FakeShopeeWorker()
            sem = asyncio.Semaphore(1)
            slots = _WorkerSlots()

            t1 = asyncio.create_task(_process_job(manager, job1, fake_worker, sem, slots))
            t2 = asyncio.create_task(_process_job(manager, job2, fake_worker, sem, slots))
            await asyncio.gather(t1, t2)

            return manager

        manager = asyncio.run(_test())

        # With semaphore(1), first job's end should come before second job's start
        events = [(jid, evt) for jid, evt in timestamps]
        # Pattern should be: start, end, start, end (sequential)
        assert events[1][1] == "end", f"Expected sequential but got: {events}"
        assert events[2][1] == "start", f"Expected sequential but got: {events}"

    def test_given_failing_job_when_processed_then_marked_failed_not_crash(self):
        """Given a job that raises, when processed via _process_job, then marked failed."""

        async def _test():
            manager = JobManager()
            job = manager.create_job("test", "https://example.com")

            class FailingWorker:
                scraper_id = "test"
                max_concurrency = 1

                async def run(self, job, mgr):
                    raise RuntimeError("boom")

            sem = asyncio.Semaphore(1)
            slots = _WorkerSlots()
            await _process_job(manager, job, FailingWorker(), sem, slots)
            return manager, job

        manager, job = asyncio.run(_test())
        updated = manager.get_job(job.job_id)
        assert updated.status == JobStatus.FAILED
        assert "boom" in updated.error
