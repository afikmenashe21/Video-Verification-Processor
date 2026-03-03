from __future__ import annotations

import json
import re

import structlog

from shared.domain import Evidence, EvidenceKind, ModelAnalysis, Verdict

logger = structlog.get_logger()

_VERDICT_PATTERN = re.compile(r'"verdict"\s*:\s*"(PASS|FAIL|UNCERTAIN)"', re.IGNORECASE)
_CONFIDENCE_PATTERN = re.compile(r'"confidence"\s*:\s*(\d+(?:\.\d+)?)')
_SUMMARY_PATTERN = re.compile(r'"summary"\s*:\s*"([^"]*)"')


def parse_model_output(raw: str) -> ModelAnalysis:
    """Parse VLM free-text output into structured ModelAnalysis.

    Tries JSON parsing first, falls back to regex extraction.
    """
    cleaned = _strip_markdown_fences(raw)

    try:
        return _parse_json(cleaned)
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.debug("json_parse_failed, falling back to regex", raw_length=len(raw))

    return _parse_regex(raw)


def _strip_markdown_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_json(text: str) -> ModelAnalysis:
    data = json.loads(text)

    verdict = _to_verdict(data.get("verdict"))
    confidence = _clamp_float(data.get("confidence"))
    summary = data.get("summary", "")
    evidence = [_parse_evidence(e) for e in data.get("evidence", [])]

    return ModelAnalysis(
        raw_output=text,
        verdict=verdict,
        confidence=confidence,
        evidence=evidence,
        summary=summary,
    )


def _parse_regex(raw: str) -> ModelAnalysis:
    verdict_match = _VERDICT_PATTERN.search(raw)
    verdict = _to_verdict(verdict_match.group(1)) if verdict_match else None

    conf_match = _CONFIDENCE_PATTERN.search(raw)
    confidence = _clamp_float(float(conf_match.group(1))) if conf_match else None

    summary_match = _SUMMARY_PATTERN.search(raw)
    summary = summary_match.group(1) if summary_match else None

    return ModelAnalysis(
        raw_output=raw,
        verdict=verdict,
        confidence=confidence,
        evidence=[],
        summary=summary,
    )


def _parse_evidence(data: dict) -> Evidence:
    kind_str = data.get("kind", "OTHER").upper()
    try:
        kind = EvidenceKind(kind_str)
    except ValueError:
        kind = EvidenceKind.OTHER

    return Evidence(
        kind=kind,
        text=data.get("text", ""),
        confidence=_clamp_float(data.get("confidence", 0.0)),
        timestamp_start_s=data.get("timestamp_start_s"),
        timestamp_end_s=data.get("timestamp_end_s"),
    )


def _to_verdict(value: str | None) -> Verdict | None:
    if value is None:
        return None
    try:
        return Verdict(value.upper())
    except ValueError:
        return None


def _clamp_float(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))
