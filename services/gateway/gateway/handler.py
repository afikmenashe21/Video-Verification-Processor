from __future__ import annotations

from typing import Any

import confluent_kafka
import httpx
import psycopg
import structlog

from shared.events import TOPIC_DOWNLOAD_READY, VideoDownloadReady

logger = structlog.get_logger()


class WebhookHandler:
    def __init__(
        self,
        conn: psycopg.Connection,
        producer: confluent_kafka.Producer,
        apify_api_token: str = "",
    ) -> None:
        self._conn = conn
        self._producer = producer
        self._apify_api_token = apify_api_token

    def handle_apify_webhook(self, task_id: str, payload: dict[str, Any]) -> bool:
        """Process an Apify webhook callback.

        Returns True if event was published, False if skipped.
        """
        log = logger.bind(task_id=task_id)
        log.info("apify_webhook_received", payload_keys=list(payload.keys()))

        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT vt.id, vt.status, vt.source_url, vt.job_id, vj.product_id
                FROM video_tasks vt
                JOIN verification_jobs vj ON vj.id = vt.job_id
                WHERE vt.id = %(task_id)s::uuid
                """,
                {"task_id": task_id},
            )
            row = cur.fetchone()

        if row is None:
            log.warning("task_not_found")
            return False

        if row["status"] in ("SKIPPED", "COMPLETED", "FAILED"):
            log.info("task_already_terminal", status=row["status"])
            return False

        # Extract download URL: first try direct payload, then fetch from Apify dataset
        download_url = _extract_download_url(payload)
        if not download_url:
            download_url = self._fetch_download_url_from_dataset(payload, log)
        if not download_url:
            log.warning("no_download_url_found")
            return False

        log = log.bind(job_id=str(row["job_id"]), download_url=download_url)

        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE video_tasks
                SET status = 'DOWNLOAD_READY',
                    download_url = %(download_url)s,
                    apify_run_id = %(run_id)s,
                    updated_at = now()
                WHERE id = %(task_id)s::uuid
                  AND status NOT IN ('COMPLETED', 'SKIPPED', 'FAILED')
                """,
                {
                    "task_id": task_id,
                    "download_url": download_url,
                    "run_id": payload.get("resource", {}).get("id"),
                },
            )
            self._conn.commit()

        event = VideoDownloadReady(
            task_id=task_id,
            job_id=str(row["job_id"]),
            download_url=download_url,
            source_url=row["source_url"],
            product_id=str(row["product_id"]),
        )

        self._producer.produce(
            topic=TOPIC_DOWNLOAD_READY,
            key=task_id.encode("utf-8"),
            value=event.model_dump_json().encode(),
        )
        self._producer.flush()

        log.info("download_ready_published")
        return True

    def _fetch_download_url_from_dataset(
        self, payload: dict[str, Any], log: structlog.stdlib.BoundLogger
    ) -> str | None:
        """Fetch dataset items from Apify API to find the download URL."""
        resource = payload.get("resource", {})
        dataset_id = resource.get("defaultDatasetId")
        if not dataset_id:
            log.debug("no_dataset_id_in_resource")
            return None

        if not self._apify_api_token:
            log.warning("no_apify_api_token_configured")
            return None

        url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={self._apify_api_token}"
        log.info("fetching_dataset_items", dataset_id=dataset_id)

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url)
                resp.raise_for_status()
                items = resp.json()

            if not items:
                log.warning("dataset_empty")
                return None

            for item in items:
                for key in ("downloadUrl", "videoUrl", "url", "videoDownloadUrl"):
                    if key in item and item[key]:
                        log.info("download_url_found_in_dataset", key=key)
                        return item[key]

            log.warning("no_download_url_in_dataset_items", first_item_keys=list(items[0].keys()))
        except Exception as e:
            log.error("dataset_fetch_failed", error=str(e))

        return None


def _extract_download_url(payload: dict[str, Any]) -> str | None:
    """Extract the video download URL directly from the webhook payload."""
    # Direct field on payload
    if "downloadUrl" in payload:
        return payload["downloadUrl"]

    # Nested in resource.output
    resource = payload.get("resource", {})
    output = resource.get("output", {})
    if isinstance(output, dict) and "downloadUrl" in output:
        return output["downloadUrl"]

    # Check dataset items if included in payload
    items = payload.get("items", [])
    if items and isinstance(items, list):
        first = items[0]
        for key in ("downloadUrl", "videoUrl", "url"):
            if key in first:
                return first[key]

    # Check eventData
    event_data = payload.get("eventData", {})
    if isinstance(event_data, dict) and "downloadUrl" in event_data:
        return event_data["downloadUrl"]

    return None
