"""Worker loop that pulls jobs from the Postgres queue and indexes them.

Runs as a background FastAPI task (started in ``server.py``'s startup
hook) when ``WORKER_MODE=cloud_run``. In local dev the HTTP ``/index-stream``
path stays authoritative, so this loop simply doesn't start.

Design:
  * A single persistent ``LISTEN indexing_jobs_new`` connection sleeps on
    ``select.select()`` for instant wake-up on new work. A 30s poll
    fallback covers dropped NOTIFY connections (they can be terminated by
    Cloud Run networking / Cloud SQL side).
  * A ``threading.Semaphore(MAX_CONCURRENT_JOBS)`` caps per-instance
    parallelism. When the slot count reaches the cap, the loop stops
    calling ``claim_job()`` — that's how we avoid hoarding jobs from
    other instances.
  * Each claimed job runs in its own worker thread; a heartbeat thread
    updates ``heartbeat_at`` every ``HEARTBEAT_INTERVAL`` seconds so
    reapers can distinguish "slow OCR call" from "worker died".
  * Every progress event emitted by ``index_documents()`` is routed to
    ``emit_event`` → ``indexing_events`` table → backend SSE.

This module is deliberately free of FastAPI imports so it can be unit-tested
without spinning up the full server.
"""

from __future__ import annotations

import logging
import os
import select
import threading
import time
from typing import Any

import psycopg2
import psycopg2.extensions

from .config import get_settings
from .indexing import index_documents
from .job_queue import (
    IndexingJob,
    WORKER_ID,
    claim_job,
    complete_job,
    emit_event,
    fail_job,
    heartbeat_job,
    mark_running,
)

logger = logging.getLogger(__name__)


# Per-instance parallelism cap. At N=2 one instance can index two small
# books at once; a 611-page OCR book would use its own slot and still
# leave the other free for a fast text PDF.
MAX_CONCURRENT_JOBS = int(os.environ.get("WORKER_MAX_CONCURRENT_JOBS", "2"))

# How often the worker thread bumps heartbeat_at. Must be << STALE_LEASE_SECONDS
# so reapers don't false-positive mid-OCR pauses.
HEARTBEAT_INTERVAL = int(os.environ.get("WORKER_HEARTBEAT_INTERVAL", "30"))

# Polling fallback for dropped NOTIFY connections. The normal path is
# LISTEN wake-up; poll only catches edge cases.
POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", "30"))

# Channel name must match the one in the migration trigger.
_NEW_JOB_CHANNEL = "indexing_jobs_new"


class WorkerLoop:
    """Single-process worker that drains the indexing_jobs queue."""

    def __init__(
        self,
        *,
        max_concurrent_jobs: int = MAX_CONCURRENT_JOBS,
        heartbeat_interval: int = HEARTBEAT_INTERVAL,
        poll_interval: int = POLL_INTERVAL,
    ) -> None:
        self._slots = threading.BoundedSemaphore(max_concurrent_jobs)
        self._max = max_concurrent_jobs
        self._heartbeat_interval = heartbeat_interval
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._dispatcher_thread: threading.Thread | None = None
        # Active workers — kept so we can join on shutdown.
        self._active_threads: set[threading.Thread] = set()
        self._active_lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self) -> None:
        """Start the dispatcher in a daemon thread. Idempotent."""
        if self._dispatcher_thread and self._dispatcher_thread.is_alive():
            return
        self._stop_event.clear()
        t = threading.Thread(
            target=self._dispatch_loop,
            name="indexing-dispatcher",
            daemon=True,
        )
        self._dispatcher_thread = t
        t.start()
        logger.info(
            f"🧑‍🏭 Worker loop started (id={WORKER_ID}, "
            f"max_concurrent={self._max}, heartbeat={self._heartbeat_interval}s)"
        )

    def stop(self, *, join_timeout: float = 5.0) -> None:
        """Signal the dispatcher to exit; wait briefly for in-flight jobs."""
        self._stop_event.set()
        if self._dispatcher_thread:
            self._dispatcher_thread.join(timeout=join_timeout)
        with self._active_lock:
            threads = list(self._active_threads)
        for t in threads:
            t.join(timeout=join_timeout)

    # ── dispatcher ───────────────────────────────────────────────────
    def _dispatch_loop(self) -> None:
        """Main loop: wait for notify/poll, drain available capacity."""
        listen_conn = self._open_listen_connection()
        try:
            while not self._stop_event.is_set():
                # Drain as many jobs as we have slots for. Each ``claim_job``
                # is a single atomic UPDATE, so two iterations here can't
                # claim the same row. Stop when slots are exhausted or the
                # queue reports empty.
                drained = self._drain_available_slots()
                if self._stop_event.is_set():
                    break
                # Sleep until a NOTIFY arrives or the poll tick fires.
                self._wait_for_wakeup(listen_conn, drained_any=drained > 0)
        finally:
            try:
                listen_conn.close()
            except Exception:
                pass

    def _drain_available_slots(self) -> int:
        """Claim jobs up to ``self._max`` concurrent. Returns count claimed."""
        claimed = 0
        while not self._stop_event.is_set():
            # Non-blocking slot check; if full, yield to running workers.
            if not self._slots.acquire(blocking=False):
                return claimed
            job = claim_job()
            if job is None:
                # Nothing pickable; release the slot we just reserved.
                self._slots.release()
                return claimed
            # Spawn worker thread for this job. It will ``release`` the slot
            # in its ``finally`` block.
            self._spawn_worker(job)
            claimed += 1
        # Released from the outer loop because stop was requested.
        return claimed

    def _wait_for_wakeup(
        self, listen_conn: psycopg2.extensions.connection, *, drained_any: bool
    ) -> None:
        """Block until NOTIFY arrives or ``poll_interval`` elapses.

        If we just drained successfully, use a short poll so a burst of
        uploads doesn't leave us waiting 30s for a second NOTIFY to fire.
        """
        wait_seconds = 1 if drained_any else self._poll_interval
        try:
            readable, _, _ = select.select(
                [listen_conn], [], [], wait_seconds
            )
            if readable:
                listen_conn.poll()
                # Drain all pending notifications. We don't care about the
                # payload (job id) — we'll claim the next available row
                # next iteration.
                while listen_conn.notifies:
                    listen_conn.notifies.pop(0)
        except (InterruptedError, OSError) as e:
            logger.warning(f"listen wait interrupted: {e}")

    # ── worker thread ────────────────────────────────────────────────
    def _spawn_worker(self, job: IndexingJob) -> None:
        t = threading.Thread(
            target=self._run_job,
            args=(job,),
            name=f"indexer-job-{job.id}",
            daemon=True,
        )
        with self._active_lock:
            self._active_threads.add(t)
        t.start()

    def _run_job(self, job: IndexingJob) -> None:
        """Execute a single indexing job with heartbeat + event relay."""
        logger.info(
            f"🧑‍🏭 Claimed job {job.id} (conv={job.conversation_id}, "
            f"attempt={job.attempts}/{job.max_attempts})"
        )
        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job.id, stop_heartbeat),
            name=f"indexer-hb-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            mark_running(job.id)

            def on_progress(event_type: str, data: dict[str, Any]) -> None:
                emit_event(
                    job.conversation_id, event_type, data, job_id=job.id
                )

            # Files may have been uploaded to GCS and not yet materialised
            # on this worker's disk. Rehydrate before calling into the
            # indexer (which still expects local paths).
            rehydrated = _ensure_files_local(job)

            result = index_documents(
                conversation_id=job.conversation_id,
                collection_name=job.collection_name,
                file_paths=rehydrated,
                on_progress=on_progress,
            )
            complete_job(job.id)
            logger.info(
                f"✅ Job {job.id} done: "
                f"{result.get('chunk_count', 0)} chunks"
            )
        except Exception as e:
            logger.exception(f"❌ Job {job.id} failed")
            # The 400 max-tokens error, bad PDF files, etc. are not worth
            # retrying (same input → same failure). Leave retriable=True
            # as the default so transient issues (OCR rate limit, DB blip)
            # get another go; the attempt counter bounds total retries.
            try:
                emit_event(
                    job.conversation_id,
                    "error",
                    {"error": str(e)[:1000]},
                    job_id=job.id,
                )
            except Exception:
                pass
            fail_job(job.id, str(e))
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=self._heartbeat_interval + 2)
            self._slots.release()
            with self._active_lock:
                self._active_threads.discard(threading.current_thread())

    def _heartbeat_loop(
        self, job_id: int, stop_event: threading.Event
    ) -> None:
        """Bump heartbeat_at while the job runs. Abort on reclaim."""
        while not stop_event.wait(self._heartbeat_interval):
            try:
                if not heartbeat_job(job_id):
                    # Someone else reclaimed this job (our lease went
                    # stale). Stop processing to avoid dual-write.
                    logger.warning(
                        f"⚠️ Job {job_id} was reclaimed by another worker; "
                        f"aborting heartbeat (indexing will continue until "
                        f"the next safe checkpoint)."
                    )
                    return
            except Exception as e:
                logger.warning(f"heartbeat for job {job_id} failed: {e}")

    # ── helpers ──────────────────────────────────────────────────────
    def _open_listen_connection(self) -> psycopg2.extensions.connection:
        """Open a dedicated connection for ``LISTEN``. Not pool-managed
        because LISTEN state is per-connection and the pool may hand the
        same connection to unrelated callers.
        """
        settings = get_settings()
        conn = psycopg2.connect(settings.database_url, connect_timeout=5)
        conn.set_isolation_level(
            psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
        )
        with conn.cursor() as cur:
            cur.execute(f"LISTEN {_NEW_JOB_CHANNEL}")
        logger.info(f"👂 LISTEN {_NEW_JOB_CHANNEL}")
        return conn


def _ensure_files_local(job: IndexingJob) -> list[str]:
    """Resolve each entry in ``job.file_paths`` to a local absolute path.

    Workers on different Cloud Run instances have independent ephemeral
    filesystems. To let any worker pick up any job, the backend enqueues
    jobs with either:
      • an already-local path (when the backend and the worker share a
        volume, e.g. local dev), or
      • a ``gs://bucket/key`` URI that any worker can download.

    Local paths that already exist are returned as-is; gs:// URIs are
    downloaded into ``/tmp`` (Cloud Run's writable scratch). A missing
    local path is logged and skipped rather than failing the whole job,
    so a partial rehydrate still produces a best-effort index.
    """
    resolved: list[str] = []
    failures: list[str] = []
    for entry in job.file_paths:
        # Entries may be a single path/URI or pipe-separated candidates
        # (e.g. "/app/storage/foo.pdf|gs://bucket/key") so the worker can
        # prefer a local copy when it happens to be on the same instance
        # and fall back to GCS download otherwise.
        candidates = [c for c in entry.split("|") if c]
        chosen: str | None = None
        entry_errors: list[str] = []
        for candidate in candidates:
            if candidate.startswith("gs://"):
                try:
                    chosen = _download_gcs_blob(candidate)
                    break
                except Exception as e:
                    entry_errors.append(f"{candidate}: {e!r}")
                    continue
            elif os.path.exists(candidate):
                chosen = candidate
                break
            else:
                entry_errors.append(f"{candidate}: not found on local fs")
        if chosen is not None:
            resolved.append(chosen)
        else:
            detail = "; ".join(entry_errors) or "no candidates"
            logger.warning(
                f"⚠️ Job {job.id}: no readable candidate for {entry} ({detail})"
            )
            failures.append(f"{entry} -> {detail}")
    if not resolved:
        raise RuntimeError(
            f"Job {job.id} has no readable file paths. Failures: "
            + " | ".join(failures)
        )
    return resolved


def _download_gcs_blob(gs_uri: str) -> str:
    """Download ``gs://bucket/key`` to ``/tmp/<basename>`` and return the path.

    Uses the google-cloud-storage client with ADC / workload identity as
    configured on Cloud Run. Imports are local so unit tests that don't
    exercise rehydration don't require the GCS dependency at import time.
    """
    from pathlib import Path

    from google.cloud import storage as gcs

    without_scheme = gs_uri[len("gs://") :]
    bucket_name, _, blob_path = without_scheme.partition("/")
    if not bucket_name or not blob_path:
        raise ValueError(f"malformed gs:// URI: {gs_uri}")

    local_path = f"/tmp/{Path(blob_path).name}"
    if os.path.exists(local_path):
        # Already materialised by an earlier job on this instance.
        return local_path

    client = gcs.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)
    logger.info(f"📥 Downloaded {gs_uri} → {local_path}")
    return local_path
