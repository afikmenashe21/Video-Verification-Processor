from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

import confluent_kafka
import structlog
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from shared.db import connect

from gateway.config import GatewayConfig
from gateway.handler import WebhookHandler


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

_config: GatewayConfig | None = None
_handler: WebhookHandler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _handler
    _setup_logging()
    _config = GatewayConfig()

    conn = connect(_config.database_url)
    producer = confluent_kafka.Producer({"bootstrap.servers": _config.kafka_bootstrap_servers})
    _handler = WebhookHandler(conn, producer, apify_api_token=_config.apify_api_token)

    logger.info("gateway_started", port=_config.http_port)
    yield

    producer.flush(10.0)
    conn.close()
    logger.info("gateway_stopped")


app = FastAPI(title="Video Verification Gateway", lifespan=lifespan)


@app.post("/api/v1/webhooks/apify")
async def apify_webhook(
    request: Request,
    task_id: str = Query(..., description="Video task ID"),
) -> JSONResponse:
    payload: dict[str, Any] = await request.json()
    published = _handler.handle_apify_webhook(task_id, payload)

    if published:
        return JSONResponse({"status": "accepted"}, status_code=200)
    return JSONResponse({"status": "skipped"}, status_code=200)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def main() -> None:
    _setup_logging()
    config = GatewayConfig()
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=config.http_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
