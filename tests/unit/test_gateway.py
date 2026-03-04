from __future__ import annotations

import uuid

import pytest

from gateway.handler import WebhookHandler, _extract_download_url


class TestExtractDownloadUrl:
    def test_shouldExtractDirectField(self):
        payload = {"downloadUrl": "https://example.com/video.mp4"}
        assert _extract_download_url(payload) == "https://example.com/video.mp4"

    def test_shouldExtractFromResourceOutput(self):
        payload = {
            "resource": {
                "id": "run-123",
                "output": {"downloadUrl": "https://example.com/video.mp4"},
            }
        }
        assert _extract_download_url(payload) == "https://example.com/video.mp4"

    def test_shouldExtractFromItems(self):
        payload = {
            "items": [{"videoUrl": "https://example.com/video.mp4"}]
        }
        assert _extract_download_url(payload) == "https://example.com/video.mp4"

    def test_shouldReturnNone_whenNoDownloadUrl(self):
        payload = {"resource": {"id": "run-123"}}
        assert _extract_download_url(payload) is None


class FakeCursor:
    def __init__(self, results: list[dict | None]):
        self._results = list(results)
        self._idx = 0
        self.rowcount = 1
        self.executed: list[tuple[str, dict]] = []

    def execute(self, query: str, params: dict | None = None):
        self.executed.append((query, params or {}))

    def fetchone(self) -> dict | None:
        if self._idx < len(self._results):
            result = self._results[self._idx]
            self._idx += 1
            return result
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass


class FakeProducer:
    def __init__(self):
        self.produced: list[dict] = []

    def produce(self, **kwargs):
        self.produced.append(kwargs)

    def flush(self):
        pass


class TestWebhookHandler:
    def test_shouldReturnFalse_whenTaskNotFound(self):
        cursor = FakeCursor([None])
        conn = FakeConnection(cursor)
        producer = FakeProducer()
        handler = WebhookHandler(conn, producer)

        result = handler.handle_apify_webhook(str(uuid.uuid4()), {"downloadUrl": "http://x.com/v.mp4"})
        assert result is False
        assert len(producer.produced) == 0

    def test_shouldReturnFalse_whenTaskSkipped(self):
        task_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        product_id = str(uuid.uuid4())

        cursor = FakeCursor([
            {"id": task_id, "status": "SKIPPED", "source_url": "http://x.com", "job_id": job_id, "product_id": product_id}
        ])
        conn = FakeConnection(cursor)
        producer = FakeProducer()
        handler = WebhookHandler(conn, producer)

        result = handler.handle_apify_webhook(task_id, {"downloadUrl": "http://x.com/v.mp4"})
        assert result is False

    def test_shouldPublishEvent_whenTaskActive(self):
        task_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        product_id = str(uuid.uuid4())

        cursor = FakeCursor([
            {"id": task_id, "status": "APIFY_SUBMITTED", "source_url": "http://tiktok.com/v1", "job_id": job_id, "product_id": product_id},
        ])
        conn = FakeConnection(cursor)
        producer = FakeProducer()
        handler = WebhookHandler(conn, producer)

        result = handler.handle_apify_webhook(task_id, {"downloadUrl": "http://cdn.example.com/video.mp4"})
        assert result is True
        assert len(producer.produced) == 1
        assert producer.produced[0]["topic"] == "video.download.ready.v1"
