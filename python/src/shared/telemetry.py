"""Telemetry module: Sentry spans + PostgreSQL processing_jobs tracking.

Provides decorators and context managers for:
- Timing each processing step with Sentry performance spans
- Writing granular telemetry rows to the `processing_jobs` table
- Structured logging with UTC timestamps
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
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

# Async error writer: a single background thread drains a queue so that
# callers on hot paths (page workers) never block on DB I/O. Used by
# log_processing_error().
_ERROR_QUEUE_MAX = 5000
_ERROR_CONTENT_MAX_CHARS = 20_000  # Truncate very long page text snapshots
_ERROR_MESSAGE_MAX_CHARS = 10_000
_ERROR_STACK_MAX_CHARS = 20_000
_error_queue: queue.Queue[dict] | None = None
_error_writer_thread: threading.Thread | None = None
_error_writer_lock = threading.Lock()


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


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n…[truncated {len(value) - limit} chars]"


def _ensure_error_writer() -> queue.Queue[dict]:
    """Start the background writer thread on first use."""
    global _error_queue, _error_writer_thread
    if _error_queue is not None and _error_writer_thread and _error_writer_thread.is_alive():
        return _error_queue

    with _error_writer_lock:
        if _error_queue is None:
            _error_queue = queue.Queue(maxsize=_ERROR_QUEUE_MAX)
        if not _error_writer_thread or not _error_writer_thread.is_alive():
            _error_writer_thread = threading.Thread(
                target=_error_writer_loop,
                name="processing-errors-writer",
                daemon=True,
            )
            _error_writer_thread.start()
    return _error_queue


def _error_writer_loop() -> None:
    """Drain the error queue and persist rows. Survives individual failures."""
    assert _error_queue is not None
    while True:
        row = _error_queue.get()
        try:
            _insert_processing_error(row)
        except Exception as e:
            logger.warning(f"[TELEMETRY] Failed to write processing_jobs_error: {e}")
        finally:
            _error_queue.task_done()


def _insert_processing_error(row: dict) -> None:
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO processing_jobs_errors
                   (uid, processing_job_id, conversation_id, file_name,
                    page_number, step, content_type, content, image_path,
                    error_type, error_message, stack_trace,
                    worker_id, retry_count, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s)""",
                (
                    row["uid"],
                    row.get("processing_job_id"),
                    row["conversation_id"],
                    row["file_name"],
                    row.get("page_number"),
                    row.get("step"),
                    row.get("content_type"),
                    row.get("content"),
                    row.get("image_path"),
                    row.get("error_type"),
                    row["error_message"],
                    row.get("stack_trace"),
                    row.get("worker_id"),
                    row.get("retry_count", 0),
                    row["created_at"],
                ),
            )
            conn.commit()
    finally:
        pool.putconn(conn)


def log_processing_error(
    conversation_id: str,
    file_name: str,
    error: BaseException,
    *,
    step: str | None = None,
    page_number: int | None = None,
    content: str | None = None,
    content_type: str | None = None,
    image_path: str | None = None,
    worker_id: str | None = None,
    retry_count: int = 0,
    processing_job_id: str | None = None,
) -> str:
    """Record a per-page/per-step error asynchronously (fire-and-forget).

    The DB write is dispatched to a background thread so callers on hot
    parsing paths never block. Returns the generated uid for correlation.

    A snapshot of the text/image that caused the error is captured in
    `content` / `image_path` so we can later inspect the exact input that
    tripped the library/API. The full traceback is stored in stack_trace.
    """
    ts = _utc_now()
    uid = str(uuid.uuid4())
    error_message = f"[{ts.isoformat()}] {type(error).__name__}: {error}"
    stack = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )

    row = {
        "uid": uid,
        "processing_job_id": processing_job_id,
        "conversation_id": conversation_id,
        "file_name": file_name,
        "page_number": page_number,
        "step": step,
        "content_type": content_type,
        "content": _truncate(content, _ERROR_CONTENT_MAX_CHARS),
        "image_path": image_path,
        "error_type": type(error).__name__,
        "error_message": _truncate(error_message, _ERROR_MESSAGE_MAX_CHARS),
        "stack_trace": _truncate(stack, _ERROR_STACK_MAX_CHARS),
        "worker_id": worker_id,
        "retry_count": retry_count,
        "created_at": ts,
    }

    try:
        q = _ensure_error_writer()
        q.put_nowait(row)
    except queue.Full:
        logger.warning("[TELEMETRY] processing_jobs_errors queue full, dropping row")
    except Exception as e:
        logger.warning(f"[TELEMETRY] Failed to enqueue processing error: {e}")

    return uid


def flush_processing_errors(timeout: float = 10.0) -> None:
    """Block until the error queue is drained. Call before process exit."""
    if _error_queue is None:
        return
    deadline = time.monotonic() + timeout
    while not _error_queue.empty() and time.monotonic() < deadline:
        time.sleep(0.05)
