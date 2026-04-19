"""Persistent FastAPI server for the RAG pipeline.

Keeps heavy imports (langchain, chromadb, openai) loaded in memory
so answering questions doesn't pay the ~20s import cost each time.
"""
from __future__ import annotations

import json
import logging
import asyncio
import os
import urllib.error
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sentry_sdk

def _before_send_log(log, _hint):
    if os.getenv("SENTRY_ENVIRONMENT", "dev") == "prod" and log["severity_text"] == "debug":
        return None
    return log

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("SENTRY_ENVIRONMENT", "dev"),
    send_default_pii=True,
    traces_sample_rate=1.0,
    max_value_length=8192,
    enable_logs=True,
    before_send_log=_before_send_log,
)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentry_sdk import logger as sentry_logger

from shared.rag import answer_with_citations
from shared.indexing import index_documents
from shared.vector_store import collection_count
from shared.metadata import enrich_metadata_web
from shared.image_gen import generate_image, build_image_prompt
from shared.telemetry import close_db_pool
from shared.url_fetch import fetch_url, describe_url, _extract_visible_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ChatRAG Server")


@app.on_event("shutdown")
async def _shutdown():
    """Clean up DB connection pool on shutdown."""
    close_db_pool()


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
    storage_dir: str | None = None
    previous_suggested_questions: list[str] | None = None
    conversation_name: str | None = None


class IndexRequest(BaseModel):
    conversation_id: str
    collection_name: str
    file_paths: list[str]


class EnrichMetadataRequest(BaseModel):
    file_paths: list[str]
    exif_metadata: dict[str, dict] | None = None
    welcome_message: str = ""


class DescribeUrlRequest(BaseModel):
    url: str
    conversation_id: str
    collection_name: str


class GenerateImageRequest(BaseModel):
    question: str
    storage_dir: str
    context: str = ""
    welcome_messages: list[str] | None = None
    size: str = "1024x1024"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/processing-jobs/{conversation_id}")
async def get_processing_jobs(conversation_id: str):
    """Get processing telemetry for a conversation (live progress view)."""
    try:
        from shared.telemetry import _get_db_pool
        pool = _get_db_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, file_name, page_number, total_pages,
                              status, step, detail, error_message, retry_count,
                              duration_ms, worker_id, started_at, completed_at, created_at
                       FROM processing_jobs
                       WHERE conversation_id = %s
                       ORDER BY created_at ASC""",
                    (conversation_id,),
                )
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
                # Convert datetime objects to ISO strings
                for row in rows:
                    for key in ("started_at", "completed_at", "created_at"):
                        if row.get(key):
                            row[key] = row[key].isoformat()
                    if row.get("id"):
                        row["id"] = str(row["id"])
                return {"conversation_id": conversation_id, "jobs": rows, "total": len(rows)}
        finally:
            pool.putconn(conn)
    except Exception as e:
        logger.warning(f"Failed to fetch processing jobs: {e}")
        return {"conversation_id": conversation_id, "jobs": [], "error": str(e)}


@app.get("/collection-count/{collection_name}")
async def get_collection_count(collection_name: str):
    count = collection_count(collection_name)
    return {"collection_name": collection_name, "count": count}


@app.post("/index")
async def index(req: IndexRequest):
    try:
        sentry_logger.info(
            "Indexing documents for conversation {conversation_id}",
            conversation_id=req.conversation_id,
            collection_name=req.collection_name,
            file_count=len(req.file_paths),
        )
        result = await asyncio.to_thread(
            index_documents,
            conversation_id=req.conversation_id,
            collection_name=req.collection_name,
            file_paths=req.file_paths,
        )
        sentry_logger.info(
            "Indexing completed for conversation {conversation_id}",
            conversation_id=req.conversation_id,
        )
        return result
    except Exception as e:
        sentry_logger.error(
            "Indexing failed for conversation {conversation_id}",
            conversation_id=req.conversation_id,
            attributes={"error": str(e)[:500]},
        )
        logger.exception("Error indexing documents")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/answer")
async def answer(req: AnswerRequest):
    try:
        sentry_logger.info(
            "Answering question for conversation {conversation_id}",
            conversation_id=req.conversation_id,
            attributes={
                "question_length": len(req.question),
                "has_image_files": bool(req.image_file_paths),
                "welcome_messages_count": len(req.welcome_messages) if req.welcome_messages else 0,
                "collection_name": req.collection_name,
            },
        )
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
            storage_dir=req.storage_dir,
            previous_suggested_questions=req.previous_suggested_questions,
            conversation_name=req.conversation_name,
        )
        answer_preview = (result.get("answer", "") or "")[:200]
        logger.info(f"📤 /answer response: {len(result.get('answer', ''))} chars, preview='{answer_preview}'")
        sentry_logger.info(
            "Answer generated for conversation {conversation_id}",
            conversation_id=req.conversation_id,
            attributes={
                "answer_length": len(result.get("answer", "")),
                "citation_count": len(result.get("citations", [])),
            },
        )
        return result
    except Exception as e:
        sentry_logger.error(
            "Answer failed for conversation {conversation_id}",
            conversation_id=req.conversation_id,
            attributes={"error": str(e)[:500]},
        )
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


@app.post("/describe-url")
async def describe_url_endpoint(req: DescribeUrlRequest):
    """Fetch a web page and describe its content using the LLM.

    Also indexes the page text into the vector store so the user can
    ask follow-up questions about the website content.
    """
    try:
        def _process_url():
            from shared.chunkers import split_into_chunks, Chunk
            from shared.vector_store import upsert_chunks
            from shared.lang_detect import detect_language
            from shared.suggested_questions import suggest_questions_from_chunks

            # 1. Fetch HTML
            logger.info(f"🌐 Fetching URL: {req.url}")
            html = fetch_url(req.url)
            logger.info(f"🌐 Fetched {len(html)} chars of HTML from {req.url}")

            # 2. Extract visible text for indexing
            visible_text = _extract_visible_text(html)
            detected_language = detect_language(visible_text[:2000])

            # 3. Generate description
            logger.info(f"📝 Generating URL description...")
            welcome_message = describe_url(req.url, html, language=detected_language)

            # 4. Chunk the visible text and index into vector store
            chunks = split_into_chunks(
                text=visible_text,
                file_name=req.url,
            )
            logger.info(f"📦 Indexing {len(chunks)} chunks from URL content...")
            upsert_result = upsert_chunks(
                collection_name=req.collection_name,
                conversation_id=req.conversation_id,
                chunks=chunks,
            )

            # 5. Generate suggested questions
            chunk_texts = [c.text for c in chunks]
            suggested_questions = suggest_questions_from_chunks(
                chunk_texts,
                language=detected_language,
                description=welcome_message,
                file_names=[req.url],
                file_types={req.url: "webpage"},
                welcome_message=welcome_message,
            )

            return {
                "welcome_message": welcome_message,
                "suggested_questions": suggested_questions,
                "detected_language": detected_language,
                "chunk_count": len(chunks),
                "html_length": len(html),
                "url": req.url,
                **upsert_result,
            }

        result = await asyncio.to_thread(_process_url)
        return result
    except urllib.error.URLError as e:
        logger.exception(f"Failed to fetch URL: {req.url}")
        raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e.reason}")
    except Exception as e:
        logger.exception(f"Error describing URL: {req.url}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-image")
async def generate_image_endpoint(req: GenerateImageRequest):
    """Generate an image from a text prompt using DALL-E.

    1. Builds a visual prompt from the user's question + context
    2. Calls OpenAI image generation API
    3. Saves the image to the conversation's storage directory
    4. Returns the file name (served via /api/storage/)
    """
    try:
        def _generate():
            # Build a detailed visual prompt from the user's request + context
            image_prompt = build_image_prompt(
                question=req.question,
                context=req.context,
                welcome_messages=req.welcome_messages,
            )
            logger.info(f"🎨 Image prompt: {image_prompt[:150]}...")

            # Generate and save the image
            result = generate_image(
                prompt=image_prompt,
                storage_dir=req.storage_dir,
                size=req.size,
            )
            result["image_prompt"] = image_prompt
            return result

        result = await asyncio.to_thread(_generate)
        return result
    except Exception as e:
        logger.exception("Error generating image")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8321)
