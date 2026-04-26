from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def log(message: str, **values: Any) -> None:
    """Print one structured log line for Cloud Logging."""
    details = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"{now_iso()} {message} {details}".strip(), flush=True)
