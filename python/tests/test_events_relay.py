"""End-to-end tests for the worker loop's event relay.

Verifies that ``emit_event`` actually writes rows to ``indexing_events``
and fires ``NOTIFY indexing_events`` so the backend SSE relay receives
them. Live-DB test; skipped when Postgres is unreachable.
"""

from __future__ import annotations

import os
import uuid

import pytest

DEFAULT_LOCAL_DSN = "postgresql://chatrag:chatrag@localhost:5432/chatrag"
os.environ.setdefault("DATABASE_URL", DEFAULT_LOCAL_DSN)


def _db_reachable() -> bool:
    try:
        import psycopg2

        with psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_reachable(),
    reason="Postgres not reachable at DATABASE_URL; skipping events tests",
)


@pytest.fixture()
def conv_id():
    import psycopg2

    cid = f"evt-{uuid.uuid4().hex[:10]}"
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO conversations (
                       id, salt, status, storage_namespace,
                       vector_collection_name, indexing_mode
                   ) VALUES (%s, gen_random_uuid(), 'processing', %s, %s, 'local')""",
                (cid, cid, f"conversation_{cid}"),
            )
    yield cid
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM indexing_events WHERE conversation_id = %s", (cid,))
            cur.execute("DELETE FROM indexing_jobs WHERE conversation_id = %s", (cid,))
            cur.execute("DELETE FROM conversations WHERE id = %s", (cid,))


def test_emit_event_persists_row(conv_id):
    from shared.job_queue import emit_event
    import psycopg2

    emit_event(conv_id, "page_progress", {"parsed": 5, "total": 100})
    emit_event(conv_id, "welcome_message", {"content": "hello"})

    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT event_type, payload
                     FROM indexing_events
                    WHERE conversation_id = %s
                 ORDER BY id""",
                (conv_id,),
            )
            rows = cur.fetchall()

    assert len(rows) == 2
    assert rows[0][0] == "page_progress"
    assert rows[0][1] == {"parsed": 5, "total": 100}
    assert rows[1][0] == "welcome_message"
    assert rows[1][1] == {"content": "hello"}


def test_emit_event_fires_notify(conv_id):
    """A LISTEN'ing connection should receive the notification.

    This is the mechanism that lets the backend SSE relay wake up the
    instant a worker emits progress — without it, the browser would
    only see events on poll cycles.
    """
    import select
    import psycopg2
    import psycopg2.extensions

    from shared.job_queue import emit_event

    listener = psycopg2.connect(os.environ["DATABASE_URL"])
    listener.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with listener.cursor() as cur:
            cur.execute("LISTEN indexing_events")

        emit_event(conv_id, "page_progress", {"parsed": 1, "total": 1})

        # Wait up to 2s for the NOTIFY to propagate. Should arrive in
        # low milliseconds on a healthy local Postgres.
        readable, _, _ = select.select([listener], [], [], 2.0)
        assert readable, "NOTIFY did not arrive within 2s"
        listener.poll()
        assert listener.notifies, "expected at least one notification"
        note = listener.notifies.pop(0)
        assert note.channel == "indexing_events"
        assert note.payload.isdigit(), f"payload should be event id, got {note.payload!r}"
    finally:
        listener.close()
