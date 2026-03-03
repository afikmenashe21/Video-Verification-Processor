from __future__ import annotations

from shared.domain import EvidenceKind, ModelAnalysis, Verdict


def compute_score(analysis: ModelAnalysis, has_ref_images: bool) -> tuple[int, float, Verdict]:
    """Compute score (0-100), confidence (0-1), and verdict from model analysis.

    The model's verdict determines direction (match vs mismatch).
    Evidence quality and consistency refine the score within that direction.
    """
    model_verdict = analysis.verdict
    confidence = _compute_confidence(analysis)

    if model_verdict == Verdict.PASS:
        score = _score_pass(analysis, has_ref_images)
    elif model_verdict == Verdict.FAIL:
        score = _score_fail(analysis, has_ref_images)
    else:
        score = _score_uncertain(analysis)

    score = max(0, min(100, score))
    verdict = _determine_verdict(score, confidence)
    return score, confidence, verdict


def _score_pass(analysis: ModelAnalysis, has_ref_images: bool) -> int:
    """Model says PASS — score in 60-100 range based on evidence strength."""
    base = 65
    evidence_bonus = _evidence_quality_bonus(analysis, has_ref_images)
    return base + evidence_bonus


def _score_fail(analysis: ModelAnalysis, has_ref_images: bool) -> int:
    """Model says FAIL — score in 0-30 range. Stronger evidence = lower score."""
    base = 25
    evidence_penalty = _evidence_quality_bonus(analysis, has_ref_images)
    return base - evidence_penalty


def _score_uncertain(analysis: ModelAnalysis) -> int:
    """Model says UNCERTAIN — score in 30-55 range."""
    if not analysis.evidence:
        return 40

    avg_conf = sum(e.confidence for e in analysis.evidence) / len(analysis.evidence)
    return 30 + int(avg_conf * 25)


def _evidence_quality_bonus(analysis: ModelAnalysis, has_ref_images: bool) -> int:
    """Calculate bonus (0-30) based on evidence count and confidence."""
    if not analysis.evidence:
        return 0

    image_evidence = [e for e in analysis.evidence if e.kind == EvidenceKind.IMAGE_MATCH]
    other_evidence = [e for e in analysis.evidence if e.kind != EvidenceKind.IMAGE_MATCH]

    bonus = 0

    if has_ref_images and image_evidence:
        max_img_conf = max(e.confidence for e in image_evidence)
        bonus += int(max_img_conf * 15)
        bonus += min(5, len(image_evidence) - 1)

    if other_evidence:
        max_other_conf = max(e.confidence for e in other_evidence)
        bonus += int(max_other_conf * 8)

    confidences = [e.confidence for e in analysis.evidence]
    spread = max(confidences) - min(confidences) if len(confidences) > 1 else 0.0
    if spread < 0.2:
        bonus += 2

    return min(30, bonus)


def _compute_confidence(analysis: ModelAnalysis) -> float:
    if analysis.confidence is not None:
        base = analysis.confidence
    elif analysis.evidence:
        base = sum(e.confidence for e in analysis.evidence) / len(analysis.evidence)
    else:
        base = 0.3

    if analysis.evidence:
        evidence_boost = min(0.1, len(analysis.evidence) * 0.02)
        base = min(1.0, base + evidence_boost)

    return round(min(1.0, max(0.0, base)), 2)


def _determine_verdict(score: int, confidence: float) -> Verdict:
    if confidence < 0.3:
        return Verdict.UNCERTAIN

    if score >= 60 and confidence >= 0.5:
        return Verdict.PASS
    if score < 35:
        return Verdict.FAIL

    return Verdict.UNCERTAIN
