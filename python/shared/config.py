from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    llm_provider: str  # "openai" or "anthropic"
    openai_api_key: str
    openai_chat_model: str
    openai_embedding_model: str
    anthropic_api_key: str
    anthropic_chat_model: str
    chroma_mode: str
    chroma_http_host: str
    chroma_persist_dir: str
    openai_reasoning_effort: str
    chroma_api_key: str
    chroma_tenant: str
    chroma_database: str


def get_settings() -> Settings:
    llm_provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    
    # Auto-fallback: if no Anthropic key but OpenAI key exists, use OpenAI
    if not anthropic_key and openai_key and llm_provider == "anthropic":
        llm_provider = "openai"
    
    return Settings(
        llm_provider=llm_provider,
        openai_api_key=openai_key,
        # Model tiers (speed vs quality):
        #   Fast + cheap:  gpt-4.1-mini, gpt-4.1-nano, claude-3-5-haiku
        #   Balanced:      gpt-4.1, claude-3-7-sonnet
        #   Best quality:  o3, claude-3-7-sonnet (extended thinking)
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini"),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "low"),
        anthropic_api_key=anthropic_key,
        anthropic_chat_model=os.getenv("ANTHROPIC_CHAT_MODEL", "claude-3-5-haiku-20241022"),
        chroma_mode=os.getenv("CHROMA_MODE", "local"),
        chroma_http_host=os.getenv("CHROMA_HTTP_HOST", "http://localhost:8000"),
        chroma_persist_dir=str(Path(os.getenv("CHROMA_PERSIST_DIR", "../data/chroma")).resolve()),
        chroma_api_key=os.getenv("CHROMA_API_KEY", ""),
        chroma_tenant=os.getenv("CHROMA_TENANT", ""),
        chroma_database=os.getenv("CHROMA_DATABASE", ""),
    )
