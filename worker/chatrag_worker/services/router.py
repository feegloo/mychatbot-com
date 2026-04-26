import psycopg
from google.cloud import pubsub_v1
from ..config import WorkerConfig
from ..db.conversations import mark_conversation_done, mark_conversation_processing
from ..db.locks import acquire_processing_lock
from ..db.messages import insert_conversation_message_once, update_conversation_message_answer
from ..db.metadata import insert_conversation_metadata
from ..pubsub.publisher import publish_answer
from ..services.processor import process_ask, process_pdf
from ..utils.logger import log, now_iso
from ..utils.payloads import Payload, get_message_type


def route_message(
    config: WorkerConfig,
    connection: psycopg.Connection,
    publisher: pubsub_v1.PublisherClient,
    answer_topic_path: str,
    payload: Payload,
    worker_id: str,
) -> None:
    """Route one worker topic message by type."""
    if config["worker_status"].lower() == "idle":
        log("worker is idle, ignoring message", worker_id=worker_id, message_type=get_message_type(payload))
        insert_conversation_metadata(connection, payload, worker_id, "worker_idle_skip", "worker ignored message because it is idle", direction="in")
        return

    message_type = get_message_type(payload)

    if message_type == "ask":
        handle_ask_message(connection, publisher, answer_topic_path, payload, worker_id)
        return

    handle_pdf_message(connection, payload, worker_id)


def handle_pdf_message(connection: psycopg.Connection, payload: Payload, worker_id: str) -> None:
    """Process uploaded PDF only when DB lock is acquired."""
    insert_conversation_metadata(connection, payload, worker_id, "worker_topic_received", "worker received PDF message", direction="in")

    if not acquire_processing_lock(connection, payload, worker_id):
        insert_conversation_metadata(connection, payload, worker_id, "pdf_lock_conflict", "another worker owns PDF lock", direction="in")
        return

    insert_conversation_metadata(connection, payload, worker_id, "pdf_lock_acquired", "worker acquired PDF processing lock", direction="in")
    mark_conversation_processing(connection, payload)
    process_pdf(payload)
    mark_conversation_done(connection, payload)
    insert_conversation_metadata(connection, payload, worker_id, "pdf_processed", "worker completed PDF processing", direction="out")


def handle_ask_message(
    connection: psycopg.Connection,
    publisher: pubsub_v1.PublisherClient,
    answer_topic_path: str,
    payload: Payload,
    worker_id: str,
) -> None:
    """Process ask message once by unique trace id and publish answer."""
    insert_conversation_metadata(connection, payload, worker_id, "worker_topic_received", "worker received ask message", direction="in")

    if not insert_conversation_message_once(connection, payload, worker_id):
        insert_conversation_metadata(connection, payload, worker_id, "ask_duplicate_skipped", "worker skipped duplicate ask trace id", direction="in")
        return

    insert_conversation_metadata(connection, payload, worker_id, "ask_message_inserted", "worker inserted conversation_message row", direction="in")
    answer = f"{process_ask(payload)}, timestamp: {now_iso()}, fingerprint: {payload.get('fingerprint')}"
    update_conversation_message_answer(connection, payload, answer)
    publish_answer(publisher, answer_topic_path, payload, answer)
    insert_conversation_metadata(connection, payload, worker_id, "answer_topic_published", "worker published answer message", topic_name="answer", direction="out",)
