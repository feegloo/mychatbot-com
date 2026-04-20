"""Telemetry module: Sentry spans + PostgreSQL processing_jobs tracking.

Provides decorators and context managers for:
- Timing each processing step with Sentry performance spans
- Writing granular telemetry rows to the `processing_jobs` table
- Structured logging with UTC timestamps
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg2
import psycopg2.pool
import sentry_sdk

from .config import get_settings

logger = logging.getLogger(__name__)

# Module-level connection pool (lazy init)
_db_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_db_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _db_pool
    if _db_pool is not None:
        return _db_pool

    settings = get_settings()
    db_url = settings.database_url
    if not db_url:
        raise RuntimeError("DATABASE_URL not set — cannot write telemetry")

    _db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=db_url,
        connect_timeout=5,
    )
    return _db_pool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def log_processing_event(
    conversation_id: str,
    file_name: str,
    step: str,
    *,
    page_number: int | None = None,
    total_pages: int | None = None,
    status: str = "running",
    detail: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    worker_id: str | None = None,
    retry_count: int = 0,
    job_id: str | None = None,
) -> str:
    """Insert or update a processing_jobs row and return the job ID.

    If job_id is provided, updates the existing row.
    Otherwise, inserts a new row and returns the generated UUID.
    """
    ts = _utc_now()
    logger.info(
        f"[TELEMETRY] {ts.isoformat()} | {status.upper():9s} | "
        f"{step} | {file_name}"
        f"{f' p.{page_number}' if page_number else ''}"
        f"{f' | {detail}' if detail else ''}"
        f"{f' | {duration_ms}ms' if duration_ms else ''}"
        f"{f' | ERROR: {error_message}' if error_message else ''}"
    )

    try:
        pool = _get_db_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                if job_id:
                    cur.execute(
                        """UPDATE processing_jobs
                           SET status = %s, step = %s, detail = %s,
                               error_message = %s, duration_ms = %s,
                               retry_count = %s,
                               completed_at = CASE
                                   WHEN %s IN ('completed', 'failed')
                                   THEN %s ELSE completed_at END,
                               worker_id = COALESCE(%s, worker_id)
                           WHERE id = %s""",
                        (
                            status,
                            step,
                            detail,
                            error_message,
                            duration_ms,
                            retry_count,
                            status,
                            ts,
                            worker_id,
                            job_id,
                        ),
                    )
                    conn.commit()
                    return job_id
                else:
                    new_id = str(uuid.uuid4())
                    cur.execute(
                        """INSERT INTO processing_jobs
                           (id, conversation_id, file_name, page_number, total_pages,
                            status, step, detail, error_message, duration_ms,
                            retry_count, worker_id, started_at, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            new_id,
                            conversation_id,
                            file_name,
                            page_number,
                            total_pages,
                            status,
                            step,
                            detail,
                            error_message,
                            duration_ms,
                            retry_count,
                            worker_id,
                            ts if status == "running" else None,
                            ts,
                        ),
                    )
                    conn.commit()
                    return new_id
        finally:
            pool.putconn(conn)
    except Exception as e:
        logger.warning(f"[TELEMETRY] DB write failed (non-fatal): {e}")
        return job_id or str(uuid.uuid4())


@contextmanager
def trace_step(
    conversation_id: str,
    file_name: str,
    step: str,
    *,
    page_number: int | None = None,
    total_pages: int | None = None,
    detail: str | None = None,
    worker_id: str | None = None,
    parent_job_id: str | None = None,
) -> Generator[dict, None, None]:
    """Context manager that:
    1. Starts a Sentry performance span
    2. Records 'running' in processing_jobs
    3. On success → 'completed' with duration_ms
    4. On error → 'failed' with error_message

    Yields a dict where callers can set extra detail:
        with trace_step(...) as ctx:
            ctx["detail"] = "extracted 1200 tokens"
    """
    ctx: dict = {"detail": detail, "tokens": None}

    # Start Sentry span
    span = sentry_sdk.start_span(
        op=f"processing.{step}",
        name=f"{step}: {file_name}" + (f" p.{page_number}" if page_number else ""),
    )
    span.set_data("conversation_id", conversation_id)
    span.set_data("file_name", file_name)
    if page_number is not None:
        span.set_data("page_number", page_number)

    job_id = log_processing_event(
        conversation_id,
        file_name,
        step,
        page_number=page_number,
        total_pages=total_pages,
        status="running",
        detail=detail,
        worker_id=worker_id,
    )

    start = time.monotonic()
    try:
        yield ctx
        elapsed_ms = int((time.monotonic() - start) * 1000)

        final_detail = ctx.get("detail") or detail
        if ctx.get("tokens"):
            final_detail = f"{final_detail or ''} | {ctx['tokens']} tokens".strip(" |")

        span.set_data("duration_ms", elapsed_ms)
        span.set_status("ok")
        span.finish()

        log_processing_event(
            conversation_id,
            file_name,
            step,
            page_number=page_number,
            total_pages=total_pages,
            status="completed",
            detail=final_detail,
            duration_ms=elapsed_ms,
            worker_id=worker_id,
            job_id=job_id,
        )

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        span.set_status("internal_error")
        span.set_data("error", str(exc))
        span.finish()

        sentry_sdk.capture_exception(exc)

        log_processing_event(
            conversation_id,
            file_name,
            step,
            page_number=page_number,
            total_pages=total_pages,
            status="failed",
            error_message=str(exc)[:500],
            duration_ms=elapsed_ms,
            worker_id=worker_id,
            job_id=job_id,
        )
        raise


def close_db_pool():
    """Shutdown the connection pool (call on app shutdown)."""
    global _db_pool
    if _db_pool:
        _db_pool.closeall()
        _db_pool = None
