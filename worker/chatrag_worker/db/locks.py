import psycopg
from typing import Optional
from ..utils.payloads import Payload, get_payload_value


def fetch_lock_owner(connection: psycopg.Connection, uid: str) -> Optional[str]:
    """Read worker id that owns the processing lock for a conversation uid."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT worker_id FROM processing_locks WHERE uid = %s", (uid,))
        row = cursor.fetchone()
        return row["worker_id"] if row else None


def insert_processing_lock(connection: psycopg.Connection, payload: Payload, worker_id: str) -> None:
    """Insert a new processing lock row for uploaded PDF processing."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO processing_locks(uid, trace_id, worker_id, file_name, storage_uri, status)
            VALUES (%s, %s, %s, %s, %s, 'processing')
            """,
            (
                get_payload_value(payload, "uid", "missing-uid"),
                get_payload_value(payload, "traceId", "missing-trace-id"),
                worker_id,
                payload.get("fileName"),
                payload.get("storageUri"),
            ),
        )


def acquire_processing_lock(connection: psycopg.Connection, payload: Payload, worker_id: str) -> bool:
    """Acquire PDF-processing lock and verify ownership when unique insert conflicts."""
    uid = get_payload_value(payload, "uid", "missing-uid")

    try:
        insert_processing_lock(connection, payload, worker_id)
        return True
    except psycopg.errors.UniqueViolation:
        connection.rollback()
        return fetch_lock_owner(connection, uid) == worker_id
