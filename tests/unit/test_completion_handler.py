from __future__ import annotations

import json
import uuid

import pytest

from shared.events import VerificationCompleted


def _make_completed_event(job_id: str, verdict: str = "PASS", score: int = 85) -> bytes:
    event = VerificationCompleted(
        job_id=job_id,
        score=score,
        confidence=0.9,
        verdict=verdict,
        summary="Test summary",
        output_txt_path="/data/output/test.txt",
        output_json_path="/data/output/test.json",
    )
    return event.model_dump_json().encode()


class FakeCursor:
    """Minimal cursor mock — returns results from a queue on fetchone()."""

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


class TestCompletionHandler:
    def test_shouldSkip_whenTaskAlreadyTerminal(self):
        from completion_handler.handler import CompletionHandler

        # UPDATE video_tasks ... RETURNING job_id → None (0 rows affected)
        cursor = FakeCursor([None])
        conn = FakeConnection(cursor)
        handler = CompletionHandler(conn)

        raw = _make_completed_event("some-task-id", "PASS")
        handler.handle(raw)

        assert len(cursor.executed) == 1
        assert "UPDATE video_tasks" in cursor.executed[0][0]

    def test_shouldIncrementMatchCount_whenVerdictIsPass(self):
        from completion_handler.handler import CompletionHandler

        job_id = str(uuid.uuid4())

        # Sequence of fetchone results:
        # 1. UPDATE video_tasks RETURNING job_id
        # 2. UPDATE match_count RETURNING match_count, match_target (completed_count UPDATE has no fetchone)
        # 3. SELECT counts (pending check)
        cursor = FakeCursor([
            {"job_id": job_id},                      # task update
            {"match_count": 1, "match_target": 3},   # match_count increment
            {"pending": 5, "total": 10},             # pending check
        ])
        conn = FakeConnection(cursor)
        handler = CompletionHandler(conn)

        raw = _make_completed_event("some-task-id", "PASS")
        handler.handle(raw)

        queries = [q[0] for q in cursor.executed]
        assert any("match_count = match_count + 1" in q for q in queries)

    def test_shouldNotIncrementMatchCount_whenVerdictIsFail(self):
        from completion_handler.handler import CompletionHandler

        job_id = str(uuid.uuid4())

        # Sequence of fetchone results:
        # 1. UPDATE video_tasks RETURNING job_id
        # 2. SELECT counts (no match_count increment for FAIL)
        cursor = FakeCursor([
            {"job_id": job_id},
            {"pending": 5, "total": 10},
        ])
        conn = FakeConnection(cursor)
        handler = CompletionHandler(conn)

        raw = _make_completed_event("some-task-id", "FAIL", score=20)
        handler.handle(raw)

        queries = [q[0] for q in cursor.executed]
        assert not any("match_count = match_count + 1" in q for q in queries)

    def test_shouldTriggerEarlyTermination_whenMatchTargetReached(self):
        from completion_handler.handler import CompletionHandler

        job_id = str(uuid.uuid4())

        # Sequence of fetchone results:
        # 1. UPDATE video_tasks RETURNING job_id
        # 2. UPDATE match_count RETURNING match_count, match_target → target reached
        cursor = FakeCursor([
            {"job_id": job_id},
            {"match_count": 3, "match_target": 3},
        ])
        conn = FakeConnection(cursor)
        handler = CompletionHandler(conn)

        raw = _make_completed_event("some-task-id", "PASS")
        handler.handle(raw)

        queries = [q[0] for q in cursor.executed]
        assert any("SET status = 'SKIPPED'" in q for q in queries)
        assert any("SET status = 'COMPLETED'" in q for q in queries)

    def test_shouldRejectInvalidJson(self):
        from completion_handler.handler import CompletionHandler
        from shared.errors import ValidationError

        cursor = FakeCursor([])
        conn = FakeConnection(cursor)
        handler = CompletionHandler(conn)

        with pytest.raises(ValidationError):
            handler.handle(b"not json")
