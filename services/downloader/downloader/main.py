from __future__ import annotations

import json
import logging
import signal
import sys

import confluent_kafka
import structlog
from minio import Minio

from shared.db import connect
from shared.events import TOPIC_DLQ
from shared.errors import ServiceError, ValidationError

from downloader.config import DownloaderConfig
from downloader.handler import DownloadHandler


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
_running = True


def _shutdown_handler(signum: int, frame: object) -> None:
    global _running
    logger.info("shutdown_signal_received", signal=signum)
    _running = False


def main() -> None:
    _setup_logging()
    config = DownloaderConfig()

    logger.info(
        "starting_downloader",
        topic=config.kafka_topic,
        group_id=config.kafka_group_id,
    )

    conn = connect(config.database_url)

    minio_client = Minio(
        config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        secure=config.minio_secure,
    )

    consumer = confluent_kafka.Consumer({
        "bootstrap.servers": config.kafka_bootstrap_servers,
        "group.id": config.kafka_group_id,
        "auto.offset.reset": config.kafka_auto_offset_reset,
        "enable.auto.commit": False,
    })
    consumer.subscribe([config.kafka_topic])

    producer = confluent_kafka.Producer({"bootstrap.servers": config.kafka_bootstrap_servers})
    handler = DownloadHandler(config, conn, minio_client, producer)

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    retry_counts: dict[str, int] = {}

    logger.info("consumer_loop_started")
    try:
        while _running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == confluent_kafka.KafkaError._PARTITION_EOF:
                    continue
                logger.error("kafka_consumer_error", error=str(msg.error()))
                continue

            msg_key = f"{msg.topic()}:{msg.partition()}:{msg.offset()}"
            log = logger.bind(topic=msg.topic(), partition=msg.partition(), offset=msg.offset())

            try:
                handler.handle(msg.value())
                consumer.commit(asynchronous=False)
                retry_counts.pop(msg_key, None)
                log.info("message_processed")

            except ValidationError as e:
                log.error("validation_error", error=str(e))
                _send_to_dlq(producer, msg.value(), str(e))
                consumer.commit(asynchronous=False)

            except ServiceError as e:
                count = retry_counts.get(msg_key, 0) + 1
                retry_counts[msg_key] = count
                log.warning("processing_error", error=str(e), retry=count)
                if count >= config.dlq_max_retries:
                    log.error("max_retries_exceeded", retries=count)
                    _send_to_dlq(producer, msg.value(), str(e))
                    consumer.commit(asynchronous=False)
                    retry_counts.pop(msg_key, None)

            except Exception as e:
                count = retry_counts.get(msg_key, 0) + 1
                retry_counts[msg_key] = count
                log.error("unexpected_error", error=str(e), retry=count, exc_info=True)
                if count >= config.dlq_max_retries:
                    log.error("max_retries_exceeded", retries=count)
                    _send_to_dlq(producer, msg.value(), str(e))
                    consumer.commit(asynchronous=False)
                    retry_counts.pop(msg_key, None)

    finally:
        logger.info("shutting_down")
        consumer.close()
        producer.flush(10.0)
        conn.close()


def _send_to_dlq(producer: confluent_kafka.Producer, original_value: bytes, error: str) -> None:
    dlq_payload = json.dumps({"original": json.loads(original_value), "error": error}).encode()
    producer.produce(topic=TOPIC_DLQ, key=b"dlq", value=dlq_payload)
    producer.flush()


if __name__ == "__main__":
    main()
