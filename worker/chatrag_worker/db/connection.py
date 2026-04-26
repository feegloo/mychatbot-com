import psycopg
from psycopg.rows import dict_row
from ..config import WorkerConfig


def create_database_connection(config: WorkerConfig) -> psycopg.Connection:
    """Open PostgreSQL connection used by locks, messages, and metadata logs."""
    if not config["database_url"]:
        raise RuntimeError("DATABASE_URL is required")

    return psycopg.connect(config["database_url"], autocommit=True, row_factory=dict_row)
