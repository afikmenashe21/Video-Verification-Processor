from __future__ import annotations

from PIL import Image

from shared.domain import (
    Evidence,
    EvidenceKind,
    ModelAnalysis,
    RunnerHealth,
    Verdict,
    VideoVerificationJob,
)
from analyzer.runners.port import ModelRunnerPort


class MockRunner(ModelRunnerPort):
    """Deterministic mock runner for pipeline testing."""

    def name(self) -> str:
        return "mock"

    def supports(self, *, video: bool, images: bool) -> bool:
        return True

    def analyze(
        self,
        job: VideoVerificationJob,
        frame_images: list[Image.Image],
        ref_images: list[Image.Image],
    ) -> ModelAnalysis:
        evidence: list[Evidence] = []

        if frame_images:
            evidence.append(
                Evidence(
                    kind=EvidenceKind.QUERY_MATCH,
                    text=f"Mock analysis of {len(frame_images)} frames for query: {job.query[:50]}",
                    confidence=0.75,
                )
            )

        for i, _ in enumerate(ref_images):
            evidence.append(
                Evidence(
                    kind=EvidenceKind.IMAGE_MATCH,
                    text=f"Mock: reference image {i + 1} found in video",
                    confidence=0.70,
                )
            )

        return ModelAnalysis(
            raw_output="MOCK_OUTPUT",
            verdict=Verdict.PASS if evidence else Verdict.UNCERTAIN,
            confidence=0.75 if evidence else 0.3,
            evidence=evidence,
            summary=f"Mock verification of '{job.query[:80]}' across {len(frame_images)} frames and {len(ref_images)} ref images.",
        )

    def healthcheck(self) -> RunnerHealth:
        return RunnerHealth(name="mock", healthy=True, detail="Mock runner always healthy")
