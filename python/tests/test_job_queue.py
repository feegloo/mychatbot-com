"""Race-safety + lifecycle tests for the Postgres job queue.

These run against a live Postgres (local via docker-compose or whichever
instance ``DATABASE_URL`` points at). Skipped automatically when no DB is
reachable so CI without Postgres stays green.

The key invariant we verify: when N workers race to claim M jobs, each
job is claimed by at most one worker. Any other behaviour would cause two
Cloud Run instances to index the same book in parallel, producing
duplicate Chroma chunks and double-billed OCR.
"""

from __future__ import annotations

import concurrent.futures
import os
import uuid

import pytest

DEFAULT_LOCAL_DSN = (
    "postgresql://chatrag:chatrag@localhost:5432/chatrag"
)
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
    reason="Postgres not reachable at DATABASE_URL; skipping live queue tests",
)


@pytest.fixture()
def clean_queue():
    """Create a throwaway conversation row to satisfy the FK, then clean up."""
    import psycopg2

    conv_id = f"qtest-{uuid.uuid4().hex[:10]}"
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO conversations (
                       id, salt, status, storage_namespace,
                       vector_collection_name, indexing_mode
                   ) VALUES (%s, gen_random_uuid(), 'processing', %s, %s, 'local')
                   ON CONFLICT (id) DO NOTHING""",
                (conv_id, conv_id, f"conversation_{conv_id}"),
            )
    yield conv_id
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM indexing_jobs WHERE conversation_id = %s",
                (conv_id,),
            )
            cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))


def test_claim_returns_none_when_queue_empty(clean_queue):
    from shared.job_queue import claim_job

    assert claim_job() is None


def test_enqueue_and_claim_roundtrip(clean_queue):
    from shared.job_queue import claim_job, complete_job, enqueue_job

    job_id = enqueue_job(
        conversation_id=clean_queue,
        collection_name=f"conversation_{clean_queue}",
        file_paths=["/tmp/a.pdf", "/tmp/b.pdf"],
        metadata={"foo": "bar"},
    )
    assert job_id > 0

    claimed = claim_job()
    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.conversation_id == clean_queue
    assert claimed.file_paths == ["/tmp/a.pdf", "/tmp/b.pdf"]
    assert claimed.metadata == {"foo": "bar"}
    # attempts is incremented atomically inside the claim UPDATE.
    assert claimed.attempts == 1

    complete_job(job_id)
    # Done jobs are NOT reclaimable.
    assert claim_job() is None


def test_claim_is_race_safe_across_workers(clean_queue):
    """The critical test: N threads compete for M jobs, no duplicates."""
    from shared.job_queue import complete_job, enqueue_job

    n_jobs = 20
    for i in range(n_jobs):
        enqueue_job(
            conversation_id=clean_queue,
            collection_name=f"conversation_{clean_queue}",
            file_paths=[f"/tmp/race_{i}.pdf"],
        )

    # Each thread imports claim_job fresh and drains until empty, recording
    # every job id it claimed. With SKIP LOCKED we should see each id in
    # exactly one thread's output.
    def drain() -> list[int]:
        from shared.job_queue import claim_job

        claimed: list[int] = []
        while True:
            job = claim_job()
            if job is None:
                return claimed
            claimed.append(job.id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: drain(), range(8)))

    all_claimed: list[int] = [jid for batch in results for jid in batch]
    assert len(all_claimed) == n_jobs, (
        f"Expected {n_jobs} total claims, got {len(all_claimed)}"
    )
    assert len(set(all_claimed)) == n_jobs, (
        f"Duplicate claims detected: {sorted(all_claimed)}"
    )

    # Clean up — complete every claimed job so the fixture teardown can
    # DELETE without FK issues (cascade would work too, just be explicit).
    for jid in set(all_claimed):
        complete_job(jid)


def test_heartbeat_detects_reclaim_by_other_worker(clean_queue, monkeypatch):
    """If another worker re-claims our stale job, our heartbeat must fail."""
    import shared.job_queue as jq

    job_id = jq.enqueue_job(
        conversation_id=clean_queue,
        collection_name=f"conversation_{clean_queue}",
        file_paths=["/tmp/hb.pdf"],
    )

    # Worker A claims.
    monkeypatch.setattr(jq, "WORKER_ID", "worker-a")
    a = jq.claim_job()
    assert a is not None and a.id == job_id

    # Worker B rudely rewrites claimed_by (simulating stale-lease reclaim
    # without going through the full STALE_LEASE_SECONDS wait).
    import psycopg2

    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE indexing_jobs SET claimed_by = 'worker-b' WHERE id = %s",
                (job_id,),
            )

    # Worker A's heartbeat now matches no rows → returns False so A knows
    # to abort before dual-writing to the same collection.
    assert jq.heartbeat_job(job_id) is False

    jq.fail_job(job_id, "abandoned", retriable=False)


def test_fail_requeues_while_attempts_remain(clean_queue):
    import shared.job_queue as jq

    job_id = jq.enqueue_job(
        conversation_id=clean_queue,
        collection_name=f"conversation_{clean_queue}",
        file_paths=["/tmp/retry.pdf"],
        max_attempts=2,
    )

    # First attempt: claim + fail retriably → should go back to 'queued'.
    first = jq.claim_job()
    assert first is not None and first.attempts == 1
    jq.fail_job(first.id, "transient", retriable=True)

    # Second claim increments attempts to 2.
    second = jq.claim_job()
    assert second is not None
    assert second.id == first.id
    assert second.attempts == 2

    # Fail again: attempts == max_attempts, so status goes terminal 'error'.
    jq.fail_job(second.id, "still broken", retriable=True)

    # Terminal rows are not claimable anymore.
    assert jq.claim_job() is None
