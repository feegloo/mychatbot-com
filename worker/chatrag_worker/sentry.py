import sentry_sdk
from .config import WorkerConfig


def init_sentry(config: WorkerConfig) -> None:
    """Initialize Sentry worker SDK when DSN is configured."""
    if not config["sentry_dsn"]:
        return

    sentry_sdk.init(
        dsn=config["sentry_dsn"],
        environment=config["sentry_environment"],
        release=config["sentry_release"],
        traces_sample_rate=1.0,
        debug=True,
    )


def capture_debug(message: str, **extra: object) -> None:
    """Send worker debug message to Sentry."""
    sentry_sdk.set_context("debug", extra)
    sentry_sdk.capture_message(message, level="debug")
