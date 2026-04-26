import json
from google.cloud import pubsub_v1
from ..utils.payloads import Payload, get_payload_value


def publish_answer(
    publisher: pubsub_v1.PublisherClient,
    topic_path: str,
    payload: Payload,
    answer: str,
) -> None:
    """Publish worker answer to answer topic."""
    message = {
        "type": "answer",
        "uid": get_payload_value(payload, "uid", "home"),
        "traceId": get_payload_value(payload, "traceId", "missing-trace-id"),
        "fingerprint": get_payload_value(payload, "fingerprint", "anonymous"),
        "value": answer,
    }

    publisher.publish(topic_path, json.dumps(message).encode("utf-8")).result()
