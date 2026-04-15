"""Tests for the Shopee captcha gate + JobManager blocked_verify flow."""

from __future__ import annotations

from api.jobs import JobManager
from api.schemas import JobStatus


class TestBlockedVerifyFlow:
    def test_mark_blocked_verify_sets_status_and_event(self):
        mgr = JobManager()
        job = mgr.create_job("shopee", "https://shopee.com.my/legoshopmy")
        mgr.mark_blocked_verify(job.job_id, event_id=42)

        updated = mgr.get_job(job.job_id)
        assert updated.status == JobStatus.BLOCKED_VERIFY
        assert updated.blocked_by_event_id == 42
        assert "captcha event #42" in (updated.error or "")

    def test_requeue_blocked_resumes_matching_jobs(self):
        mgr = JobManager()
        a = mgr.create_job("shopee", "https://shopee.com.my/shop-a")
        b = mgr.create_job("shopee", "https://shopee.com.my/shop-b")
        c = mgr.create_job("shopee", "https://shopee.com.my/shop-c")

        mgr.mark_blocked_verify(a.job_id, event_id=1)
        mgr.mark_blocked_verify(b.job_id, event_id=1)
        mgr.mark_blocked_verify(c.job_id, event_id=2)

        resumed = mgr.requeue_blocked(event_id=1)
        assert set(resumed) == {a.job_id, b.job_id}
        assert mgr.get_job(a.job_id).status == JobStatus.QUEUED
        assert mgr.get_job(b.job_id).status == JobStatus.QUEUED
        assert mgr.get_job(c.job_id).status == JobStatus.BLOCKED_VERIFY
        assert mgr.get_job(a.job_id).blocked_by_event_id is None

    def test_has_blocked_shopee_jobs(self):
        mgr = JobManager()
        assert mgr.has_blocked_shopee_jobs() is False
        job = mgr.create_job("shopee_saturation", "batch")
        mgr.mark_blocked_verify(job.job_id, event_id=7)
        assert mgr.has_blocked_shopee_jobs() is True

    def test_non_shopee_blocked_ignored_by_gate_helper(self):
        mgr = JobManager()
        job = mgr.create_job("toysrus", "https://example.com")
        mgr.mark_blocked_verify(job.job_id, event_id=99)
        # toysrus does not start with "shopee"
        assert mgr.has_blocked_shopee_jobs() is False
