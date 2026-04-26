from google.cloud import pubsub_v1
from .config import create_config
from .db.connection import create_database_connection
from .db.metadata import insert_conversation_metadata
from .pubsub.client import create_publisher, create_subscriber
from .sentry import capture_debug, init_sentry
from .services.router import route_message
from .utils.identity import get_worker_id_from_gcp
from .utils.logger import log
from .utils.payloads import decode_json


def main() -> None:
    """Start Pub/Sub pull worker and block forever."""
    config = create_config()
    init_sentry(config)

    worker_id = get_worker_id_from_gcp()
    connection = create_database_connection(config)
    subscriber, subscription_path = create_subscriber(config)
    publisher, answer_topic_path = create_publisher(config)

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        """Handle one Pub/Sub message and ACK/NACK it."""
        try:
            payload = decode_json(message.data)
            insert_conversation_metadata(connection, payload, worker_id, "pubsub_message_received", "worker pulled message from worker subscription", topic_name=config["subscription"], direction="in")
            route_message(config, connection, publisher, answer_topic_path, payload, worker_id)
            message.ack()
        except Exception as error:
            capture_debug("worker message failed", error=str(error))
            message.nack()

    log("worker started", worker_id=worker_id, subscription=subscription_path)
    future = subscriber.subscribe(subscription_path, callback=callback)
    future.result()


if __name__ == "__main__":
    main()
