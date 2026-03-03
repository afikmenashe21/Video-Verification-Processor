"""End-to-end test with real test resources and MockRunner."""
from __future__ import annotations

import json
import os
import tempfile

from PIL import Image

from shared.domain import (
    VerificationResult,
    VideoVerificationJob,
)
from preprocessor.reader import read_video_metadata
from preprocessor.sampling import FpsSampler
from analyzer.runners.registry import ModelRunnerRegistry
from analyzer.runners.mock_runner import MockRunner
from scorer.scoring import compute_score
from scorer.report_writer import format_text_report, format_json_metadata

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIDEOS_DIR = os.path.join(BASE, "test_resources", "videos")
IMAGES_DIR = os.path.join(BASE, "test_resources", "images")

QUERY = """Golden Product Description (Technical Specs)
Brand: Nike (Jordan Brand).
Model: Air Jordan 1 Low.
Colorway: Gorge Green / Fierce Pink / Sail.
Primary Material: Smooth premium leather throughout the upper.
Color Distribution:
  Base & Overlays: Monochromatic deep forest green (Gorge Green) leather across the toe box, mid-panel, and overlays.
  Swoosh: Vibrant, high-contrast neon pink (Fierce Pink) stitched on the lateral and medial sides.
  Midsole: Sail/Off-white textured rubber for a vintage aesthetic.
  Outsole: Solid Gorge Green rubber with classic AJ1 traction pattern.
Branding & Details:
  Tongue: Green nylon with a vibrant pink Jumpman logo embroidered on the top.
  Heel: Vibrant pink "Wings" logo embroidered on the heel counter.
  Laces: Flat, tonal deep green laces matching the leather overlays.
Silhouette: Low-top profile designed specifically for the women's category."""


def _run_job(video_name: str, output_dir: str) -> dict:
    video_path = os.path.join(VIDEOS_DIR, video_name)
    images = [
        os.path.join(IMAGES_DIR, "jordan_1.jpeg"),
        os.path.join(IMAGES_DIR, "jordan_2.jpeg"),
    ]

    job_id = f"e2e-{video_name.replace('.', '-')}"
    model_name = "mock"

    # Stage 1: Preprocess
    metadata = read_video_metadata(video_path)
    sampler = FpsSampler(fps=1.0)
    frames = sampler.sample(video_path, 64)
    frame_images = [f.image for f in frames]

    ref_images = [Image.open(p).convert("RGB") for p in images]

    # Stage 2: Analyze
    registry = ModelRunnerRegistry()
    registry.register("mock", MockRunner)
    runner = registry.get("mock")

    job = VideoVerificationJob(
        job_id=job_id,
        video_path=video_path,
        images_path=images,
        query=QUERY,
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

    import time
    latency_ms = 50.0

    report = format_text_report(job, result, model_name, latency_ms)
    txt_path = os.path.join(output_dir, f"{job_id}.txt")
    with open(txt_path, "w") as f:
        f.write(report)

    meta = format_json_metadata(job, result, model_name, latency_ms, len(frames))
    json_path = os.path.join(output_dir, f"{job_id}.json")
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)

    return {
        "job_id": job_id,
        "metadata": meta,
        "report": report,
    }


def test_vid1_e2e():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_job("vid_1.mp4", tmp)

        meta = result["metadata"]
        assert meta["job_id"] == "e2e-vid_1-mp4"
        assert meta["model"] == "mock"
        assert 0 <= meta["score"] <= 100
        assert meta["verdict"] in ("PASS", "FAIL", "UNCERTAIN")
        assert meta["stats"]["frames_sampled"] > 0
        assert meta["stats"]["frames_sampled"] <= 64
        assert len(meta["evidence"]) >= 1

        print(f"\n--- vid_1.mp4 results ---")
        print(f"Score: {meta['score']}/100, Verdict: {meta['verdict']}, Confidence: {meta['confidence']}")
        print(f"Frames sampled: {meta['stats']['frames_sampled']}")
        print(f"Evidence items: {len(meta['evidence'])}")


def test_vid2_e2e():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_job("vid_2.mp4", tmp)

        meta = result["metadata"]
        assert meta["job_id"] == "e2e-vid_2-mp4"
        assert meta["model"] == "mock"
        assert 0 <= meta["score"] <= 100
        assert meta["stats"]["frames_sampled"] > 0
        assert meta["stats"]["frames_sampled"] <= 64

        print(f"\n--- vid_2.mp4 results ---")
        print(f"Score: {meta['score']}/100, Verdict: {meta['verdict']}, Confidence: {meta['confidence']}")
        print(f"Frames sampled: {meta['stats']['frames_sampled']}")
        print(f"Evidence items: {len(meta['evidence'])}")
