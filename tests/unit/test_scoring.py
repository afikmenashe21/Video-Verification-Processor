from shared.domain import Evidence, EvidenceKind, ModelAnalysis, Verdict
from scorer.scoring import compute_score


def _analysis(
    verdict: Verdict | None = None,
    confidence: float | None = None,
    evidence: list[Evidence] | None = None,
    summary: str = "test",
) -> ModelAnalysis:
    return ModelAnalysis(
        raw_output="test",
        verdict=verdict,
        confidence=confidence,
        evidence=evidence or [],
        summary=summary,
    )


class TestComputeScore:
    def shouldReturnHighScore_whenModelPassesWithEvidence(self):
        evidence = [
            Evidence(kind=EvidenceKind.IMAGE_MATCH, text="product matches", confidence=0.9),
        ]
        analysis = _analysis(verdict=Verdict.PASS, confidence=0.85, evidence=evidence)
        score, conf, verdict = compute_score(analysis, has_ref_images=True)
        assert score >= 70
        assert verdict == Verdict.PASS

    def shouldReturnLowScore_whenModelFails(self):
        evidence = [
            Evidence(kind=EvidenceKind.IMAGE_MATCH, text="product does not match", confidence=0.95),
        ]
        analysis = _analysis(verdict=Verdict.FAIL, confidence=0.9, evidence=evidence)
        score, conf, verdict = compute_score(analysis, has_ref_images=True)
        assert score < 20
        assert verdict == Verdict.FAIL

    def shouldReturnMidScore_whenUncertain(self):
        analysis = _analysis(verdict=Verdict.UNCERTAIN, confidence=0.5)
        score, conf, verdict = compute_score(analysis, has_ref_images=False)
        assert 30 <= score <= 55
        assert verdict == Verdict.UNCERTAIN

    def shouldReturnUncertain_whenLowConfidence(self):
        analysis = _analysis(verdict=Verdict.PASS, confidence=0.2)
        _, _, verdict = compute_score(analysis, has_ref_images=False)
        assert verdict == Verdict.UNCERTAIN

    def shouldHandleNoEvidence(self):
        analysis = _analysis(verdict=Verdict.PASS, confidence=0.8)
        score, conf, verdict = compute_score(analysis, has_ref_images=False)
        assert score >= 60
        assert verdict == Verdict.PASS

    def shouldHandleAllNone(self):
        analysis = _analysis()
        score, conf, verdict = compute_score(analysis, has_ref_images=False)
        assert 0 <= score <= 100
        assert 0.0 <= conf <= 1.0
        assert verdict in (Verdict.PASS, Verdict.FAIL, Verdict.UNCERTAIN)

    def shouldCapScoreAt100(self):
        evidence = [
            Evidence(kind=EvidenceKind.IMAGE_MATCH, text="match", confidence=1.0),
            Evidence(kind=EvidenceKind.IMAGE_MATCH, text="match2", confidence=1.0),
            Evidence(kind=EvidenceKind.QUERY_MATCH, text="q", confidence=1.0),
        ]
        analysis = _analysis(verdict=Verdict.PASS, confidence=1.0, evidence=evidence)
        score, _, _ = compute_score(analysis, has_ref_images=True)
        assert score <= 100

    def shouldNotGiveHighScore_whenModelFailsWithStrongEvidence(self):
        """Regression: model FAIL + high confidence evidence should yield low score."""
        evidence = [
            Evidence(kind=EvidenceKind.QUERY_MATCH, text="mismatch", confidence=1.0),
            Evidence(kind=EvidenceKind.QUERY_MATCH, text="mismatch2", confidence=1.0),
            Evidence(kind=EvidenceKind.IMAGE_MATCH, text="different product", confidence=1.0),
        ]
        analysis = _analysis(verdict=Verdict.FAIL, confidence=1.0, evidence=evidence)
        score, _, verdict = compute_score(analysis, has_ref_images=True)
        assert score < 10
        assert verdict == Verdict.FAIL


def test_scoring_basic():
    """Run all scoring tests."""
    t = TestComputeScore()
    t.shouldReturnHighScore_whenModelPassesWithEvidence()
    t.shouldReturnLowScore_whenModelFails()
    t.shouldReturnMidScore_whenUncertain()
    t.shouldReturnUncertain_whenLowConfidence()
    t.shouldHandleNoEvidence()
    t.shouldHandleAllNone()
    t.shouldCapScoreAt100()
    t.shouldNotGiveHighScore_whenModelFailsWithStrongEvidence()
