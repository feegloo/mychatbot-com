"""Long-running Pub/Sub subscriber for the chatrag-worker service."""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from concurrent import futures
from contextlib import nullcontext
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import sentry_sdk  # noqa: E402

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("SENTRY_ENVIRONMENT", "dev"),
    send_default_pii=True,
    traces_sample_rate=1.0,
    max_value_length=8192,
    enable_logs=True,
)

from sentry_sdk import logger as sentry_logger  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Maximum seconds a single indexing job may run before it is abandoned.
_JOB_TIMEOUT_SEC = int(os.environ.get("JOB_TIMEOUT_SEC", "900"))

# Cold-start metrics: first message latency since process boot.
_PROCESS_BOOT_TS = time.time()
_FIRST_JOB_SEEN = False


def _emit_event_to_db(
    conversation_id: str,
    event_type: str,
    payload: dict,
    *,
    job_id: str | None,
) -> None:
    """Write a progress event to ``indexing_events`` for the backend SSE relay."""
    from psycopg2.extras import Json

    from shared.telemetry import _get_db_pool

    enriched_payload = dict(payload)
    if job_id:
        enriched_payload.setdefault("job_id", job_id)

    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO indexing_events (
                       conversation_id, event_type, payload
                   ) VALUES (%s, %s, %s)""",
                (conversation_id, event_type, Json(enriched_payload)),
            )
    except Exception as e:
        logger.warning(f"⚠️ emit_event({event_type}) failed: {e}")
    finally:
        pool.putconn(conn)


def _ensure_files_local(file_paths: list[str]) -> list[str]:
    """Resolve each payload entry to a local readable path."""
    resolved: list[str] = []
    for entry in file_paths:
        candidates = entry.split("|")
        local_candidate = next((c for c in candidates if not c.startswith("gs://")), None)
        gs_candidate = next((c for c in candidates if c.startswith("gs://")), None)

        if local_candidate and Path(local_candidate).exists():
            resolved.append(local_candidate)
            continue

        if gs_candidate:
            resolved.append(_download_from_gcs(gs_candidate))
            continue

        raise FileNotFoundError(f"Cannot resolve {entry!r} to a readable file")
    return resolved


def _download_from_gcs(gs_uri: str) -> str:
    """Download a ``gs://`` URI to ``/tmp`` and return the local path."""
    from google.cloud import storage as gcs

    parts = gs_uri.replace("gs://", "", 1).split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Malformed GCS URI: {gs_uri}")
    bucket_name, blob_path = parts

    client = gcs.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    local_path = f"/tmp/{Path(blob_path).name}"
    blob.download_to_filename(local_path)
    logger.info(f"📥 Downloaded {gs_uri} → {local_path}")
    return local_path


def _process_message(message) -> None:
    """Handle a single Pub/Sub message.

    ACK on success / unrecoverable failure (don't retry broken payloads).
    NACK on transient failure so Pub/Sub redelivers.
    """
    from shared.indexing import index_documents
    from shared.pubsub_client import IndexingJobPayload

    try:
        payload = IndexingJobPayload.from_json(message.data)
    except Exception as e:
        logger.error(f"❌ Malformed Pub/Sub payload (ack to drop): {e}")
        sentry_sdk.capture_exception(e)
        message.ack()
        return

    metadata = payload.metadata or {}
    trace_id = str(metadata.get("traceId") or "")
    upstream_sentry_trace = str(metadata.get("sentryTrace") or "")
    upstream_baggage = str(metadata.get("baggage") or "")

    global _FIRST_JOB_SEEN
    if not _FIRST_JOB_SEEN:
        _FIRST_JOB_SEEN = True
        cold_start_seconds = round(time.time() - _PROCESS_BOOT_TS, 3)
        sentry_logger.debug(
            "chatrag-worker cold start initialized",
            attributes={
                "cold_start_seconds": cold_start_seconds,
                "job_id": payload.job_id,
                "conversation_id": payload.conversation_id,
                "trace_id": trace_id,
            },
        )
        sentry_sdk.capture_message(
            f"chatrag-worker cold start: {cold_start_seconds}s",
            level="debug",
        )

    if trace_id:
        sentry_sdk.set_tag("trace_id", trace_id)

    trace_ctx = (
        sentry_sdk.continue_trace(
            {
                "sentry-trace": upstream_sentry_trace,
                "baggage": upstream_baggage,
            }
        )
        if upstream_sentry_trace
        else nullcontext()
    )

    with trace_ctx:
        with sentry_sdk.start_span(
            name="worker.process_indexing_job",
            op="queue.process",
            attributes={
                "conversation_id": payload.conversation_id,
                "job_id": payload.job_id,
                "chatrag.trace_id": trace_id,
            },
        ):
            logger.info(
                f"📨 Received job {payload.job_id} "
                f"(conv={payload.conversation_id}, files={len(payload.file_names)})"
            )
            sentry_logger.info(
                "Worker received indexing job",
                attributes={
                    "job_id": payload.job_id,
                    "conversation_id": payload.conversation_id,
                    "file_count": len(payload.file_names),
                    "requested_by": payload.worker_name,
                    "trace_id": trace_id,
                },
            )

            def on_progress(event_type: str, data: dict) -> None:
                enriched = dict(data)
                if event_type in ("welcome_message", "complete"):
                    enriched.setdefault(
                        "_meta",
                        {
                            "uploadedFileNames": metadata.get("uploadedFileNames", []),
                            "storedToOriginal": metadata.get("storedToOriginal", {}),
                            "traceId": trace_id,
                        },
                    )
                _emit_event_to_db(
                    payload.conversation_id,
                    event_type,
                    enriched,
                    job_id=payload.job_id,
                )

            try:
                local_paths = _ensure_files_local(payload.file_names)
            except Exception as e:
                logger.exception(f"❌ Failed to resolve files for job {payload.job_id}: {e}")
                sentry_sdk.capture_exception(e)
                on_progress("error", {"error": f"file resolution failed: {e}"})
                message.ack()
                return

            start_ts = time.time()
            executor = futures.ThreadPoolExecutor(max_workers=1)
            job_future = executor.submit(
                index_documents,
                conversation_id=payload.conversation_id,
                collection_name=payload.collection_name,
                file_paths=local_paths,
                on_progress=on_progress,
                job_metadata=payload.metadata,
                allow_delegation=False,
            )
            try:
                job_future.result(timeout=_JOB_TIMEOUT_SEC)
                elapsed = round(time.time() - start_ts, 3)
                logger.info(f"✅ Job {payload.job_id} done in {elapsed}s")
                sentry_logger.debug(
                    "Worker finished indexing job",
                    attributes={
                        "job_id": payload.job_id,
                        "conversation_id": payload.conversation_id,
                        "duration_seconds": elapsed,
                        "trace_id": trace_id,
                    },
                )
                message.ack()
            except futures.TimeoutError:
                elapsed = int(time.time() - start_ts)
                logger.error(
                    f"⏱️ Job {payload.job_id} timed out after {elapsed}s "
                    f"(limit={_JOB_TIMEOUT_SEC}s)"
                )
                sentry_sdk.capture_message(
                    f"Indexing job timed out: {payload.conversation_id}",
                    level="error",
                )
                on_progress("error", {"error": f"Processing timed out after {elapsed}s"})
                message.ack()
            except Exception as e:
                logger.exception(f"❌ Job {payload.job_id} failed: {e}")
                sentry_sdk.capture_exception(e)
                on_progress("error", {"error": str(e)[:500]})
                message.nack()
            finally:
                executor.shutdown(wait=False)


def main() -> int:
    from google.cloud import pubsub_v1

    from shared.pubsub_client import get_subscription_path

    subscription_path = get_subscription_path()
    logger.info(f"🚀 chatrag-worker subscribing to {subscription_path}")

    subscriber = pubsub_v1.SubscriberClient()

    max_messages = int(os.environ.get("PUBSUB_MAX_MESSAGES", "1"))
    flow_control = pubsub_v1.types.FlowControl(max_messages=max_messages)

    streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=_process_message,
        flow_control=flow_control,
    )

    def _shutdown(_signum, _frame):
        logger.info("🛑 Shutdown signal received; draining subscriber...")
        streaming_pull_future.cancel()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        streaming_pull_future.result()
    except futures.CancelledError:
        logger.info("Subscriber cancelled.")
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        streaming_pull_future.result()
    except Exception as e:
        logger.exception(f"Subscriber died unexpectedly: {e}")
        sentry_sdk.capture_exception(e)
        return 1
    finally:
        from shared.telemetry import flush_processing_errors

        flush_processing_errors(timeout=10.0)
        subscriber.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
