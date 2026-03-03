from __future__ import annotations

import json
import os

import structlog

from shared.domain import (
    Evidence,
    EvidenceKind,
    ModelAnalysis,
    VerificationResult,
    Verdict,
    VideoVerificationJob,
)
from shared.errors import ValidationError
from shared.events import AnalysisCompleted, VerificationCompleted

from scorer.config import ScorerConfig
from scorer.report_writer import format_json_metadata, format_text_report
from scorer.scoring import compute_score

logger = structlog.get_logger()


class ScorerHandler:
    def __init__(self, config: ScorerConfig) -> None:
        self._config = config

    def handle(self, raw_value: bytes) -> tuple[str, VerificationCompleted]:
        """Process an AnalysisCompleted message.

        Returns (job_id, VerificationCompleted event) for publishing.
        """
        # Deserialize
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}") from e

        try:
            event = AnalysisCompleted.model_validate(payload)
        except Exception as e:
            raise ValidationError(f"Schema validation failed: {e}") from e

        log = logger.bind(job_id=event.job_id, model=event.model)
        log.info("processing_analysis")

        # Reconstruct domain objects from event
        evidence_list = [
            Evidence(
                kind=EvidenceKind(e.kind) if e.kind in EvidenceKind.__members__ else EvidenceKind.OTHER,
                text=e.text,
                confidence=e.confidence,
                timestamp_start_s=e.timestamp_start_s,
                timestamp_end_s=e.timestamp_end_s,
            )
            for e in event.analysis.evidence
        ]

        verdict_val = None
        try:
            verdict_val = Verdict(event.analysis.verdict)
        except ValueError:
            pass

        analysis = ModelAnalysis(
            raw_output=event.analysis.raw_output,
            verdict=verdict_val,
            confidence=event.analysis.confidence,
            evidence=evidence_list,
            summary=event.analysis.summary,
        )

        # Score
        has_ref = len(event.images_path) > 0
        score, confidence, verdict = compute_score(analysis, has_ref)

        result = VerificationResult(
            score_0_100=score,
            confidence_0_1=confidence,
            verdict=verdict,
            summary=analysis.summary or "No summary available.",
            evidence=evidence_list,
            raw_model_output=analysis.raw_output,
        )

        # Build job for report writer
        job = VideoVerificationJob(
            job_id=event.job_id,
            video_path=event.video_path,
            images_path=event.images_path,
            query=event.query,
            model=event.model,
        )

        latency_ms = event.latency_ms

        # Write outputs
        txt_path = os.path.join(self._config.output_dir, f"{event.job_id}.txt")
        json_path = os.path.join(self._config.output_dir, f"{event.job_id}.json")

        os.makedirs(self._config.output_dir, exist_ok=True)

        report = format_text_report(job, result, event.model, latency_ms)
        with open(txt_path, "w") as f:
            f.write(report)

        meta = format_json_metadata(job, result, event.model, latency_ms, event.frames_sampled)
        with open(json_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        log.info("output_written", txt_path=txt_path, json_path=json_path,
                 score=score, verdict=verdict.value)

        completed = VerificationCompleted(
            job_id=event.job_id,
            score=score,
            confidence=confidence,
            verdict=verdict.value,
            summary=result.summary,
            output_txt_path=txt_path,
            output_json_path=json_path,
        )

        return event.job_id, completed
