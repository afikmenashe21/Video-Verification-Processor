from __future__ import annotations

import uuid

from shared.events import VideoDownloadReady, VideoVerificationRequested


class TestVideoDownloadReady:
    def test_shouldSerializeAndDeserialize(self):
        event = VideoDownloadReady(
            task_id=str(uuid.uuid4()),
            job_id=str(uuid.uuid4()),
            download_url="https://cdn.example.com/video.mp4",
            source_url="https://tiktok.com/@user/video/123",
            product_id=str(uuid.uuid4()),
        )
        json_bytes = event.model_dump_json().encode()
        parsed = VideoDownloadReady.model_validate_json(json_bytes)
        assert parsed.task_id == event.task_id
        assert parsed.download_url == event.download_url


class TestVideoVerificationRequestedExtended:
    def test_shouldAcceptNewOptionalFields(self):
        event = VideoVerificationRequested(
            video_path="/data/videos/test.mp4",
            query="find shoes",
            video_task_id=str(uuid.uuid4()),
            product_id=str(uuid.uuid4()),
        )
        assert event.video_task_id is not None
        assert event.product_id is not None

    def test_shouldDefaultNewFieldsToNone(self):
        event = VideoVerificationRequested(
            video_path="/data/videos/test.mp4",
            query="find shoes",
        )
        assert event.video_task_id is None
        assert event.product_id is None
