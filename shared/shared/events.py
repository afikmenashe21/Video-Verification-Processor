from __future__ import annotations

from pydantic import BaseModel, Field


# Topic constants
TOPIC_REQUESTED = "video.verification.requested.v1"
TOPIC_FRAMES_EXTRACTED = "video.frames.extracted.v1"
TOPIC_ANALYSIS_COMPLETED = "video.analysis.completed.v1"
TOPIC_VERIFICATION_COMPLETED = "video.verification.completed.v1"
TOPIC_DLQ = "video.verification.dlq.v1"

EVENT_VERSION = "1"


# --- Input event ---

class VideoVerificationRequested(BaseModel):
    job_id: str | None = None
    video_path: str
    images_path: list[str] = Field(default_factory=list)
    query: str
    model: str = "gemini"
    metadata: dict[str, str] = Field(default_factory=dict)


# --- Preprocessor → Analyzer ---

class VideoMetadataEvent(BaseModel):
    duration_s: float
    fps: float
    width: int
    height: int
    codec: str


class FramesExtracted(BaseModel):
    job_id: str
    frames_dir: str
    frame_count: int
    frame_timestamps_s: list[float]
    images_path: list[str]
    query: str
    model: str
    video_metadata: VideoMetadataEvent


# --- Analyzer → Scorer ---

class EvidenceEvent(BaseModel):
    kind: str
    text: str
    confidence: float
    timestamp_start_s: float | None = None
    timestamp_end_s: float | None = None


class AnalysisEvent(BaseModel):
    raw_output: str
    verdict: str
    confidence: float
    evidence: list[EvidenceEvent] = Field(default_factory=list)
    summary: str


class AnalysisCompleted(BaseModel):
    job_id: str
    model: str
    query: str
    images_path: list[str]
    video_path: str = ""
    frames_sampled: int
    analysis: AnalysisEvent
    latency_ms: float


# --- Scorer output ---

class VerificationCompleted(BaseModel):
    job_id: str
    score: int
    confidence: float
    verdict: str
    summary: str
    output_txt_path: str
    output_json_path: str
