from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    openai_api_key: str
    openai_chat_model: str
    openai_embedding_model: str
    chroma_mode: str
    chroma_http_host: str
    chroma_persist_dir: str
    chroma_api_key: str
    chroma_tenant: str
    chroma_database: str


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        chroma_mode=os.getenv("CHROMA_MODE", "local"),
        chroma_http_host=os.getenv("CHROMA_HTTP_HOST", "http://localhost:8000"),
        chroma_persist_dir=str(Path(os.getenv("CHROMA_PERSIST_DIR", "../data/chroma")).resolve()),
        chroma_api_key=os.getenv("CHROMA_API_KEY", ""),
        chroma_tenant=os.getenv("CHROMA_TENANT", ""),
        chroma_database=os.getenv("CHROMA_DATABASE", ""),
    )
