from __future__ import annotations

import json

import psycopg
import structlog

from shared.errors import ValidationError
from shared.events import VerificationCompleted

logger = structlog.get_logger()


class CompletionHandler:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def handle(self, raw_value: bytes) -> None:
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}") from e

        try:
            event = VerificationCompleted.model_validate(payload)
        except Exception as e:
            raise ValidationError(f"Schema validation failed: {e}") from e

        task_id = event.job_id
        log = logger.bind(task_id=task_id, verdict=event.verdict, score=event.score)
        log.info("processing_completion")

        with self._conn.cursor() as cur:
            # Idempotent update: only update if not already in terminal state
            cur.execute(
                """
                UPDATE video_tasks
                SET status = 'COMPLETED',
                    score = %(score)s,
                    confidence = %(confidence)s,
                    verdict = %(verdict)s::verdict_type,
                    updated_at = now()
                WHERE id = %(task_id)s::uuid
                  AND status NOT IN ('COMPLETED', 'SKIPPED', 'FAILED')
                RETURNING job_id
                """,
                {
                    "task_id": task_id,
                    "score": event.score,
                    "confidence": event.confidence,
                    "verdict": event.verdict,
                },
            )
            row = cur.fetchone()
            if row is None:
                log.info("task_already_terminal_skipping")
                self._conn.commit()
                return

            job_id = str(row["job_id"])
            log = log.bind(job_id=job_id)

            # Update completed_count on job
            cur.execute(
                """
                UPDATE verification_jobs
                SET completed_count = completed_count + 1,
                    updated_at = now()
                WHERE id = %(job_id)s::uuid
                """,
                {"job_id": job_id},
            )

            # If PASS, increment match_count
            if event.verdict == "PASS":
                cur.execute(
                    """
                    UPDATE verification_jobs
                    SET match_count = match_count + 1,
                        updated_at = now()
                    WHERE id = %(job_id)s::uuid
                    RETURNING match_count, match_target
                    """,
                    {"job_id": job_id},
                )
                job_row = cur.fetchone()
                match_count = job_row["match_count"]
                match_target = job_row["match_target"]
                log.info("match_incremented", match_count=match_count, match_target=match_target)

                if match_count >= match_target:
                    self._mark_job_completed(cur, job_id, log)
                    self._conn.commit()
                    return

            # Check if all tasks are in terminal state
            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED')) AS pending,
                    count(*) AS total
                FROM video_tasks
                WHERE job_id = %(job_id)s::uuid
                """,
                {"job_id": job_id},
            )
            counts = cur.fetchone()
            if counts["pending"] == 0:
                log.info("all_tasks_terminal", total=counts["total"])
                cur.execute(
                    """
                    UPDATE verification_jobs
                    SET status = 'COMPLETED', updated_at = now()
                    WHERE id = %(job_id)s::uuid AND status != 'COMPLETED'
                    """,
                    {"job_id": job_id},
                )

            self._conn.commit()
            log.info("completion_handled")

    def _mark_job_completed(
        self, cur: psycopg.Cursor, job_id: str, log: structlog.stdlib.BoundLogger
    ) -> None:
        # Skip remaining non-terminal tasks
        cur.execute(
            """
            UPDATE video_tasks
            SET status = 'SKIPPED', updated_at = now()
            WHERE job_id = %(job_id)s::uuid
              AND status NOT IN ('COMPLETED', 'FAILED', 'SKIPPED')
            """,
            {"job_id": job_id},
        )
        skipped = cur.rowcount
        log.info("remaining_tasks_skipped", skipped_count=skipped)

        cur.execute(
            """
            UPDATE verification_jobs
            SET status = 'COMPLETED', updated_at = now()
            WHERE id = %(job_id)s::uuid
            """,
            {"job_id": job_id},
        )
        log.info("job_completed_early_termination")
