import os
import socket


def get_worker_id_from_gcp() -> str:
    """Build worker id from Cloud Run environment and container hostname."""
    service = os.environ.get("K_SERVICE") or "local-worker"
    revision = os.environ.get("K_REVISION") or "local-revision"
    hostname = os.environ.get("HOSTNAME") or socket.gethostname()
    return f"{service}:{revision}:{hostname}"
