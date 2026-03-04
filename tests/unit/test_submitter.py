from __future__ import annotations

import uuid

import pytest

from submitter.schemas import CreateJobRequest, JobResponse, TaskResponse


class TestSchemas:
    def test_shouldAcceptValidCreateJobRequest(self):
        req = CreateJobRequest(
            product_id=str(uuid.uuid4()),
            urls=["https://tiktok.com/v1", "https://tiktok.com/v2"],
        )
        assert len(req.urls) == 2

    def test_shouldRejectEmptyUrls(self):
        with pytest.raises(Exception):
            CreateJobRequest(product_id=str(uuid.uuid4()), urls=[])

    def test_shouldBuildJobResponse(self):
        resp = JobResponse(
            job_id=str(uuid.uuid4()),
            product_id=str(uuid.uuid4()),
            status="IN_PROGRESS",
            match_target=3,
            match_count=0,
            total_urls=5,
            completed_count=0,
            created_at="2026-03-04T00:00:00Z",
        )
        assert resp.status == "IN_PROGRESS"
        assert resp.match_target == 3

    def test_shouldBuildTaskResponse(self):
        resp = TaskResponse(
            task_id=str(uuid.uuid4()),
            source_url="https://tiktok.com/v1",
            status="COMPLETED",
            score=85,
            confidence=0.9,
            verdict="PASS",
        )
        assert resp.verdict == "PASS"

    def test_shouldAllowNullableFields(self):
        resp = TaskResponse(
            task_id=str(uuid.uuid4()),
            source_url="https://tiktok.com/v1",
            status="PENDING",
        )
        assert resp.score is None
        assert resp.verdict is None
