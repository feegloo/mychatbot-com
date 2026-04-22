"""Postgres-backed job queue for the indexing worker.

Design goals:
  * Concurrent workers on multiple Cloud Run instances must never claim the
    same job. Enforced via ``SELECT ... FOR UPDATE SKIP LOCKED`` — the
    canonical Postgres pattern, used by pg-boss, River, Graphile Worker, etc.
    With SKIP LOCKED, each concurrent ``claim_job()`` call sees a different
    row and no caller blocks on another's lock; anyone who loses the race
    simply gets ``None`` and goes back to sleep until the next NOTIFY.
  * Crashed workers shouldn't strand jobs forever. Every claim includes
    ``heartbeat_at``; claim reconsiders rows whose heartbeat is older than
    ``STALE_LEASE_SECONDS``. The retry counter is incremented atomically in
    the same UPDATE so runaway retries can be capped via ``max_attempts``.
  * No ``SELECT … FROM indexing_jobs WHERE … ; UPDATE …`` two-step — that
    pattern races across instances. Everything is one UPDATE with a CTE.

The module is thread-safe: callers get fresh connections from the telemetry
pool for each operation.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from .telemetry import _get_db_pool

logger = logging.getLogger(__name__)


# A job is considered stuck (and up for re-claim) if its heartbeat is older
# than this. Should be several times the worker's heartbeat interval so a
# normal OCR stall doesn't trigger re-claim. Matches the upper bound of a
# single OpenAI Vision OCR call + generous jitter.
STALE_LEASE_SECONDS = 180

# Worker identity for claimed_by. Combines Cloud Run revision (so we can
# grep "which rollout processed this book") with hostname (so we can tell
# instances in the same revision apart). Local dev falls back gracefully.
def _worker_id() -> str:
    revision = os.environ.get("K_REVISION") or "local"
    host = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown"
    return f"{revision}@{host}"


WORKER_ID = _worker_id()


@dataclass
class IndexingJob:
    """A claimed job handed to the worker for processing."""

    id: int
    conversation_id: str
    collection_name: str
    file_paths: list[str]
    storage_namespace: str | None
    attempts: int
    max_attempts: int
    metadata: dict[str, Any]


def enqueue_job(
    conversation_id: str,
    collection_name: str,
    file_paths: list[str],
    *,
    storage_namespace: str | None = None,
    max_attempts: int = 3,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Insert a new job. The AFTER INSERT trigger fires NOTIFY so any idle
    worker listening on ``indexing_jobs_new`` wakes immediately.

    Returns the job id so callers (e.g. upload handlers) can surface it.
    """
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO indexing_jobs (
                       conversation_id, collection_name, file_paths,
                       storage_namespace, max_attempts, metadata
                   ) VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    conversation_id,
                    collection_name,
                    Json(file_paths),
                    storage_namespace,
                    max_attempts,
                    Json(metadata or {}),
                ),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row[0])
    finally:
        pool.putconn(conn)


def claim_job() -> IndexingJob | None:
    """Atomically claim the oldest available job for this worker.

    Returns the claimed job or ``None`` if the queue has nothing pickable.

    Race-safety: ``FOR UPDATE SKIP LOCKED`` inside the CTE guarantees that
    if N workers call ``claim_job()`` simultaneously, they each get a
    distinct row (or ``None``). No worker ever blocks on another's lock,
    so claim latency stays bounded even under contention.

    Re-claim safety: a job whose heartbeat is older than
    ``STALE_LEASE_SECONDS`` is considered abandoned (the previous worker
    crashed / was evicted) and becomes claimable again. ``attempts`` is
    incremented so a poison job that crashes every worker will eventually
    exceed ``max_attempts`` and be marked error via ``fail_job``.
    """
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """WITH next_job AS (
                     SELECT id
                       FROM indexing_jobs
                      WHERE attempts < max_attempts
                        AND (
                             status = 'queued'
                          OR (status IN ('claimed', 'running')
                              AND heartbeat_at < NOW() - make_interval(secs => %s))
                        )
                      ORDER BY created_at ASC
                      FOR UPDATE SKIP LOCKED
                      LIMIT 1
                   )
                   UPDATE indexing_jobs j
                      SET status       = 'claimed',
                          claimed_by   = %s,
                          claimed_at   = NOW(),
                          heartbeat_at = NOW(),
                          attempts     = j.attempts + 1
                     FROM next_job
                    WHERE j.id = next_job.id
                RETURNING j.id, j.conversation_id, j.collection_name,
                          j.file_paths, j.storage_namespace,
                          j.attempts, j.max_attempts, j.metadata""",
                (STALE_LEASE_SECONDS, WORKER_ID),
            )
            row = cur.fetchone()
            if row is None:
                return None
            # psycopg2 returns JSONB as parsed Python objects when using
            # RealDictCursor + default adapters, but older versions hand
            # back strings. Normalize.
            file_paths = row["file_paths"]
            if isinstance(file_paths, str):
                file_paths = json.loads(file_paths)
            metadata = row["metadata"] or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            return IndexingJob(
                id=int(row["id"]),
                conversation_id=row["conversation_id"],
                collection_name=row["collection_name"],
                file_paths=list(file_paths or []),
                storage_namespace=row.get("storage_namespace"),
                attempts=int(row["attempts"]),
                max_attempts=int(row["max_attempts"]),
                metadata=dict(metadata),
            )
    finally:
        pool.putconn(conn)


def mark_running(job_id: int) -> None:
    """Transition a freshly-claimed job from 'claimed' → 'running'.

    Split from the claim so a worker that dies between claim and first
    heartbeat can be distinguished from one that died mid-processing.
    Both states are treated identically by the reaper (heartbeat-based),
    but the status string is useful for the UI.
    """
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE indexing_jobs
                      SET status = 'running', heartbeat_at = NOW()
                    WHERE id = %s AND claimed_by = %s""",
                (job_id, WORKER_ID),
            )
    finally:
        pool.putconn(conn)


def heartbeat_job(job_id: int) -> bool:
    """Bump ``heartbeat_at`` to prove this worker is still alive.

    Returns ``False`` if the row was already reclaimed by another worker
    (``claimed_by`` changed): the caller should abort processing so we
    don't end up with two workers writing to the same collection.
    """
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE indexing_jobs
                      SET heartbeat_at = NOW()
                    WHERE id = %s AND claimed_by = %s
                RETURNING id""",
                (job_id, WORKER_ID),
            )
            return cur.fetchone() is not None
    finally:
        pool.putconn(conn)


def complete_job(job_id: int) -> None:
    """Mark a job as successfully finished. Terminal state."""
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE indexing_jobs
                      SET status = 'done',
                          finished_at = NOW(),
                          error_message = NULL
                    WHERE id = %s AND claimed_by = %s""",
                (job_id, WORKER_ID),
            )
    finally:
        pool.putconn(conn)


def fail_job(job_id: int, error_message: str, *, retriable: bool = True) -> None:
    """Mark a job as failed.

    If ``retriable`` is True and attempts < max_attempts, the job goes back
    to 'queued' and the requeue trigger wakes listeners. Otherwise it
    becomes terminal 'error'.
    """
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if retriable:
                cur.execute(
                    """UPDATE indexing_jobs
                          SET status = CASE
                                WHEN attempts < max_attempts THEN 'queued'
                                ELSE 'error' END,
                              error_message = %s,
                              finished_at = CASE
                                WHEN attempts < max_attempts THEN NULL
                                ELSE NOW() END
                        WHERE id = %s AND claimed_by = %s""",
                    (error_message[:4000], job_id, WORKER_ID),
                )
            else:
                cur.execute(
                    """UPDATE indexing_jobs
                          SET status = 'error',
                              error_message = %s,
                              finished_at = NOW()
                        WHERE id = %s AND claimed_by = %s""",
                    (error_message[:4000], job_id, WORKER_ID),
                )
    finally:
        pool.putconn(conn)


def emit_event(
    conversation_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    job_id: int | None = None,
) -> None:
    """Publish a progress event for the backend SSE relay.

    Workers on the indexer Cloud Run service cannot talk to the frontend's
    EventEmitter (different process, different container). They write
    events to ``indexing_events``; the AFTER INSERT trigger fires
    ``NOTIFY indexing_events`` and any backend instance with a browser
    subscribed to this conversation's SSE channel will pick it up.

    Rows are persisted so a browser reconnecting mid-indexing can replay
    missed events via ``GET /conversations/:id/events?since_id=N``.
    """
    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO indexing_events (
                       conversation_id, job_id, event_type, payload
                   ) VALUES (%s, %s, %s, %s)""",
                (conversation_id, job_id, event_type, Json(payload)),
            )
    except Exception as e:
        # Event emission must never block indexing — log and move on.
        logger.warning(f"⚠️ emit_event({event_type}) failed: {e}")
    finally:
        pool.putconn(conn)
