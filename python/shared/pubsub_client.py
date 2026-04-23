"""GCP Pub/Sub client for delegating indexing work to remote workers.

Replaces the previous Postgres-backed ``indexing_jobs`` queue. The main
``chatrag`` instance publishes a JSON job payload when its local CPU
budget is exhausted; the ``chatrag-worker`` service runs a pull
subscriber that dispatches to ``index_documents``.

Design notes:
  * **No strict routing.** ``worker_name`` in the payload is advisory
    (useful in logs to trace which instance *requested* delegation);
    any worker listening on the shared subscription may consume it.
  * **Payload is self-contained** so workers never round-trip to the
    backend for job details. ``file_names`` is a list of paths; each
    entry may be a local absolute path or a ``gs://`` URI fallback.
  * **Ack deadline** is configured on the subscription, not here
    (large PDFs can take minutes — use Pub/Sub's modifyAckDeadline
    via subscriber client which does it automatically).
  * **Local dev**: set ``PUBSUB_EMULATOR_HOST=localhost:8085`` and the
    google-cloud-pubsub library transparently routes all RPCs to the
    in-process emulator (started by ``docker compose up pubsub-emulator``).
    No GCP credentials needed. When ``PUBSUB_TOPIC`` is unset the
    publisher raises ``PubSubNotConfigured`` so callers can fall back
    to inline processing instead.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class PubSubNotConfigured(RuntimeError):
    """Raised when Pub/Sub env vars are missing (local dev / tests)."""


@dataclass
class IndexingJobPayload:
    """The JSON message published to the indexing topic.

    ``worker_name`` is the requester's container id, NOT a routing
    target. All fields except ``worker_name`` are required for the
    worker to process the job.
    """

    worker_name: str
    file_names: list[str]
    conversation_id: str
    collection_name: str
    job_id: str
    storage_namespace: str | None = None
    metadata: dict[str, Any] | None = None

    def to_json(self) -> bytes:
        payload = {
            "workerName": self.worker_name,
            "fileName": self.file_names,
            "conversationId": self.conversation_id,
            "collectionName": self.collection_name,
            "jobId": self.job_id,
            "storageNamespace": self.storage_namespace,
            "metadata": self.metadata or {},
        }
        return json.dumps(payload).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> "IndexingJobPayload":
        obj = json.loads(data.decode("utf-8"))
        return cls(
            worker_name=obj.get("workerName", ""),
            file_names=list(obj.get("fileName") or []),
            conversation_id=obj["conversationId"],
            collection_name=obj["collectionName"],
            job_id=obj.get("jobId") or str(uuid.uuid4()),
            storage_namespace=obj.get("storageNamespace"),
            metadata=obj.get("metadata") or {},
        )


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def get_topic_path() -> str:
    """Return the fully-qualified topic path, e.g.
    ``projects/my-proj/topics/chatrag-indexing``.

    Raises ``PubSubNotConfigured`` when ``PUBSUB_TOPIC`` or
    ``GCP_PROJECT_ID`` is missing.
    """
    project = _env("GCP_PROJECT_ID")
    topic = _env("PUBSUB_TOPIC")
    if not project or not topic:
        raise PubSubNotConfigured(
            "PUBSUB_TOPIC and GCP_PROJECT_ID must be set to publish indexing jobs",
        )
    # Callers can pass either a short name or a full path
    if topic.startswith("projects/"):
        return topic
    return f"projects/{project}/topics/{topic}"


def get_subscription_path() -> str:
    project = _env("GCP_PROJECT_ID")
    sub = _env("PUBSUB_SUBSCRIPTION")
    if not project or not sub:
        raise PubSubNotConfigured(
            "PUBSUB_SUBSCRIPTION and GCP_PROJECT_ID must be set to subscribe",
        )
    if sub.startswith("projects/"):
        return sub
    return f"projects/{project}/subscriptions/{sub}"


# Lazy singleton so importing this module has no side effects
_publisher = None


def _get_publisher():
    global _publisher
    if _publisher is None:
        from google.cloud import pubsub_v1

        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_indexing_job(payload: IndexingJobPayload) -> str:
    """Publish a job to the indexing topic. Blocks until broker ack.

    Returns the message id. Raises ``PubSubNotConfigured`` if topic
    env vars are missing, or any ``google.api_core`` exception on
    publish failure — callers should fall back to inline processing.
    """
    topic_path = get_topic_path()
    publisher = _get_publisher()
    future = publisher.publish(
        topic_path,
        payload.to_json(),
        # Attributes are indexed for subscription filtering; keep workerName
        # here too so Pub/Sub filter expressions can target a specific worker
        # if we ever want strict routing.
        worker=payload.worker_name,
        conversation_id=payload.conversation_id,
    )
    message_id = future.result(timeout=10)
    logger.info(
        f"📤 Published indexing job → {topic_path} "
        f"(msg_id={message_id}, job={payload.job_id}, files={len(payload.file_names)})"
    )
    return message_id
