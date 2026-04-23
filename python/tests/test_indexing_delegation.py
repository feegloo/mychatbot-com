"""Tests for the CPU-budget + Pub/Sub delegation logic in
``shared.indexing.index_documents``.

The actual indexing pipeline is heavy (PyMuPDF, embeddings); these tests
patch ``_index_documents_inline`` and the publisher so they verify only
the *routing* decision.
"""

from __future__ import annotations

import threading

import pytest

from shared import cpu_budget, indexing
from shared.cpu_budget import MAIN_MAX_CPU


@pytest.fixture(autouse=True)
def _reset_budget(monkeypatch):
    monkeypatch.setattr(cpu_budget, "MAIN_MAX_CPU", 2)
    monkeypatch.setattr(cpu_budget, "_budget", threading.BoundedSemaphore(2))
    monkeypatch.setattr(cpu_budget, "_in_use", 0)
    # Re-import the symbols indexing.py grabbed at function-call time —
    # cpu_budget is imported lazily inside index_documents, so the patches
    # above are picked up automatically on next call.
    yield


def test_runs_inline_when_budget_available(monkeypatch):
    called = {}

    def _fake_inline(*, conversation_id, collection_name, file_paths, on_progress):
        called["ran"] = True
        return {"ok": True}

    monkeypatch.setattr(indexing, "_index_documents_inline", _fake_inline)
    monkeypatch.setattr(cpu_budget, "estimate_slots_for_file", lambda _p: 1)

    result = indexing.index_documents(
        conversation_id="c1",
        collection_name="col1",
        file_paths=["/tmp/small.pdf"],
    )
    assert called.get("ran") is True
    assert result == {"ok": True}


def test_delegates_when_budget_exhausted(monkeypatch):
    monkeypatch.setattr(cpu_budget, "estimate_slots_for_file", lambda _p: 2)

    # Pre-exhaust the budget so the next call cannot reserve.
    assert cpu_budget.try_reserve(2) is True

    published: dict = {}

    def _fake_publish(payload):
        published["payload"] = payload
        return "msg-99"

    monkeypatch.setattr(
        "shared.pubsub_client.publish_indexing_job", _fake_publish
    )
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setenv("PUBSUB_TOPIC", "t")

    inline_called = {"ran": False}

    def _fake_inline(**_):
        inline_called["ran"] = True
        return {}

    monkeypatch.setattr(indexing, "_index_documents_inline", _fake_inline)

    result = indexing.index_documents(
        conversation_id="c1",
        collection_name="col1",
        file_paths=["/tmp/big.pdf"],
    )
    assert result.get("delegated") is True
    assert inline_called["ran"] is False
    assert published["payload"].conversation_id == "c1"
    assert published["payload"].file_names == ["/tmp/big.pdf"]


def test_falls_back_inline_when_pubsub_unconfigured(monkeypatch):
    monkeypatch.setattr(cpu_budget, "estimate_slots_for_file", lambda _p: 2)

    # Exhaust budget so delegation path is taken.
    assert cpu_budget.try_reserve(2) is True

    monkeypatch.delenv("PUBSUB_TOPIC", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

    inline_ran = {}

    def _fake_inline(**_):
        inline_ran["yes"] = True
        return {"ok": True}

    monkeypatch.setattr(indexing, "_index_documents_inline", _fake_inline)
    result = indexing.index_documents(
        conversation_id="c1",
        collection_name="col1",
        file_paths=["/tmp/big.pdf"],
    )
    # Falls back to inline rather than dropping the job.
    assert inline_ran.get("yes") is True
    assert result == {"ok": True}


def test_worker_disables_delegation_runs_inline(monkeypatch):
    monkeypatch.setattr(cpu_budget, "estimate_slots_for_file", lambda _p: 2)
    assert cpu_budget.try_reserve(2) is True  # exhaust

    inline_ran = {}

    def _fake_inline(**_):
        inline_ran["yes"] = True
        return {}

    monkeypatch.setattr(indexing, "_index_documents_inline", _fake_inline)
    indexing.index_documents(
        conversation_id="c1",
        collection_name="col1",
        file_paths=["/tmp/big.pdf"],
        allow_delegation=False,
    )
    assert inline_ran["yes"] is True


def test_releases_slots_after_inline_run(monkeypatch):
    monkeypatch.setattr(cpu_budget, "estimate_slots_for_file", lambda _p: 1)
    monkeypatch.setattr(indexing, "_index_documents_inline", lambda **_: {})
    assert cpu_budget.available_slots() == MAIN_MAX_CPU  # baseline

    indexing.index_documents(
        conversation_id="c1",
        collection_name="col1",
        file_paths=["/tmp/a.pdf"],
    )
    assert cpu_budget.available_slots() == MAIN_MAX_CPU


def test_releases_slots_even_on_inline_exception(monkeypatch):
    monkeypatch.setattr(cpu_budget, "estimate_slots_for_file", lambda _p: 1)

    def _bad(**_):
        raise RuntimeError("boom")

    monkeypatch.setattr(indexing, "_index_documents_inline", _bad)
    with pytest.raises(RuntimeError, match="boom"):
        indexing.index_documents(
            conversation_id="c1",
            collection_name="col1",
            file_paths=["/tmp/a.pdf"],
        )
    assert cpu_budget.available_slots() == MAIN_MAX_CPU
