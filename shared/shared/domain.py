from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


class EvidenceKind(str, Enum):
    QUERY_MATCH = "QUERY_MATCH"
    IMAGE_MATCH = "IMAGE_MATCH"
    OBJECT_MATCH = "OBJECT_MATCH"
    OTHER = "OTHER"


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    text: str
    confidence: float
    timestamp_start_s: float | None = None
    timestamp_end_s: float | None = None


@dataclass(frozen=True)
class ModelAnalysis:
    raw_output: str
    verdict: Verdict | None = None
    confidence: float | None = None
    evidence: list[Evidence] = field(default_factory=list)
    summary: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    score_0_100: int
    confidence_0_1: float
    verdict: Verdict
    summary: str
    evidence: list[Evidence]
    raw_model_output: str


@dataclass
class VideoVerificationJob:
    job_id: str
    video_path: str
    images_path: list[str]
    query: str
    model: str
    metadata: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def generate_idempotency_key(video_path: str, images_path: list[str], query: str) -> str:
        content = f"{video_path}|{'|'.join(sorted(images_path))}|{query}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class VideoMetadata:
    duration_s: float
    fps: float
    width: int
    height: int
    codec: str


@dataclass(frozen=True)
class RunnerHealth:
    name: str
    healthy: bool
    detail: str = ""
