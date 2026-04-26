import json
import psycopg
from ..utils.payloads import Payload, get_payload_value


def insert_conversation_metadata(
    connection: psycopg.Connection,
    payload: Payload,
    worker_id: str,
    event_type: str,
    message: str,
    source: str = "worker",
    topic_name: str | None = None,
    direction: str | None = None,
) -> None:
    """Insert one full-flow debug event into conversations_metadatas."""
    uid = get_payload_value(payload, "uid", "home")
    trace_id = get_payload_value(payload, "traceId", "missing-trace-id")
    fingerprint = payload.get("fingerprint")

    ensure_conversation_exists(connection, uid, trace_id)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversations_metadatas(
                uid,
                trace_id,
                fingerprint,
                source,
                event_type,
                topic_name,
                direction,
                payload,
                message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                uid,
                trace_id,
                str(fingerprint) if fingerprint else None,
                source,
                event_type,
                topic_name,
                direction,
                json.dumps({**payload, "worker_id": worker_id}),
                message,
            ),
        )


def ensure_conversation_exists(connection: psycopg.Connection, uid: str, trace_id: str) -> None:
    """Ensure metadata has valid conversations foreign key target."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversations(uid, trace_id, status)
            VALUES (%s, %s, 'metadata-only')
            ON CONFLICT (uid) DO NOTHING
            """,
            (uid, trace_id),
        )
