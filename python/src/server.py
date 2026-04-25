"""Persistent FastAPI server for the RAG pipeline.

Keeps heavy imports (langchain, chromadb, openai) loaded in memory
so answering questions doesn't pay the ~20s import cost each time.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import urllib.error
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import sentry_sdk  # noqa: E402


def _before_send_log(log, _hint):
    if os.getenv("SENTRY_ENVIRONMENT", "dev") == "prod" and log["severity_text"] == "debug":
        return None
    return log


def _before_send(event, hint):
    if "ClientCreateCollectionEvent" in event.get("logentry", {}).get("message", ""):
        return None
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_str = str(exc_info[1])
        if "ClientCreateCollectionEvent" in exc_str:
            return None
        # Drop OpenTelemetry exporter noise (OTLP collector not reachable in Cloud Run)
        module = getattr(exc_info[0], "__module__", "") or ""
        if module.startswith("opentelemetry") or "opentelemetry" in exc_str.lower():
            return None
        if "ECONNREFUSED" in exc_str and ":4318" in exc_str:
            return None
    # Also scan stack frames for opentelemetry origin
    for values in event.get("exception", {}).get("values", []) or []:
        for frame in (values.get("stacktrace") or {}).get("frames", []) or []:
            if "opentelemetry" in (frame.get("module") or "") or "opentelemetry" in (frame.get("filename") or ""):
                return None
    return event


sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("SENTRY_ENVIRONMENT", "dev"),
    send_default_pii=True,
    traces_sample_rate=1.0,
    max_value_length=8192,
    enable_logs=True,
    before_send=_before_send,
    before_send_log=_before_send_log,
)

# Initialize OpenTelemetry (before FastAPI import so auto-instrumentation hooks in)
from shared.otel import init_otel  # noqa: E402

init_otel()

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sentry_sdk import logger as sentry_logger  # noqa: E402

from shared.image_gen import (  # noqa: E402
    build_image_announcement,
    build_image_prompt,
    generate_image,
    generate_image_streaming,
)
from shared.indexing import index_documents  # noqa: E402
from shared.metadata import enrich_metadata_web  # noqa: E402
from shared.music_gen import build_music_prompt, generate_music  # noqa: E402
from shared.rag import answer_with_citations  # noqa: E402
from shared.telemetry import close_db_pool  # noqa: E402
from shared.url_fetch import _extract_visible_text, describe_url, fetch_url  # noqa: E402
from shared.vector_store import collection_count, query_chunks  # noqa: E402
from shared.video_gen import build_video_prompt, generate_video  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handlers."""
    from shared.config import get_settings

    settings = get_settings()
    logger.info(f"🔵 Using OpenAI model: {settings.openai_chat_model}")
    yield
    close_db_pool()


app = FastAPI(title="ChatRAG Server", lifespan=_lifespan)


@app.middleware("http")
async def _request_id_middleware(request, call_next):
    """Bind incoming X-Request-Id to Sentry tag + log context so the same
    identifier can be grepped across browser → backend → python logs and
    is visible in the Sentry trace.
    """
    request_id = request.headers.get("x-request-id") or ""
    trace_id = request.headers.get("x-trace-id") or ""
    with sentry_sdk.new_scope() as scope:
        if request_id:
            scope.set_tag("request_id", request_id)
        if trace_id:
            scope.set_tag("trace_id", trace_id)
            sentry_logger.debug(
                "Python server accepted traced request",
                attributes={
                    "trace_id": trace_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
        logger.info(
            f"▶️  {request.method} {request.url.path} "
            f"| request_id={request_id} trace_id={trace_id}"
        )
        response = await call_next(request)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response


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
    trace_id: str | None = None


class EnrichMetadataRequest(BaseModel):
    file_paths: list[str]
    exif_metadata: dict[str, dict] | None = None
    welcome_message: str = ""


class DescribeUrlRequest(BaseModel):
    url: str
    conversation_id: str
    collection_name: str
    trace_id: str | None = None


class GenerateImageRequest(BaseModel):
    question: str
    storage_dir: str
    context: str = ""
    welcome_messages: list[str] | None = None
    collection_name: str = ""
    conversation_id: str = ""
    chat_history: list[dict] | None = None
    size: str = "880x880"
    # size: str = "880x880"
    quality: Literal["auto", "high", "low"] = "low"
    # Absolute paths to reference images the model should condition on
    # (routed through OpenAI's images.edit endpoint). Optional.
    reference_image_paths: list[str] | None = None


class AnnounceImageRequest(BaseModel):
    question: str
    welcome_messages: list[str] | None = None
    chat_history: list[dict] | None = None


class RegisterImageRequest(BaseModel):
    image_id: str
    description: str
    conversation_id: str
    storage_namespace: str
    file_name: str
    image_title: str | None = None
    image_prompt: str | None = None
    user_prompt: str | None = None
    source_original_names: list[str] | None = None


class ReusableImageRequest(BaseModel):
    query_text: str
    exclude_conversation_id: str | None = None
    preferred_source_files: list[str] | None = None
    max_distance: float | None = None


class GenerateVideoRequest(BaseModel):
    question: str
    storage_dir: str
    welcome_messages: list[str] | None = None
    collection_name: str = ""
    conversation_id: str = ""
    chat_history: list[dict] | None = None
    duration_seconds: int | None = None


class GenerateMusicRequest(BaseModel):
    question: str
    storage_dir: str
    welcome_messages: list[str] | None = None
    collection_name: str = ""
    conversation_id: str = ""
    chat_history: list[dict] | None = None
    duration_seconds: int | None = None


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
                rows = [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]
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
        if req.trace_id:
            sentry_sdk.set_tag("trace_id", req.trace_id)
        sentry_logger.info(
            "Indexing documents for conversation {conversation_id}",
            conversation_id=req.conversation_id,
            collection_name=req.collection_name,
            file_count=len(req.file_paths),
            attributes={"trace_id": req.trace_id or ""},
        )
        with sentry_sdk.start_span(
            name="python.index_documents",
            op="task.index",
            attributes={
                "conversation_id": req.conversation_id,
                "chatrag.trace_id": req.trace_id or "",
            },
        ):
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/index-stream")
async def index_stream(req: IndexRequest):
    """Streaming variant of /index that emits NDJSON events as indexing progresses.

    Events:
      {"event": "welcome_message", "data": {...}}  – welcome message ready
      {"event": "complete", "data": {...}}          – indexing finished
      {"event": "error", "data": {"error": "..."}}  – fatal error
    """
    from fastapi.responses import StreamingResponse  # noqa: E402

    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_progress(event_type: str, data: dict) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, {"event": event_type, "data": data})

    async def generate():
        task = asyncio.ensure_future(
            asyncio.to_thread(
                index_documents,
                conversation_id=req.conversation_id,
                collection_name=req.collection_name,
                file_paths=req.file_paths,
                on_progress=on_progress,
            )
        )

        try:
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=60.0)
                    yield json.dumps(item, ensure_ascii=False, default=str) + "\n"
                    if item["event"] in ("complete", "error"):
                        break
                except TimeoutError:
                    if task.done():
                        exc = task.exception()
                        if exc:
                            yield json.dumps(
                                {"event": "error", "data": {"error": str(exc)}}
                            ) + "\n"
                        break
                    yield "\n"  # keepalive
        except Exception as e:
            yield json.dumps({"event": "error", "data": {"error": str(e)}}) + "\n"

        if not task.done():
            with contextlib.suppress(Exception):
                await task

    sentry_logger.info(
        "Streaming index for conversation {conversation_id}",
        conversation_id=req.conversation_id,
        attributes={"trace_id": req.trace_id or ""},
    )

    return StreamingResponse(generate(), media_type="application/x-ndjson")


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
        logger.info(
            f"📤 /answer response: "
            f"{len(result.get('answer', ''))} chars, "
            f"preview='{answer_preview}'"
        )
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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        if req.trace_id:
            sentry_sdk.set_tag("trace_id", req.trace_id)

        def _process_url():
            from shared.chunkers import split_into_chunks
            from shared.lang_detect import detect_language
            from shared.suggested_questions import suggest_questions_from_chunks
            from shared.vector_store import upsert_chunks

            # 1. Fetch HTML
            logger.info(f"🌐 Fetching URL: {req.url}")
            html = fetch_url(req.url)
            logger.info(f"🌐 Fetched {len(html)} chars of HTML from {req.url}")

            # 2. Extract visible text for indexing
            visible_text = _extract_visible_text(html)
            detected_language = detect_language(visible_text[:2000])

            # 3. Generate description
            logger.info("📝 Generating URL description...")
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
        raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e.reason}") from e
    except Exception as e:
        logger.exception(f"Error describing URL: {req.url}")
        raise HTTPException(status_code=500, detail=str(e)) from e


def _discover_uploaded_reference_files(storage_dir: str) -> list[str]:
    """Pick uploaded PDFs from ``storage_dir`` to use as reference images.

    When the caller does not specify explicit reference images, we attach
    the cover (first page) of any uploaded PDF so the image generator can
    visually ground the result in the source document. Previously generated
    images (``generated-*.png``, ``generated-*.jpg``, ``generated-*.webp``) and rendered cover caches (``*.cover.png``)
    are excluded. Capped at ``MAX_REFERENCE_IMAGES``.
    """
    from pathlib import Path as _Path

    from shared.image_gen import MAX_REFERENCE_IMAGES

    base = _Path(storage_dir)
    if not base.is_dir():
        return []
    pdfs = sorted(
        p for p in base.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )
    return [str(p) for p in pdfs[:MAX_REFERENCE_IMAGES]]


@app.post("/announce-image")
async def announce_image_endpoint(req: AnnounceImageRequest):
    """Fast single-LLM call returning a one-sentence teaser describing the
    image about to be generated. Used by the frontend to replace the
    generic "Generating image, please wait…" label while the real
    /generate-image call runs in parallel.
    """
    try:
        announcement = await asyncio.to_thread(
            build_image_announcement,
            req.question,
            req.welcome_messages,
            req.chat_history,
        )
        return {"announcement": announcement}
    except Exception as e:
        logger.exception("Error building image announcement")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/generate-image")
async def generate_image_endpoint(req: GenerateImageRequest):
    """Generate an image from a text prompt using DALL-E.

    1. Queries top-10 RAG chunks matching the user's request for grounding
    2. Builds a visual prompt from question + chunks + conversation history
    3. Calls OpenAI image generation API
    4. Saves the image and returns file name + source chunk references
    """
    try:

        def _generate():
            # If no explicit references were passed and the conversation has
            # uploaded PDFs, use their first page (book cover) as a visual
            # anchor for the generated image.
            reference_image_paths = req.reference_image_paths
            if not reference_image_paths:
                reference_image_paths = _discover_uploaded_reference_files(req.storage_dir)
                if reference_image_paths:
                    logger.info(
                        f"📎 Auto-attaching {len(reference_image_paths)} uploaded PDF(s) "
                        "as image-gen references"
                    )
            # Retrieve top-10 document chunks relevant to the image request
            rag_chunks: list[dict] = []
            if req.collection_name and req.conversation_id:
                try:
                    rag_chunks = query_chunks(
                        collection_name=req.collection_name,
                        conversation_id=req.conversation_id,
                        question=req.question,
                        top_k=10,
                    )
                    logger.info(f"🔍 Retrieved {len(rag_chunks)} RAG chunks for image generation")
                except Exception as exc:
                    logger.warning(f"⚠️ Could not query RAG chunks for image: {exc}")

            # Build a detailed visual prompt grounded in the retrieved sources
            prompt_result = build_image_prompt(
                question=req.question,
                context=req.context,
                welcome_messages=req.welcome_messages,
                rag_chunks=rag_chunks if rag_chunks else None,
                chat_history=req.chat_history,
            )
            image_prompt = prompt_result["prompt"]
            image_title = prompt_result["title"]
            source_indices = prompt_result.get("source_indices", [])
            image_size = req.size or "880x880"
            logger.info(f"🎨 Image prompt: {image_prompt[:150]}... (sources: {source_indices}, size: {image_size})")

            # Generate and save the image
            result = generate_image(
                prompt=image_prompt,
                storage_dir=req.storage_dir,
                size=image_size,
                quality=req.quality,
                reference_image_paths=reference_image_paths,
            )
            result["image_prompt"] = image_prompt
            result["image_title"] = image_title

            # Resolve which chunks were cited by the model
            cited_sources = [
                rag_chunks[i]
                for i in source_indices
                if isinstance(i, int) and 0 <= i < len(rag_chunks)
            ]
            result["rag_sources"] = cited_sources
            return result

        result = await asyncio.to_thread(_generate)
        return result
    except Exception as e:
        logger.exception("Error generating image")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/generate-image-stream")
async def generate_image_stream_endpoint(req: GenerateImageRequest):
    """Streaming variant of /generate-image.

    Emits NDJSON events so the UI can show progressive "morphing" frames
    before the final image is ready:
      {"event": "prompt_ready", "data": {"image_prompt": ..., "image_title": ...}}
      {"event": "partial",      "data": {"b64": "...", "index": 0}}
      {"event": "complete",     "data": {file_name, revised_prompt, image_prompt, image_title, rag_sources}}
      {"event": "error",        "data": {"error": "..."}}
    """
    from fastapi.responses import StreamingResponse  # noqa: E402

    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    def _emit(event: str, data: dict) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, {"event": event, "data": data})

    def _run() -> dict:
        # Keep the streaming path on pure text-to-image unless the caller
        # explicitly selected reference images. Auto-attaching uploaded PDFs
        # pushes generation into the edit/reference branch, which often
        # suppresses progressive partial frames and breaks the morph UI.
        reference_image_paths = req.reference_image_paths

        rag_chunks: list[dict] = []
        if req.collection_name and req.conversation_id:
            try:
                rag_chunks = query_chunks(
                    collection_name=req.collection_name,
                    conversation_id=req.conversation_id,
                    question=req.question,
                    top_k=10,
                )
            except Exception as exc:
                logger.warning(f"⚠️ Could not query RAG chunks (stream): {exc}")

        prompt_result = build_image_prompt(
            question=req.question,
            context=req.context,
            welcome_messages=req.welcome_messages,
            rag_chunks=rag_chunks if rag_chunks else None,
            chat_history=req.chat_history,
        )
        image_prompt = prompt_result["prompt"]
        image_title = prompt_result["title"]
        source_indices = prompt_result.get("source_indices", [])
        image_size = req.size or "880x880"

        _emit("prompt_ready", {"image_prompt": image_prompt, "image_title": image_title})

        final: dict | None = None
        partial_count = 0
        for item in generate_image_streaming(
            prompt=image_prompt,
            storage_dir=req.storage_dir,
            size=image_size,
            quality=req.quality,
            reference_image_paths=reference_image_paths,
        ):
            if item["type"] == "partial":
                partial_count += 1
                logger.info(f"✅ Endpoint emitting partial #{partial_count} (index={item['index']})")
                _emit("partial", {"b64": item["b64"], "index": item["index"]})
            elif item["type"] == "completed":
                logger.info("✅ Endpoint emitting completion event")
                final = item

        if not final:
            raise RuntimeError("Streaming generator yielded no completion event")

        cited_sources = [
            rag_chunks[i]
            for i in source_indices
            if isinstance(i, int) and 0 <= i < len(rag_chunks)
        ]
        return {
            "file_name": final["file_name"],
            "revised_prompt": final["revised_prompt"],
            "image_prompt": image_prompt,
            "image_title": image_title,
            "rag_sources": cited_sources,
        }

    async def generator():
        task = asyncio.ensure_future(asyncio.to_thread(_run))
        try:
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=60.0)
                    yield json.dumps(item, ensure_ascii=False, default=str) + "\n"
                except TimeoutError:
                    if task.done():
                        break
                    yield "\n"  # keepalive
                if task.done() and event_queue.empty():
                    break
            exc = task.exception()
            if exc:
                yield json.dumps({"event": "error", "data": {"error": str(exc)}}) + "\n"
            else:
                yield json.dumps({"event": "complete", "data": task.result()}, ensure_ascii=False, default=str) + "\n"
        except Exception as e:
            logger.exception("Error in generate-image-stream generator")
            yield json.dumps({"event": "error", "data": {"error": str(e)}}) + "\n"
            if not task.done():
                with contextlib.suppress(Exception):
                    await task

    return StreamingResponse(generator(), media_type="application/x-ndjson")


@app.post("/register-image")
async def register_image_endpoint(req: RegisterImageRequest):
    """Index a generated image's description into the cross-conversation
    reusable-images collection so future answers can semantically match it."""
    from shared.reusable_images import register_image

    try:
        await asyncio.to_thread(
            register_image,
            image_id=req.image_id,
            description=req.description,
            conversation_id=req.conversation_id,
            storage_namespace=req.storage_namespace,
            file_name=req.file_name,
            image_title=req.image_title,
            image_prompt=req.image_prompt,
            user_prompt=req.user_prompt,
            source_original_names=req.source_original_names,
        )
        return {"ok": True}
    except Exception as e:
        logger.exception("Error registering image")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/reusable-image")
async def reusable_image_endpoint(req: ReusableImageRequest):
    """Look up the best-matching previously generated image (if any) for the
    given query text. Returns ``{match: null}`` when nothing crosses the
    similarity threshold so callers can fall through to fresh generation."""
    from shared.reusable_images import DEFAULT_MAX_DISTANCE, find_reusable_image

    try:
        match = await asyncio.to_thread(
            find_reusable_image,
            query_text=req.query_text,
            exclude_conversation_id=req.exclude_conversation_id,
            preferred_source_files=req.preferred_source_files,
            max_distance=req.max_distance if req.max_distance is not None else DEFAULT_MAX_DISTANCE,
        )
        return {"match": match}
    except Exception as e:
        logger.exception("Error querying reusable image")
        raise HTTPException(status_code=500, detail=str(e)) from e


def _gather_av_context(
    collection_name: str, conversation_id: str, question: str
) -> list[dict]:
    """Helper shared by /generate-video and /generate-music to retrieve
    RAG chunks so generated clips are grounded in the documents."""
    if not (collection_name and conversation_id):
        return []
    try:
        return query_chunks(
            collection_name=collection_name,
            conversation_id=conversation_id,
            question=question,
            top_k=8,
        )
    except Exception as exc:  # pragma: no cover — logged and continues
        logger.warning(f"⚠️ Could not query RAG chunks for AV generation: {exc}")
        return []


@app.post("/generate-video")
async def generate_video_endpoint(req: GenerateVideoRequest):
    """Generate a short video from a text prompt using Replicate (LTX-Video).

    1. Retrieves RAG chunks to ground the clip in the source documents.
    2. Builds a cinematic prompt via the chat LLM.
    3. Calls Replicate, downloads the .mp4, saves it into storage_dir.
    """
    try:
        def _generate():
            rag_chunks = _gather_av_context(
                req.collection_name, req.conversation_id, req.question
            )
            prompt_result = build_video_prompt(
                question=req.question,
                welcome_messages=req.welcome_messages,
                rag_chunks=rag_chunks if rag_chunks else None,
                chat_history=req.chat_history,
            )
            logger.info(
                f"🎬 Video prompt: {prompt_result['prompt'][:150]}... "
                f"(sources: {prompt_result.get('source_indices', [])})"
            )
            result = generate_video(
                prompt=prompt_result["prompt"],
                storage_dir=req.storage_dir,
                duration_seconds=req.duration_seconds,
            )
            result["video_prompt"] = prompt_result["prompt"]
            result["video_title"] = prompt_result["title"]
            source_indices = prompt_result.get("source_indices", [])
            result["rag_sources"] = [
                rag_chunks[i]
                for i in source_indices
                if isinstance(i, int) and 0 <= i < len(rag_chunks)
            ]
            return result

        return await asyncio.to_thread(_generate)
    except Exception as e:
        logger.exception("Error generating video")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/generate-music")
async def generate_music_endpoint(req: GenerateMusicRequest):
    """Generate a short music clip using Replicate (MusicGen).

    Same pipeline as /generate-video but tailored for instrumental audio.
    """
    try:
        def _generate():
            rag_chunks = _gather_av_context(
                req.collection_name, req.conversation_id, req.question
            )
            prompt_result = build_music_prompt(
                question=req.question,
                welcome_messages=req.welcome_messages,
                rag_chunks=rag_chunks if rag_chunks else None,
                chat_history=req.chat_history,
            )
            logger.info(
                f"🎵 Music prompt: {prompt_result['prompt'][:150]}... "
                f"(sources: {prompt_result.get('source_indices', [])})"
            )
            result = generate_music(
                prompt=prompt_result["prompt"],
                storage_dir=req.storage_dir,
                duration_seconds=req.duration_seconds,
            )
            result["music_prompt"] = prompt_result["prompt"]
            result["music_title"] = prompt_result["title"]
            source_indices = prompt_result.get("source_indices", [])
            result["rag_sources"] = [
                rag_chunks[i]
                for i in source_indices
                if isinstance(i, int) and 0 <= i < len(rag_chunks)
            ]
            return result

        return await asyncio.to_thread(_generate)
    except Exception as e:
        logger.exception("Error generating music")
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8321)
