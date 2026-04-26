from __future__ import annotations

import errno
import logging
import sys


class NonBlockingSafeStreamHandler(logging.StreamHandler):
    """Stream handler that drops EAGAIN/EWOULDBLOCK writes.

    Cloud Run and containerized runtimes can occasionally expose stdout/stderr
    in a non-blocking mode. When the stream backpressure spikes, Python's
    logging emit can raise BlockingIOError. Dropping only those transient writes
    is safer than allowing an exception to bubble from logging internals.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return
            raise


def configure_safe_logging(level: int = logging.INFO) -> None:
    """Configure root logging with a handler tolerant to non-blocking streams."""
    root = logging.getLogger()
    if getattr(root, "_chatrag_safe_logging_configured", False):
        return

    handler = NonBlockingSafeStreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Chroma can emit noisy posthog telemetry errors in some dependency mixes.
    # This logger is non-critical for app behavior; keep it quiet in runtime logs.
    chroma_telemetry_logger = logging.getLogger("chromadb.telemetry.product.posthog")
    chroma_telemetry_logger.setLevel(logging.CRITICAL)
    chroma_telemetry_logger.propagate = False

    root._chatrag_safe_logging_configured = True
