from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    # LLM provider: 'openai' (default) or 'ollama' (fully offline, no API key needed)
    llm_provider: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embedding_model: str
    # Vision model for OCR — must support image input (e.g. llava:7b, llava-llama3, moondream)
    ollama_vision_model: str
    # Optional local OCR integration (https://github.com/ahnafnafee/local-llm-pdf-ocr)
    local_pdf_ocr_enabled: bool
    local_pdf_ocr_command: str
    local_pdf_ocr_repo_path: str
    local_pdf_ocr_timeout_sec: int
    local_pdf_ocr_api_base: str
    local_pdf_ocr_model: str
    local_pdf_ocr_grounded: bool


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini"),
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
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_chat_model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b"),
        ollama_embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        ollama_vision_model=os.getenv("OLLAMA_VISION_MODEL", "llava:7b"),
        local_pdf_ocr_enabled=_env_bool("LOCAL_PDF_OCR_ENABLED", False),
        local_pdf_ocr_command=os.getenv("LOCAL_PDF_OCR_COMMAND", "").strip(),
        local_pdf_ocr_repo_path=os.getenv("LOCAL_PDF_OCR_REPO_PATH", "").strip(),
        local_pdf_ocr_timeout_sec=int(os.getenv("LOCAL_PDF_OCR_TIMEOUT_SEC", "180")),
        local_pdf_ocr_api_base=os.getenv("LOCAL_PDF_OCR_API_BASE", "").strip(),
        local_pdf_ocr_model=os.getenv("LOCAL_PDF_OCR_MODEL", "").strip(),
        local_pdf_ocr_grounded=_env_bool("LOCAL_PDF_OCR_GROUNDED", False),
    )

