from google.cloud import pubsub_v1
from ..config import WorkerConfig


def create_subscriber(config: WorkerConfig) -> tuple[pubsub_v1.SubscriberClient, str]:
    """Create Pub/Sub subscriber and subscription path."""
    subscriber = pubsub_v1.SubscriberClient()
    path = subscriber.subscription_path(config["project_id"], config["subscription"])
    return subscriber, path


def create_publisher(config: WorkerConfig) -> tuple[pubsub_v1.PublisherClient, str]:
    """Create Pub/Sub publisher and answer topic path."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(config["project_id"], config["answer_topic"])
    return publisher, topic_path
