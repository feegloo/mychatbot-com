import psycopg
from ..utils.payloads import Payload, get_payload_value


def mark_conversation_processing(connection: psycopg.Connection, payload: Payload) -> None:
    """Mark conversation as processing."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversations
            SET status = 'processing', updated_at = NOW()
            WHERE uid = %s
            """,
            (get_payload_value(payload, "uid", "missing-uid"),),
        )


def mark_conversation_done(connection: psycopg.Connection, payload: Payload) -> None:
    """Mark conversation as processed."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversations
            SET status = 'processed', updated_at = NOW()
            WHERE uid = %s
            """,
            (get_payload_value(payload, "uid", "missing-uid"),),
        )
