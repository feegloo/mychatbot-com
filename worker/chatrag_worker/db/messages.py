import psycopg
from ..utils.payloads import Payload, get_payload_value, read_question_from_payload


def insert_conversation_message_once(connection: psycopg.Connection, payload: Payload, worker_id: str) -> bool:
    """Insert ask message by unique trace id and return true only for first worker."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversation_messages(trace_id, uid, fingerprint, direction, value, worker_id, status)
            VALUES (%s, %s, %s, 'user', %s, %s, 'processing')
            ON CONFLICT (trace_id) DO NOTHING
            RETURNING id
            """,
            (
                get_payload_value(payload, "traceId", "missing-trace-id"),
                get_payload_value(payload, "uid", "home"),
                get_payload_value(payload, "fingerprint", "anonymous"),
                read_question_from_payload(payload),
                worker_id,
            ),
        )
        return cursor.fetchone() is not None


def update_conversation_message_answer(connection: psycopg.Connection, payload: Payload, answer: str) -> None:
    """Store worker answer for ask trace id."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversation_messages
            SET answer = %s, status = 'answered', updated_at = NOW()
            WHERE trace_id = %s
            """,
            (answer, get_payload_value(payload, "traceId", "missing-trace-id")),
        )
