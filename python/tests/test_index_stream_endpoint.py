"""Tests for the /index-stream endpoint in server.py.

Critical regression guard: verifies that ``on_progress`` is wired through to
``index_documents`` so that welcome_message + complete events are actually
streamed to the caller rather than silently dropped.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src import server


@pytest.mark.asyncio
async def test_index_stream_passes_on_progress_to_index_documents(monkeypatch):
    """on_progress must reach index_documents so events are emitted to the stream."""
    received_events: list[dict] = []

    def _fake_index_documents(
        *,
        _conversation_id=None,
        _collection_name=None,
        _file_paths=None,
        on_progress,
        _user_language=None,
        **_,
    ):
        # Simulate the inline pipeline emitting the expected events.
        assert on_progress is not None, (
            "on_progress was not passed to index_documents — events will never be streamed"
        )
        on_progress("welcome_message", {"welcome_message": "Hello from doc"})
        on_progress(
            "complete",
            {
                "suggested_questions": ["Q1"],
                "welcome_message": "Hello from doc",
                "file_metadata": {},
            },
        )
        return {"ok": True}

    monkeypatch.setattr(server, "index_documents", _fake_index_documents)

    req = server.IndexRequest(
        conversation_id="test-conv-1",
        collection_name="col_test-conv-1",
        file_paths=["/tmp/test.txt"],
    )

    response = await server.index_stream(req)

    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            raw = chunk.decode("utf-8")
        elif isinstance(chunk, str):
            raw = chunk
        else:
            continue
        for line in raw.split("\n"):
            if line.strip():
                received_events.append(json.loads(line))

    event_types = [e["event"] for e in received_events]
    assert "welcome_message" in event_types, (
        f"welcome_message not in stream; got: {event_types}"
    )
    assert "complete" in event_types, (
        f"complete not in stream; got: {event_types}"
    )
    assert event_types[-1] == "complete", (
        "complete must be the last event in the stream"
    )
    welcome_evt = next(e for e in received_events if e["event"] == "welcome_message")
    assert welcome_evt["data"]["welcome_message"] == "Hello from doc"
