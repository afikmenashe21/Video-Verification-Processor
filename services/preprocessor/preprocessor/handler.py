from __future__ import annotations

import json
import os

import structlog

from shared.domain import VideoVerificationJob
from shared.errors import ValidationError
from shared.events import (
    FramesExtracted,
    VideoMetadataEvent,
    VideoVerificationRequested,
)

from preprocessor.config import PreprocessorConfig
from preprocessor.reader import read_video_metadata
from preprocessor.sampling import FpsSampler

logger = structlog.get_logger()


class PreprocessorHandler:
    def __init__(self, config: PreprocessorConfig) -> None:
        self._config = config
        self._sampler = FpsSampler(fps=config.frame_sampling_fps)

    def handle(self, raw_value: bytes) -> tuple[str, FramesExtracted]:
        """Process a VideoVerificationRequested message.

        Returns (job_id, FramesExtracted event) for publishing.
        """
        # Deserialize
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}") from e

        try:
            request = VideoVerificationRequested.model_validate(payload)
        except Exception as e:
            raise ValidationError(f"Schema validation failed: {e}") from e

        job_id = request.job_id or VideoVerificationJob.generate_idempotency_key(
            request.video_path, request.images_path, request.query
        )

        log = logger.bind(job_id=job_id, model=request.model)
        log.info("processing_request", video_path=request.video_path)

        # Read video metadata
        metadata = read_video_metadata(request.video_path)
        log.info("video_metadata", duration_s=metadata.duration_s, fps=metadata.fps,
                 resolution=f"{metadata.width}x{metadata.height}")

        if metadata.duration_s > self._config.max_video_seconds:
            log.warning("video_exceeds_max_duration",
                        duration_s=metadata.duration_s, max_s=self._config.max_video_seconds)

        # Sample frames
        frames = self._sampler.sample(request.video_path, self._config.frame_sampling_max_frames)
        log.info("frames_sampled", count=len(frames))

        # Save frames to disk
        frames_dir = os.path.join(self._config.frames_base_dir, job_id)
        os.makedirs(frames_dir, exist_ok=True)

        timestamps: list[float] = []
        for i, frame in enumerate(frames):
            frame_path = os.path.join(frames_dir, f"frame_{i:04d}.jpg")
            frame.image.save(frame_path, format="JPEG", quality=85)
            timestamps.append(frame.timestamp_s)

        log.info("frames_saved", frames_dir=frames_dir, count=len(frames))

        # Build output event
        event = FramesExtracted(
            job_id=job_id,
            frames_dir=frames_dir,
            frame_count=len(frames),
            frame_timestamps_s=timestamps,
            images_path=request.images_path,
            query=request.query,
            model=request.model,
            video_metadata=VideoMetadataEvent(
                duration_s=metadata.duration_s,
                fps=metadata.fps,
                width=metadata.width,
                height=metadata.height,
                codec=metadata.codec,
            ),
        )

        return job_id, event
