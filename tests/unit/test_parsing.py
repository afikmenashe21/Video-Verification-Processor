import json

from shared.domain import EvidenceKind, Verdict
from analyzer.parsing import parse_model_output


def test_shouldParseCleanJson():
    data = {
        "verdict": "PASS",
        "confidence": 0.85,
        "evidence": [
            {
                "kind": "QUERY_MATCH",
                "text": "Red car found at 5s",
                "confidence": 0.9,
                "timestamp_start_s": 5.0,
                "timestamp_end_s": 8.0,
            }
        ],
        "summary": "Red car confirmed.",
    }
    result = parse_model_output(json.dumps(data))
    assert result.verdict == Verdict.PASS
    assert result.confidence == 0.85
    assert len(result.evidence) == 1
    assert result.evidence[0].kind == EvidenceKind.QUERY_MATCH
    assert result.summary == "Red car confirmed."


def test_shouldParseMarkdownFencedJson():
    raw = '```json\n{"verdict": "FAIL", "confidence": 0.3, "evidence": [], "summary": "Nothing found."}\n```'
    result = parse_model_output(raw)
    assert result.verdict == Verdict.FAIL
    assert result.confidence == 0.3


def test_shouldFallbackToRegex_whenInvalidJson():
    raw = 'The "verdict": "UNCERTAIN" and "confidence": 0.45. Some text with "summary": "Unclear results".'
    result = parse_model_output(raw)
    assert result.verdict == Verdict.UNCERTAIN
    assert result.confidence == 0.45
    assert result.summary == "Unclear results"


def test_shouldHandleCompleteGarbage():
    result = parse_model_output("random nonsense without any structured data")
    assert result.verdict is None
    assert result.confidence is None
    assert result.evidence == []


def test_shouldClampConfidence():
    data = {"verdict": "PASS", "confidence": 1.5, "evidence": [], "summary": "ok"}
    result = parse_model_output(json.dumps(data))
    assert result.confidence == 1.0


def test_shouldHandleMissingFields():
    data = {"verdict": "PASS"}
    result = parse_model_output(json.dumps(data))
    assert result.verdict == Verdict.PASS
    assert result.evidence == []
