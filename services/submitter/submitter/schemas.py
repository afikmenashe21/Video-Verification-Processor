from __future__ import annotations

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    product_id: str
    urls: list[str] = Field(..., min_length=1)


class JobResponse(BaseModel):
    job_id: str
    product_id: str
    status: str
    match_target: int
    match_count: int
    total_urls: int
    completed_count: int
    created_at: str


class TaskResponse(BaseModel):
    task_id: str
    source_url: str
    status: str
    score: int | None = None
    confidence: float | None = None
    verdict: str | None = None
    error_message: str | None = None
