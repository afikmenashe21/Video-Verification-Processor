from __future__ import annotations

from shared.domain import VerificationResult, VideoVerificationJob


def format_text_report(job: VideoVerificationJob, result: VerificationResult, model_name: str, latency_ms: float) -> str:
    lines = [
        "=" * 60,
        "VIDEO VERIFICATION REPORT",
        "=" * 60,
        "",
        f"Job ID:      {job.job_id}",
        f"Model:       {model_name}",
        f"Video:       {job.video_path}",
        f"Query:       {job.query}",
        f"Ref Images:  {len(job.images_path)}",
        f"Runtime:     {latency_ms:.0f} ms",
        "",
        "-" * 40,
        "VERDICT & SCORE",
        "-" * 40,
        f"Verdict:     {result.verdict.value}",
        f"Score:       {result.score_0_100} / 100",
        f"Confidence:  {result.confidence_0_1:.2f}",
        "",
    ]

    if result.evidence:
        lines.append("-" * 40)
        lines.append("EVIDENCE")
        lines.append("-" * 40)
        for i, e in enumerate(result.evidence, 1):
            ts = ""
            if e.timestamp_start_s is not None:
                ts = f" [{e.timestamp_start_s:.1f}s"
                if e.timestamp_end_s is not None:
                    ts += f" - {e.timestamp_end_s:.1f}s"
                ts += "]"
            lines.append(f"  {i}. [{e.kind.value}] (conf={e.confidence:.2f}){ts}")
            lines.append(f"     {e.text}")
        lines.append("")

    lines.append("-" * 40)
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(result.summary)
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_json_metadata(
    job: VideoVerificationJob,
    result: VerificationResult,
    model_name: str,
    latency_ms: float,
    frames_sampled: int,
) -> dict:
    return {
        "job_id": job.job_id,
        "model": model_name,
        "inputs": {
            "video_path": job.video_path,
            "images_path": job.images_path,
            "query": job.query,
        },
        "score": result.score_0_100,
        "confidence": result.confidence_0_1,
        "verdict": result.verdict.value,
        "summary": result.summary,
        "evidence": [
            {
                "kind": e.kind.value,
                "text": e.text,
                "confidence": e.confidence,
                "timestamp_start_s": e.timestamp_start_s,
                "timestamp_end_s": e.timestamp_end_s,
            }
            for e in result.evidence
        ],
        "stats": {
            "latency_ms": latency_ms,
            "frames_sampled": frames_sampled,
        },
    }
