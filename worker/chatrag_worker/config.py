import os
from typing import TypedDict


class WorkerConfig(TypedDict):
    project_id: str
    subscription: str
    answer_topic: str
    worker_status: str
    database_url: str
    sentry_dsn: str
    sentry_environment: str
    sentry_release: str


def create_config() -> WorkerConfig:
    """Read worker runtime configuration from environment variables."""
    return {
        "project_id": os.environ.get("GCP_PROJECT_ID", ""),
        "subscription": os.environ.get("PUBSUB_SUBSCRIPTION", "chatrag-worker-sub"),
        "answer_topic": os.environ.get("PUBSUB_ANSWER_TOPIC", "chatrag-answer-topic"),
        "worker_status": os.environ.get("WORKER_STATUS", "processing"),
        "database_url": os.environ.get("DATABASE_URL", ""),
        "sentry_dsn": os.environ.get("SENTRY_DSN", ""),
        "sentry_environment": os.environ.get("SENTRY_ENVIRONMENT", "production"),
        "sentry_release": os.environ.get("SENTRY_RELEASE", "chatrag@local"),
    }
