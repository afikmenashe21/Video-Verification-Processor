from __future__ import annotations

import psycopg
import structlog

from shared.errors import ValidationError

from submitter.apify_client import ApifyClient
from submitter.config import SubmitterConfig
from submitter.schemas import CreateJobRequest, JobResponse, TaskResponse

logger = structlog.get_logger()


class SubmitterHandler:
    def __init__(
        self,
        config: SubmitterConfig,
        conn: psycopg.Connection,
        apify_client: ApifyClient,
    ) -> None:
        self._config = config
        self._conn = conn
        self._apify = apify_client

    def create_job(self, request: CreateJobRequest) -> JobResponse:
        log = logger.bind(product_id=request.product_id, url_count=len(request.urls))
        log.info("creating_verification_job")

        # Verify product exists
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM products WHERE id = %(product_id)s::uuid",
                {"product_id": request.product_id},
            )
            if cur.fetchone() is None:
                raise ValidationError(f"Product not found: {request.product_id}")

        # Create job
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO verification_jobs (product_id, match_target, total_urls, status)
                VALUES (%(product_id)s::uuid, %(match_target)s, %(total_urls)s, 'IN_PROGRESS')
                RETURNING id, created_at
                """,
                {
                    "product_id": request.product_id,
                    "match_target": self._config.match_target,
                    "total_urls": len(request.urls),
                },
            )
            job_row = cur.fetchone()
            job_id = str(job_row["id"])
            created_at = str(job_row["created_at"])

            log = log.bind(job_id=job_id)

            # Create video tasks
            task_ids: list[tuple[str, str]] = []
            for url in request.urls:
                cur.execute(
                    """
                    INSERT INTO video_tasks (job_id, source_url, status)
                    VALUES (%(job_id)s::uuid, %(source_url)s, 'PENDING')
                    RETURNING id
                    """,
                    {"job_id": job_id, "source_url": url},
                )
                task_id = str(cur.fetchone()["id"])
                task_ids.append((task_id, url))

            self._conn.commit()

        log.info("job_and_tasks_created", task_count=len(task_ids))

        # Trigger Apify for each URL
        for task_id, url in task_ids:
            try:
                run_id = self._apify.start_actor_run(url, task_id)
                with self._conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE video_tasks
                        SET status = 'APIFY_SUBMITTED',
                            apify_run_id = %(run_id)s,
                            updated_at = now()
                        WHERE id = %(task_id)s::uuid
                        """,
                        {"task_id": task_id, "run_id": run_id},
                    )
                    self._conn.commit()
            except Exception as e:
                log.error("apify_submit_failed", task_id=task_id, url=url, error=str(e))
                with self._conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE video_tasks
                        SET status = 'FAILED',
                            error_message = %(error)s,
                            updated_at = now()
                        WHERE id = %(task_id)s::uuid
                        """,
                        {"task_id": task_id, "error": str(e)[:500]},
                    )
                    self._conn.commit()

        return JobResponse(
            job_id=job_id,
            product_id=request.product_id,
            status="IN_PROGRESS",
            match_target=self._config.match_target,
            match_count=0,
            total_urls=len(request.urls),
            completed_count=0,
            created_at=created_at,
        )

    def get_job(self, job_id: str) -> JobResponse | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, product_id, status, match_target, match_count,
                       total_urls, completed_count, created_at
                FROM verification_jobs
                WHERE id = %(job_id)s::uuid
                """,
                {"job_id": job_id},
            )
            row = cur.fetchone()

        if row is None:
            return None

        return JobResponse(
            job_id=str(row["id"]),
            product_id=str(row["product_id"]),
            status=row["status"],
            match_target=row["match_target"],
            match_count=row["match_count"],
            total_urls=row["total_urls"],
            completed_count=row["completed_count"],
            created_at=str(row["created_at"]),
        )

    def get_tasks(self, job_id: str) -> list[TaskResponse]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_url, status, score, confidence, verdict, error_message
                FROM video_tasks
                WHERE job_id = %(job_id)s::uuid
                ORDER BY created_at
                """,
                {"job_id": job_id},
            )
            rows = cur.fetchall()

        return [
            TaskResponse(
                task_id=str(r["id"]),
                source_url=r["source_url"],
                status=r["status"],
                score=r["score"],
                confidence=r["confidence"],
                verdict=r["verdict"],
                error_message=r["error_message"],
            )
            for r in rows
        ]
