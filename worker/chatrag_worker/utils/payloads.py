import json
from typing import Any

Payload = dict[str, Any]


def decode_json(data: bytes) -> Payload:
    """Decode Pub/Sub bytes payload into dictionary."""
    return json.loads(data.decode("utf-8"))


def get_payload_value(payload: Payload, key: str, fallback: str) -> str:
    """Read string value from Pub/Sub payload with fallback."""
    value = payload.get(key)
    return str(value) if value else fallback


def get_message_type(payload: Payload) -> str:
    """Return message type used by worker router."""
    return str(payload.get("type") or "process_pdf")


def read_question_from_payload(payload: Payload) -> str:
    """Extract question from ask message JSON string value."""
    value = payload.get("value")

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return str(parsed.get("question") or "")
        except json.JSONDecodeError:
            return value

    if isinstance(value, dict):
        return str(value.get("question") or "")

    return ""
