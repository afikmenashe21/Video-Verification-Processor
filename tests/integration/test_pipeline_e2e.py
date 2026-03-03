"""End-to-end pipeline test using all 3 stages inline with MockRunner."""
from __future__ import annotations

import json
import os

from PIL import Image

from shared.domain import (
    Evidence,
    EvidenceKind,
    ModelAnalysis,
    VerificationResult,
    Verdict,
    VideoVerificationJob,
)
from preprocessor.reader import read_video_metadata
from preprocessor.sampling import FpsSampler
from analyzer.runners.registry import ModelRunnerRegistry
from analyzer.runners.mock_runner import MockRunner
from scorer.scoring import compute_score
from scorer.report_writer import format_text_report, format_json_metadata


def test_shouldProduceOutputFiles_whenProcessingValidJob(tmp_dir, sample_video, sample_ref_image):
    """Run all 3 stages inline and verify outputs."""
    output_dir = tmp_dir
    job_id = "test-job-001"
    video_path = sample_video
    images_path = [sample_ref_image]
    query = "Find the blue color in the video"
    model_name = "mock"

    # Stage 1: Preprocess
    metadata = read_video_metadata(video_path)
    sampler = FpsSampler(fps=1.0)
    frames = sampler.sample(video_path, 64)
    frame_images = [f.image for f in frames]

    ref_images = [Image.open(p).convert("RGB") for p in images_path]

    # Stage 2: Analyze
    registry = ModelRunnerRegistry()
    registry.register("mock", MockRunner)
    runner = registry.get("mock")

    job = VideoVerificationJob(
        job_id=job_id,
        video_path=video_path,
        images_path=images_path,
        query=query,
        model=model_name,
    )

    analysis = runner.analyze(job, frame_images, ref_images)

    # Stage 3: Score + Report
    has_ref = len(ref_images) > 0
    score, confidence, verdict = compute_score(analysis, has_ref)

    result = VerificationResult(
        score_0_100=score,
        confidence_0_1=confidence,
        verdict=verdict,
        summary=analysis.summary or "No summary available.",
        evidence=analysis.evidence,
        raw_model_output=analysis.raw_output,
    )

    latency_ms = 100.0

    report = format_text_report(job, result, model_name, latency_ms)
    txt_path = os.path.join(output_dir, f"{job_id}.txt")
    with open(txt_path, "w") as f:
        f.write(report)

    meta = format_json_metadata(job, result, model_name, latency_ms, len(frames))
    json_path = os.path.join(output_dir, f"{job_id}.json")
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)

    # Verify txt report
    assert os.path.exists(txt_path)
    txt_content = open(txt_path).read()
    assert "test-job-001" in txt_content
    assert "VERDICT" in txt_content or "Verdict" in txt_content

    # Verify json metadata
    assert os.path.exists(json_path)
    with open(json_path) as f:
        meta = json.load(f)
    assert meta["job_id"] == "test-job-001"
    assert meta["model"] == "mock"
    assert 0 <= meta["score"] <= 100
    assert meta["verdict"] in ("PASS", "FAIL", "UNCERTAIN")
    assert meta["stats"]["frames_sampled"] > 0
