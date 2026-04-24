from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    openai_api_key: str
    openai_chat_model: str
    openai_embedding_model: str
    openai_image_model: str
    chroma_mode: str
    chroma_http_host: str
    chroma_persist_dir: str
    openai_reasoning_effort: str
    chroma_api_key: str
    chroma_tenant: str
    chroma_database: str
    # Database for telemetry
    database_url: str


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4"),
        # Keep gpt-image-2 as default because progressive partial frames
        # (used by UI morph effect) are implemented on its streaming path.
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "low"),
        chroma_mode=os.getenv("CHROMA_MODE", "local"),
        chroma_http_host=os.getenv("CHROMA_HTTP_HOST", "http://localhost:8000"),
        chroma_persist_dir=str(Path(os.getenv("CHROMA_PERSIST_DIR", "../data/chroma")).resolve()),
        chroma_api_key=os.getenv("CHROMA_API_KEY", ""),
        chroma_tenant=os.getenv("CHROMA_TENANT", ""),
        chroma_database=os.getenv("CHROMA_DATABASE", ""),
        database_url=os.getenv("DATABASE_URL", "postgres://chatrag:chatrag@localhost:5432/chatrag"),
    )

