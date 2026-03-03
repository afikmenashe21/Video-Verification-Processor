import pytest
from pydantic import ValidationError

from shared.events import VideoVerificationRequested


def test_shouldAcceptValidPayload():
    req = VideoVerificationRequested(
        video_path="/data/video.mp4",
        images_path=["/data/img1.jpg"],
        query="Find the person",
        model="gemini",
    )
    assert req.video_path == "/data/video.mp4"
    assert req.model == "gemini"


def test_shouldAcceptMinimalPayload():
    req = VideoVerificationRequested(
        video_path="/data/video.mp4",
        query="Check video",
    )
    assert req.images_path == []
    assert req.model == "gemini"
    assert req.job_id is None


def test_shouldRejectMissingVideoPath():
    with pytest.raises(ValidationError):
        VideoVerificationRequested(query="Check")


def test_shouldRejectMissingQuery():
    with pytest.raises(ValidationError):
        VideoVerificationRequested(video_path="/data/v.mp4")


def test_shouldAcceptMetadata():
    req = VideoVerificationRequested(
        video_path="/v.mp4",
        query="test",
        metadata={"requested_by": "service-x"},
    )
    assert req.metadata["requested_by"] == "service-x"
