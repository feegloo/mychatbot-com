"""Tests for ``shared.pubsub_client``.

No GCP dependency — we only test JSON serialization and env-var helpers.
The actual ``publish_indexing_job`` call is mocked.
"""

from __future__ import annotations

import json

import pytest

from shared import pubsub_client
from shared.pubsub_client import (
    IndexingJobPayload,
    PubSubNotConfigured,
    get_subscription_path,
    get_topic_path,
    publish_indexing_job,
)


def test_payload_round_trip():
    p = IndexingJobPayload(
        worker_name="chatrag-001",
        file_names=["/tmp/a.pdf", "gs://b/a.pdf"],
        conversation_id="conv-1",
        collection_name="col-1",
        job_id="job-uuid",
        storage_namespace="ns",
        metadata={"k": "v"},
    )
    raw = p.to_json()
    parsed = json.loads(raw)
    # Field names match the contract requested by the user.
    assert parsed["workerName"] == "chatrag-001"
    assert parsed["fileName"] == ["/tmp/a.pdf", "gs://b/a.pdf"]
    assert parsed["conversationId"] == "conv-1"

    revived = IndexingJobPayload.from_json(raw)
    assert revived == p


def test_from_json_tolerates_missing_optional_fields():
    raw = json.dumps(
        {
            "workerName": "",
            "fileName": ["a.pdf"],
            "conversationId": "c1",
            "collectionName": "col",
        }
    ).encode()
    payload = IndexingJobPayload.from_json(raw)
    assert payload.job_id  # auto-generated UUID
    assert payload.metadata == {}
    assert payload.storage_namespace is None


def test_get_topic_path_requires_env(monkeypatch):
    monkeypatch.delenv("PUBSUB_TOPIC", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(PubSubNotConfigured):
        get_topic_path()


def test_get_topic_path_short_name(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-proj")
    monkeypatch.setenv("PUBSUB_TOPIC", "chatrag-indexing")
    assert get_topic_path() == "projects/my-proj/topics/chatrag-indexing"


def test_get_topic_path_full_path(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-proj")
    monkeypatch.setenv("PUBSUB_TOPIC", "projects/other/topics/x")
    assert get_topic_path() == "projects/other/topics/x"


def test_get_subscription_path_short(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-proj")
    monkeypatch.setenv("PUBSUB_SUBSCRIPTION", "chatrag-indexing-sub")
    assert (
        get_subscription_path()
        == "projects/my-proj/subscriptions/chatrag-indexing-sub"
    )


def test_publish_invokes_publisher_with_attributes(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "my-proj")
    monkeypatch.setenv("PUBSUB_TOPIC", "chatrag-indexing")

    captured: dict = {}

    class _FakeFuture:
        def result(self, timeout=None):
            return "msg-123"

    class _FakePublisher:
        def publish(self, topic, data, **attrs):
            captured["topic"] = topic
            captured["data"] = data
            captured["attrs"] = attrs
            return _FakeFuture()

    monkeypatch.setattr(pubsub_client, "_get_publisher", lambda: _FakePublisher())

    payload = IndexingJobPayload(
        worker_name="w1",
        file_names=["a.pdf"],
        conversation_id="conv-1",
        collection_name="col",
        job_id="j1",
    )
    msg_id = publish_indexing_job(payload)
    assert msg_id == "msg-123"
    assert captured["topic"] == "projects/my-proj/topics/chatrag-indexing"
    assert captured["attrs"]["worker"] == "w1"
    assert captured["attrs"]["conversation_id"] == "conv-1"
    assert json.loads(captured["data"])["jobId"] == "j1"
