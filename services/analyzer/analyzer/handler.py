from __future__ import annotations

import json
import os
import shutil
import time

import structlog
from PIL import Image

from shared.domain import VideoVerificationJob
from shared.errors import ValidationError
from shared.events import (
    AnalysisCompleted,
    AnalysisEvent,
    EvidenceEvent,
    FramesExtracted,
)

from analyzer.config import AnalyzerConfig
from analyzer.runners.registry import ModelRunnerRegistry

logger = structlog.get_logger()


class AnalyzerHandler:
    def __init__(self, config: AnalyzerConfig, registry: ModelRunnerRegistry) -> None:
        self._config = config
        self._registry = registry

    def handle(self, raw_value: bytes) -> tuple[str, AnalysisCompleted]:
        """Process a FramesExtracted message.

        Returns (job_id, AnalysisCompleted event) for publishing.
        """
        # Deserialize
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}") from e

        try:
            event = FramesExtracted.model_validate(payload)
        except Exception as e:
            raise ValidationError(f"Schema validation failed: {e}") from e

        log = logger.bind(job_id=event.job_id, model=event.model)
        log.info("processing_frames", frames_dir=event.frames_dir, frame_count=event.frame_count)

        start = time.monotonic()

        # Resolve model runner
        model_name = event.model
        if model_name not in self._registry.available_models():
            model_name = self._config.model_default
        runner = self._registry.get(model_name)

        # Load frames from disk
        frame_images: list[Image.Image] = []
        for i in range(event.frame_count):
            frame_path = os.path.join(event.frames_dir, f"frame_{i:04d}.jpg")
            if os.path.exists(frame_path):
                frame_images.append(Image.open(frame_path).convert("RGB"))
        log.info("frames_loaded", count=len(frame_images))

        # Load reference images
        ref_images: list[Image.Image] = []
        for img_path in event.images_path:
            ref_images.append(Image.open(img_path).convert("RGB"))
        log.info("ref_images_loaded", count=len(ref_images))

        # Build a job object for the runner
        job = VideoVerificationJob(
            job_id=event.job_id,
            video_path="",
            images_path=event.images_path,
            query=event.query,
            model=model_name,
        )

        # Run inference
        analysis = runner.analyze(job, frame_images, ref_images)
        latency_ms = (time.monotonic() - start) * 1000
        log.info("inference_complete", verdict=analysis.verdict, confidence=analysis.confidence,
                 latency_ms=latency_ms)

        # Cleanup frames directory
        try:
            shutil.rmtree(event.frames_dir)
            log.info("frames_cleaned_up", frames_dir=event.frames_dir)
        except OSError as e:
            log.warning("frames_cleanup_failed", frames_dir=event.frames_dir, error=str(e))

        # Build output event
        evidence_events = [
            EvidenceEvent(
                kind=e.kind.value,
                text=e.text,
                confidence=e.confidence,
                timestamp_start_s=e.timestamp_start_s,
                timestamp_end_s=e.timestamp_end_s,
            )
            for e in analysis.evidence
        ]

        completed = AnalysisCompleted(
            job_id=event.job_id,
            model=model_name,
            query=event.query,
            images_path=event.images_path,
            frames_sampled=event.frame_count,
            analysis=AnalysisEvent(
                raw_output=analysis.raw_output,
                verdict=analysis.verdict.value if analysis.verdict else "UNCERTAIN",
                confidence=analysis.confidence if analysis.confidence is not None else 0.0,
                evidence=evidence_events,
                summary=analysis.summary or "No summary available.",
            ),
            latency_ms=latency_ms,
        )

        return event.job_id, completed
