from __future__ import annotations

import json
import os
import tempfile

import confluent_kafka
import httpx
import psycopg
import structlog
from minio import Minio

from shared.errors import DownloadError, ValidationError
from shared.events import (
    TOPIC_REQUESTED,
    VideoDownloadReady,
    VideoVerificationRequested,
)

from downloader.config import DownloaderConfig

logger = structlog.get_logger()


class DownloadHandler:
    def __init__(
        self,
        config: DownloaderConfig,
        conn: psycopg.Connection,
        minio_client: Minio,
        producer: confluent_kafka.Producer,
    ) -> None:
        self._config = config
        self._conn = conn
        self._minio = minio_client
        self._producer = producer

    def handle(self, raw_value: bytes) -> None:
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}") from e

        try:
            event = VideoDownloadReady.model_validate(payload)
        except Exception as e:
            raise ValidationError(f"Schema validation failed: {e}") from e

        log = logger.bind(task_id=event.task_id, job_id=event.job_id)
        log.info("processing_download_ready")

        # Check if task is still active
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM video_tasks WHERE id = %(task_id)s::uuid",
                {"task_id": event.task_id},
            )
            row = cur.fetchone()

        if row is None:
            log.warning("task_not_found")
            return

        if row["status"] in ("SKIPPED", "COMPLETED", "FAILED"):
            log.info("task_already_terminal", status=row["status"])
            return

        # Update status to DOWNLOADING
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE video_tasks
                SET status = 'DOWNLOADING', updated_at = now()
                WHERE id = %(task_id)s::uuid
                  AND status NOT IN ('COMPLETED', 'SKIPPED', 'FAILED')
                """,
                {"task_id": event.task_id},
            )
            self._conn.commit()

        # Download video
        try:
            local_path = self._download_video(event, log)
        except Exception as e:
            self._mark_failed(event.task_id, str(e))
            raise DownloadError(f"Failed to download video: {e}") from e

        # Upload to MinIO
        minio_key = f"{event.job_id}/{event.task_id}.mp4"
        try:
            self._upload_to_minio(local_path, minio_key, log)
        except Exception as e:
            self._mark_failed(event.task_id, str(e))
            raise DownloadError(f"Failed to upload to MinIO: {e}") from e

        # Update task status
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE video_tasks
                SET status = 'UPLOADED',
                    minio_bucket = %(bucket)s,
                    minio_key = %(key)s,
                    updated_at = now()
                WHERE id = %(task_id)s::uuid
                  AND status NOT IN ('COMPLETED', 'SKIPPED', 'FAILED')
                """,
                {
                    "task_id": event.task_id,
                    "bucket": self._config.minio_bucket,
                    "key": minio_key,
                },
            )
            self._conn.commit()

        # Load product details for the verification request
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.reference_images, p.query_text, p.default_model
                FROM products p
                JOIN verification_jobs vj ON vj.product_id = p.id
                WHERE vj.id = %(job_id)s::uuid
                """,
                {"job_id": event.job_id},
            )
            product = cur.fetchone()

        if product is None:
            self._mark_failed(event.task_id, "Product not found for job")
            raise DownloadError("Product not found for job")

        # Publish to existing pipeline
        # job_id in the pipeline = video_task_id (1:1 mapping)
        verification_event = VideoVerificationRequested(
            job_id=event.task_id,
            video_path=local_path,
            images_path=product["reference_images"] or [],
            query=product["query_text"],
            model=product["default_model"],
            video_task_id=event.task_id,
            product_id=event.product_id,
        )

        self._producer.produce(
            topic=TOPIC_REQUESTED,
            key=event.task_id.encode("utf-8"),
            value=verification_event.model_dump_json().encode(),
        )
        self._producer.flush()

        # Update task to PROCESSING
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE video_tasks
                SET status = 'PROCESSING', updated_at = now()
                WHERE id = %(task_id)s::uuid
                  AND status NOT IN ('COMPLETED', 'SKIPPED', 'FAILED')
                """,
                {"task_id": event.task_id},
            )
            self._conn.commit()

        log.info("verification_requested_published")

    def _download_video(
        self, event: VideoDownloadReady, log: structlog.stdlib.BoundLogger
    ) -> str:
        job_dir = os.path.join(self._config.video_base_dir, event.job_id)
        os.makedirs(job_dir, exist_ok=True)
        local_path = os.path.join(job_dir, f"{event.task_id}.mp4")

        log.info("downloading_video", url=event.download_url, dest=local_path)

        with httpx.Client(timeout=self._config.download_timeout_s, follow_redirects=True) as client:
            with client.stream("GET", event.download_url) as response:
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)

        file_size = os.path.getsize(local_path)
        log.info("video_downloaded", size_bytes=file_size)
        return local_path

    def _upload_to_minio(
        self, local_path: str, key: str, log: structlog.stdlib.BoundLogger
    ) -> None:
        log.info("uploading_to_minio", bucket=self._config.minio_bucket, key=key)
        self._minio.fput_object(
            self._config.minio_bucket,
            key,
            local_path,
            content_type="video/mp4",
        )
        log.info("minio_upload_complete")

    def _mark_failed(self, task_id: str, error_message: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE video_tasks
                SET status = 'FAILED',
                    error_message = %(error)s,
                    updated_at = now()
                WHERE id = %(task_id)s::uuid
                  AND status NOT IN ('COMPLETED', 'SKIPPED', 'FAILED')
                """,
                {"task_id": task_id, "error": error_message[:500]},
            )
            self._conn.commit()
