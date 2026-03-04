from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.db import connect
from shared.errors import ValidationError

from submitter.apify_client import ApifyClient
from submitter.config import SubmitterConfig
from submitter.handler import SubmitterHandler
from submitter.schemas import CreateJobRequest, JobResponse, TaskResponse


def _setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)


logger = structlog.get_logger()

_handler: SubmitterHandler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handler
    _setup_logging()
    config = SubmitterConfig()

    conn = connect(config.database_url)
    apify_client = ApifyClient(
        api_token=config.apify_api_token,
        actor_id=config.apify_actor_id,
        webhook_base_url=config.webhook_base_url,
    )
    _handler = SubmitterHandler(config, conn, apify_client)

    logger.info("submitter_started", port=config.http_port)
    yield

    conn.close()
    logger.info("submitter_stopped")


app = FastAPI(title="Video Verification Submitter", lifespan=lifespan)


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
async def create_job(request: CreateJobRequest) -> JobResponse:
    try:
        return _handler.create_job(request)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    result = _handler.get_job(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@app.get("/api/v1/jobs/{job_id}/tasks", response_model=list[TaskResponse])
async def get_tasks(job_id: str) -> list[TaskResponse]:
    return _handler.get_tasks(job_id)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def main() -> None:
    _setup_logging()
    config = SubmitterConfig()
    uvicorn.run(
        "submitter.main:app",
        host="0.0.0.0",
        port=config.http_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
