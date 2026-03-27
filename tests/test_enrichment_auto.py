"""Tests for auto-enrichment dedup and queue helpers."""

import asyncio

import pytest

from api.jobs import JobManager
from services.enrichment.auto import (
    _get_pending_enrichment_set_numbers,
    queue_enrichment_batch,
    queue_enrichment_if_needed,
)


@pytest.fixture
def manager():
    """Fresh JobManager for each test."""
    return JobManager()


class TestGetPendingSetNumbers:
    """Tests for _get_pending_enrichment_set_numbers."""

    def test_empty_manager(self, manager):
        """Given no jobs. Then returns empty set."""
        assert _get_pending_enrichment_set_numbers(manager) == set()

    def test_finds_queued_enrichment(self, manager):
        """Given a queued enrichment job. Then set number is in pending."""
        manager.create_job("enrichment", "75192")
        pending = _get_pending_enrichment_set_numbers(manager)
        assert "75192" in pending

    def test_finds_running_enrichment(self, manager):
        """Given a running enrichment job. Then set number is in pending."""
        job = manager.create_job("enrichment", "75192")
        manager.mark_running(job.job_id)
        pending = _get_pending_enrichment_set_numbers(manager)
        assert "75192" in pending

    def test_ignores_completed(self, manager):
        """Given a completed enrichment job. Then NOT in pending."""
        job = manager.create_job("enrichment", "75192")
        manager.mark_completed(job.job_id, items_found=3)
        pending = _get_pending_enrichment_set_numbers(manager)
        assert "75192" not in pending

    def test_ignores_failed(self, manager):
        """Given a failed enrichment job. Then NOT in pending."""
        job = manager.create_job("enrichment", "75192")
        manager.mark_failed(job.job_id, "error")
        pending = _get_pending_enrichment_set_numbers(manager)
        assert "75192" not in pending

    def test_ignores_non_enrichment_jobs(self, manager):
        """Given a shopee job. Then NOT in enrichment pending."""
        manager.create_job("shopee", "https://shopee.com.my/...")
        pending = _get_pending_enrichment_set_numbers(manager)
        assert len(pending) == 0

    def test_parses_source_from_url(self, manager):
        """Given enrichment job with source '75192:bricklink'.
        Then set number '75192' is in pending."""
        manager.create_job("enrichment", "75192:bricklink")
        pending = _get_pending_enrichment_set_numbers(manager)
        assert "75192" in pending


class TestQueueEnrichmentIfNeeded:
    """Tests for queue_enrichment_if_needed -- single set dedup."""

    def test_queues_new_set(self, manager):
        """Given no pending jobs for set. Then queues and returns True."""
        result = queue_enrichment_if_needed(manager, "75192")
        assert result is True
        assert len(manager.list_jobs()) == 1

    def test_skips_already_pending(self, manager):
        """Given already queued job for set. Then skips and returns False."""
        manager.create_job("enrichment", "75192")
        result = queue_enrichment_if_needed(manager, "75192")
        assert result is False
        assert len(manager.list_jobs()) == 1  # still just 1

    def test_skips_when_source_specific_pending(self, manager):
        """Given queued '75192:bricklink'. When queue '75192'.
        Then skips (same set number)."""
        manager.create_job("enrichment", "75192:bricklink")
        result = queue_enrichment_if_needed(manager, "75192")
        assert result is False

    def test_queues_after_previous_completed(self, manager):
        """Given previously completed enrichment. Then queues new one."""
        job = manager.create_job("enrichment", "75192")
        manager.mark_completed(job.job_id, items_found=5)
        result = queue_enrichment_if_needed(manager, "75192")
        assert result is True
        assert len(manager.list_jobs()) == 2


class TestQueueEnrichmentBatch:
    """Tests for queue_enrichment_batch -- multiple sets with dedup."""

    def test_queues_all_new(self, manager):
        """Given 3 new set numbers. Then all 3 queued."""
        queued = queue_enrichment_batch(manager, ["75192", "42151", "31009"])
        assert queued == 3
        assert len(manager.list_jobs()) == 3

    def test_deduplicates_against_pending(self, manager):
        """Given '75192' already pending. Then only queues the other 2."""
        manager.create_job("enrichment", "75192")
        queued = queue_enrichment_batch(manager, ["75192", "42151", "31009"])
        assert queued == 2
        assert len(manager.list_jobs()) == 3  # 1 existing + 2 new

    def test_deduplicates_within_batch(self, manager):
        """Given duplicate set numbers in batch. Then only queues unique."""
        queued = queue_enrichment_batch(
            manager, ["75192", "42151", "75192", "42151"]
        )
        assert queued == 2

    def test_empty_batch(self, manager):
        """Given empty list. Then queues 0."""
        queued = queue_enrichment_batch(manager, [])
        assert queued == 0
