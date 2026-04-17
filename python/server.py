"""Persistent FastAPI server for the RAG pipeline.

Keeps heavy imports (langchain, chromadb, openai) loaded in memory
so answering questions doesn't pay the ~20s import cost each time.
"""
from __future__ import annotations

import json
import logging
import asyncio
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.rag import answer_with_citations
from shared.indexing import index_documents
from shared.vector_store import collection_count
from shared.metadata import enrich_metadata_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ChatRAG Server")


@app.on_event("startup")
async def _startup_checks():
    """Log configuration and verify Ollama connectivity when USE_GEMMA is enabled."""
    from shared.config import get_settings
    settings = get_settings()
    if settings.use_gemma:
        logger.info(f"🟢 Gemma mode ENABLED — model={settings.gemma_model} url={settings.gemma_base_url}")
        try:
            import urllib.request
            req = urllib.request.Request(f"{settings.gemma_base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                import json as _json
                data = _json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
            if models:
                logger.info(f"🟢 Ollama available. Loaded models: {models}")
            else:
                logger.warning(f"⚠️ Ollama is running but has no models. Pull one: docker exec chatrag-ollama ollama pull {settings.gemma_model}")
        except Exception as e:
            logger.warning(f"⚠️ Cannot reach Ollama at {settings.gemma_base_url}: {e}. Make sure Ollama is running.")
    else:
        logger.info(f"🔵 Using cloud LLM provider: {settings.llm_provider}")


class AnswerRequest(BaseModel):
    conversation_id: str
    collection_name: str
    question: str
    chat_history: list[dict] | None = None
    welcome_messages: list[str] | None = None
    image_file_paths: list[str] | None = None
    file_metadata: dict[str, dict] | None = None


class IndexRequest(BaseModel):
    conversation_id: str
    collection_name: str
    file_paths: list[str]


class EnrichMetadataRequest(BaseModel):
    file_paths: list[str]
    exif_metadata: dict[str, dict] | None = None
    welcome_message: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/collection-count/{collection_name}")
async def get_collection_count(collection_name: str):
    count = collection_count(collection_name)
    return {"collection_name": collection_name, "count": count}


@app.post("/index")
async def index(req: IndexRequest):
    try:
        result = await asyncio.to_thread(
            index_documents,
            conversation_id=req.conversation_id,
            collection_name=req.collection_name,
            file_paths=req.file_paths,
        )
        return result
    except Exception as e:
        logger.exception("Error indexing documents")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/answer")
async def answer(req: AnswerRequest):
    try:
        logger.info(
            f"📥 /answer request: question='{req.question[:100]}' "
            f"image_file_paths={req.image_file_paths} "
            f"file_metadata_keys={list(req.file_metadata.keys()) if req.file_metadata else None} "
            f"welcome_messages_count={len(req.welcome_messages) if req.welcome_messages else 0}"
        )
        result = await asyncio.to_thread(
            answer_with_citations,
            collection_name=req.collection_name,
            conversation_id=req.conversation_id,
            question=req.question,
            chat_history=req.chat_history,
            welcome_messages=req.welcome_messages,
            image_file_paths=req.image_file_paths,
            file_metadata=req.file_metadata,
        )
        answer_preview = (result.get("answer", "") or "")[:200]
        logger.info(f"📤 /answer response: {len(result.get('answer', ''))} chars, preview='{answer_preview}'")
        return result
    except Exception as e:
        logger.exception("Error answering question")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/enrich-metadata")
async def enrich_metadata(req: EnrichMetadataRequest):
    """Run async web detection (Google Vision) for image files.
    
    Fire-and-forget: caller doesn't need to wait for this.
    Returns enriched metadata dict {filename: {web_detection, identified_name, ...}}.
    """
    try:
        result = await asyncio.to_thread(
            enrich_metadata_web,
            req.file_paths,
            exif_metadata=req.exif_metadata,
            welcome_message=req.welcome_message,
        )
        return result
    except Exception as e:
        logger.warning(f"Metadata enrichment failed (non-fatal): {e}")
        return {}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8321)
