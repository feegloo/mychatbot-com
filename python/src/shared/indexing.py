from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from .chapters import (
    build_page_to_chapter_map,
    chapters_to_serializable,
    detect_chapters,
)
from .chunkers import Chunk, split_into_chunks
from .cloud_dispatch import is_cloud_mode
from .describe import DescribeResult, describe_documents
from .extractors import _MIME_TYPES, IMAGE_EXTENSIONS, clean_file_name, extract_pdf, ocr_pdf_page
from .lang_detect import detect_language
from .metadata import extract_metadata_many
from .moderation import SexualContentError, check_content_moderation
from .page_worker import FileProcessingResult, process_pdf_parallel, process_standalone_file
from .suggested_questions import suggest_questions_from_chunks
from .telemetry import log_processing_event, trace_step
from .vector_store import delete_collection, upsert_chunks
from .wiki import build_conversation_wiki

logger = logging.getLogger(__name__)

# Thread pool for background welcome message generation (started early via callback)
_describe_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="early-describe")
_EARLY_WELCOME_PAGE_TARGET = 100
_MIN_PAGE_TEXT_CHARS_FOR_SUMMARY = 50
_MIN_PAGE_SUMMARY_CHARS = 200
_MAX_PAGE_SUMMARY_CHARS = 600
_PAGE_SUMMARY_RATIO = 10


def _build_document_context(file_path: str, file_metadata: dict[str, dict] | None) -> str:
    """Build a short document context string for image description prompts.

    Combines title, author, and cleaned file name so the vision model knows
    what domain vocabulary to use when describing extracted images.
    """
    p = Path(file_path)
    display_name = clean_file_name(p.name)
    parts: list[str] = []

    if file_metadata:
        meta = file_metadata.get(p.name, {})
        if isinstance(meta, dict):
            title = meta.get("title", "")
            author = meta.get("author", "")
            if title:
                parts.append(title)
            if author:
                parts.append(f"by {author}")

    # Always include the cleaned filename as a fallback hint
    if not parts:
        parts.append(display_name)
    elif display_name and display_name not in " ".join(parts):
        parts.append(f"(file: {display_name})")

    return " — ".join(parts)

# OCR-first welcome strategy for scanned / image-based PDFs
# (tunable via environment variables for production)
_OCR_PREFETCH_PAGES = int(os.getenv("OCR_PREFETCH_PAGES", "0"))  # 0 = all pages
_OCR_PREFETCH_WORKERS = int(os.getenv("OCR_PREFETCH_WORKERS", "8"))
_OCR_MIN_CHARS_PER_PAGE = 10  # Very low threshold — any OCR text is useful for welcome


def _build_page_summary(page_text: str) -> str | None:
    """Build a compact per-page summary used for early welcome generation.

    Thresholds keep early prompts informative but bounded:
    - Skip very short pages (<= 50 chars) to avoid low-signal summaries.
    - Use ~10% of page text, clamped to 200..600 chars, so each page contributes
      enough context without bloating the early describe prompt.
    """
    if len(page_text.strip()) <= _MIN_PAGE_TEXT_CHARS_FOR_SUMMARY:
        return None
    summary_len = max(
        _MIN_PAGE_SUMMARY_CHARS,
        min(_MAX_PAGE_SUMMARY_CHARS, len(page_text) // _PAGE_SUMMARY_RATIO),
    )
    return page_text[:summary_len].replace("\n", " ").strip()


def _ocr_prefetch_welcome(
    file_path: str,
    file_metadata: dict,
    file_name_list: list[str],
    file_types: dict[str, str],
    *,
    conversation_id: str | None = None,
    user_language: str | None = None,
) -> DescribeResult | None:
    """OCR-first welcome strategy for scanned / image-based PDFs.

    When native text extraction yields fewer than 500 words (no text layer),
    we OCR the first _OCR_PREFETCH_PAGES pages in parallel so the user
    receives a welcome message before full indexing completes.  The rest of
    the pages are processed normally by the main pipeline.
    """
    import fitz  # lazy — only needed for scanned PDFs

    p = Path(file_path)
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        logger.warning(f"⚠️ OCR prefetch: cannot open {p.name}: {e}")
        return None

    if total_pages < 2:
        # Single-page documents are handled fast enough by the regular path.
        return None

    # 0 means "all pages"; otherwise respect the configured cap.
    pages_to_ocr = total_pages if _OCR_PREFETCH_PAGES == 0 else min(_OCR_PREFETCH_PAGES, total_pages)
    logger.info(
        f"⏱️  Scanned PDF '{p.name}': OCR-prefetching "
        f"{pages_to_ocr}/{total_pages} pages "
        f"with {_OCR_PREFETCH_WORKERS} workers"
    )

    def _ocr_page(page_idx: int) -> tuple[int, str]:
        try:
            return page_idx, ocr_pdf_page(
                file_path, page_idx, conversation_id=conversation_id
            ) or ""
        except Exception as e:
            logger.warning(f"⚠️ OCR prefetch page {page_idx + 1} of {p.name}: {e}")
            return page_idx, ""

    with ThreadPoolExecutor(max_workers=_OCR_PREFETCH_WORKERS) as pool:
        ocr_results = list(pool.map(_ocr_page, range(pages_to_ocr)))

    page_texts = dict(ocr_results)
    total_chars = sum(len(t) for t in page_texts.values())
    avg_chars = total_chars / pages_to_ocr

    # Even if OCR yielded little text (heavily scanned / low-quality scan), we
    # still generate a welcome so the user is not left waiting in silence.  The
    # system prompt will tell the model to describe what it found and explain
    # that more OCR is underway.
    if avg_chars < _OCR_MIN_CHARS_PER_PAGE:
        logger.info(
            f"⏱️  OCR prefetch: very little text for {p.name} "
            f"(avg {avg_chars:.0f} chars/page) — generating minimal OCR-in-progress welcome"
        )
        # Build a tiny "in progress" placeholder combined text
        sparse_text = "\n\n".join(
            f"# Page {idx + 1}\n\n{t}"
            for idx, t in sorted(page_texts.items())
            if t.strip()
        )
        # Fall back to metadata-only describe so the describe prompt gets the
        # "scanned_no_text" signal injected by the caller.
        combined = sparse_text or ""
        ocr_lang = detect_language(combined[:2000]) if combined else None
        logger.info(
            f"⏱️  OCR prefetch minimal done for {p.name}: "
            f"{total_chars} chars, lang={ocr_lang}, "
            f"{pages_to_ocr}/{total_pages} pages prefetched"
        )
        return describe_documents(
            [{"file_path": file_path, "file_name": p.name, "text": combined}],
            [],
            language=ocr_lang,
            file_metadata=file_metadata,
            file_names=file_name_list,
            file_types=file_types,
            # Signal to describe_documents that this is an OCR-in-progress result
            ocr_in_progress=True,
            total_pages_hint=total_pages,
            ocr_pages_done=pages_to_ocr,
            user_language=user_language,
        )

    combined = "\n\n".join(
        f"# Page {idx + 1}\n\n{t}"
        for idx, t in sorted(page_texts.items())
        if t.strip()
    )
    ocr_lang = detect_language(combined[:2000]) if combined else None
    logger.info(
        f"⏱️  OCR prefetch done for {p.name}: "
        f"{total_chars} chars, lang={ocr_lang}, "
        f"{pages_to_ocr}/{total_pages} pages prefetched"
    )
    # If we only processed a subset of pages, flag that OCR is still ongoing
    # so describe_documents can include that context in the welcome message.
    still_processing = pages_to_ocr < total_pages
    return describe_documents(
        [{"file_path": file_path, "file_name": p.name, "text": combined}],
        [],
        language=ocr_lang,
        file_metadata=file_metadata,
        file_names=file_name_list,
        file_types=file_types,
        ocr_in_progress=still_processing,
        total_pages_hint=total_pages,
        ocr_pages_done=pages_to_ocr,
        user_language=user_language,
    )


def _maybe_regenerate_heavy_ocr_welcome(
    *,
    file_results: list,
    extracted: list[dict],
    file_metadata: dict,
    file_name_list: list[str],
    file_types: dict[str, str],
    detected_language: str | None,
    describe_chapters: list[dict] | None,
    current_welcome: str,
    on_progress: Callable[[str, dict], None] | None,
    user_language: str | None = None,
) -> DescribeResult | None:
    """Regenerate the welcome message for heavy-OCR PDFs once indexing is done.

    The initial ("fast") welcome is built from the first few OCR'd pages so
    users see something quickly. For large books where OCR dominates, that
    early snapshot is a poor summary of the full work. Once every page has
    been OCR'd and upserted, we run describe_documents one more time with
    the full text and emit a fresh welcome event.
    """
    heavy_ocr_file = next(
        (
            fr
            for fr in file_results
            if getattr(fr, "streaming_meta", None)
            and fr.streaming_meta.get("is_heavy_ocr")
        ),
        None,
    )
    if heavy_ocr_file is None:
        return None

    full_extracted = [
        {
            "file_path": doc["file_path"],
            "file_name": doc["file_name"],
            "text": doc.get("text") or "",
        }
        for doc in extracted
    ]
    total_chars = sum(len(d["text"]) for d in full_extracted)
    logger.info(
        f"🔁 Regenerating welcome for heavy-OCR file {heavy_ocr_file.file_name} "
        f"({heavy_ocr_file.streaming_meta['ocr_page_count']} OCR pages, "
        f"{total_chars} chars)"
    )
    try:
        regen = describe_documents(
            full_extracted,
            [],
            language=detected_language,
            file_metadata=file_metadata,
            file_names=file_name_list,
            file_types=file_types,
            chapters=describe_chapters,
            user_language=user_language,
        )
    except Exception as e:
        logger.warning(f"⚠️ Welcome regeneration failed: {e}")
        return None

    new_welcome = (regen.get("welcome_message") or "").strip()
    if not new_welcome or new_welcome == current_welcome.strip():
        return None

    # The [mindmap]...[/mindmap] block is kept embedded in the welcome message.
    # Emit as a follow-up welcome_message event so the frontend can replace
    # the provisional description.
    if on_progress is not None:
        try:
            on_progress(
                "welcome_message",
                {
                    "welcome_message": new_welcome,
                    "suggested_questions": regen.get("suggested_questions") or [],
                    "file_metadata": file_metadata or {},
                    "regenerated": True,
                },
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to emit regenerated welcome event: {e}")

    return regen


def _image_chunks(images: list[dict], file_name: str) -> list[Chunk]:
    """Convert extracted image dicts into Chunk objects.

    The chunk text prefixes the description with an image context header so
    the embedded vector carries semantic signals about both what the image shows
    and where it came from.  This header mirrors what the RAG prompt sees when
    the chunk is retrieved, making the model more likely to reference the image.
    """
    chunks = []
    for idx, img in enumerate(images):
        abs_path = Path(img["image_path"])
        image_name = abs_path.name

        page = img["page"]
        section = f"Image (page {page})" if page is not None else "Image"

        # Prefix the description with a searchable header.
        # The header repeats the page and filename so retrieval scores improve
        # for queries like "show me the diagram on page 5" or topic-based searches.
        display_file = clean_file_name(img.get("file_name", file_name))
        page_label = f"page {page}" if page is not None else "unknown page"
        chunk_text = (
            f"[Image — {display_file}, {page_label}]\n{img['description']}"
        )

        chunks.append(
            Chunk(
                chunk_id=f"{Path(img['file_name']).stem}_img_{idx}",
                file_name=img["file_name"],
                text=chunk_text,
                section=section,
                page=page,
                metadata={
                    "is_image": True,
                    "image_name": image_name,
                },
            )
        )
    return chunks


def index_documents(
    conversation_id: str,
    collection_name: str,
    file_paths: list[str],
    on_progress: Callable[[str, dict], None] | None = None,
    *,
    job_metadata: dict | None = None,
    allow_delegation: bool = True,
    user_language: str | None = None,
) -> dict:
    logger.info(
        f"📁 Starting indexing of {len(file_paths)} file(s) for collection: {collection_name}"
    )

    # Resolve user_language: prefer explicit arg, then fall back to job_metadata
    # (the worker receives job_metadata from the delegated Pub/Sub payload).
    resolved_user_language = user_language or (job_metadata or {}).get("user_language")

    # When delegating to a worker, embed user_language in job_metadata so it
    # survives the Pub/Sub serialisation and is available on the worker side.
    if resolved_user_language and (job_metadata is None or "user_language" not in job_metadata):
        job_metadata = dict(job_metadata or {})
        job_metadata["user_language"] = resolved_user_language

    # ── CPU budget + delegation decision ─────────────────────────────
    # Main instance caps its own CPU usage at 50% of system cores (see
    # shared.cpu_budget). If the budget is exhausted, we publish the job
    # to Pub/Sub so chatrag-worker can pick it up. ``allow_delegation``
    # is False on workers themselves — they always run inline.
    slots_reserved = _reserve_cpu_or_delegate(
        conversation_id=conversation_id,
        collection_name=collection_name,
        file_paths=file_paths,
        on_progress=on_progress,
        job_metadata=job_metadata,
        allow_delegation=allow_delegation,
    )
    if slots_reserved is None:
        # Delegated — caller should rely on worker's NOTIFY events instead.
        return {"delegated": True, "conversation_id": conversation_id}

    try:
        return _index_documents_inline(
            conversation_id=conversation_id,
            collection_name=collection_name,
            file_paths=file_paths,
            on_progress=on_progress,
            user_language=resolved_user_language,
        )
    finally:
        from .cpu_budget import release as _release_cpu
        _release_cpu(slots_reserved)


def _reserve_cpu_or_delegate(
    *,
    conversation_id: str,
    collection_name: str,
    file_paths: list[str],
    on_progress: Callable[[str, dict], None] | None,
    job_metadata: dict | None,
    allow_delegation: bool,
) -> int | None:
    """Reserve CPU slots for this job or publish it to Pub/Sub.

    Returns the slot count reserved (caller must release), or ``None``
    when the job has been delegated to a remote worker.
    """
    from .cpu_budget import (
        MAIN_MAX_CPU,
        estimate_slots_for_file,
        try_reserve,
    )

    slots = max((estimate_slots_for_file(fp.split("|", 1)[0]) for fp in file_paths), default=1)
    # A single job can never demand more than the entire main budget.
    slots = min(slots, MAIN_MAX_CPU)

    if try_reserve(slots):
        logger.info(
            f"🧮 Reserved {slots} CPU slot(s) for job (files={len(file_paths)})"
        )
        return slots

    if not allow_delegation:
        # Caller opted out (e.g. this IS the worker). Fall through and
        # run anyway — over-subscription is less bad than dropping work.
        logger.warning(
            f"⚠️ CPU budget exhausted but delegation disabled; running inline "
            f"({slots} slot(s) requested)"
        )
        return slots

    delegated = _try_delegate_to_worker(
        conversation_id=conversation_id,
        collection_name=collection_name,
        file_paths=file_paths,
        on_progress=on_progress,
        job_metadata=job_metadata,
    )
    if delegated:
        return None

    # Delegation failed (e.g. Pub/Sub unreachable). Run inline anyway
    # rather than losing the upload; CpuBudgetExhausted would surface
    # a worse UX than brief over-subscription.
    logger.warning(
        f"⚠️ Delegation unavailable; proceeding inline despite exhausted budget "
        f"({slots} slot(s) requested)"
    )
    return slots


def _try_delegate_to_worker(
    *,
    conversation_id: str,
    collection_name: str,
    file_paths: list[str],
    on_progress: Callable[[str, dict], None] | None,
    job_metadata: dict | None,
) -> bool:
    """Publish the job to the chatrag-worker Pub/Sub topic. Returns
    ``True`` on successful publish, ``False`` to signal the caller
    should fall back to inline processing.
    """
    import socket
    import uuid

    try:
        from .pubsub_client import (
            IndexingJobPayload,
            PubSubNotConfigured,
            publish_indexing_job,
        )
    except ImportError:
        # google-cloud-pubsub not installed (shouldn't happen in prod image).
        return False

    job_id = str(uuid.uuid4())
    worker_name = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown"
    payload = IndexingJobPayload(
        worker_name=worker_name,
        file_names=file_paths,
        conversation_id=conversation_id,
        collection_name=collection_name,
        job_id=job_id,
        metadata=job_metadata or {},
    )
    try:
        message_id = publish_indexing_job(payload)
    except PubSubNotConfigured:
        logger.info("Pub/Sub not configured; cannot delegate job")
        return False
    except Exception as e:
        logger.exception(f"Pub/Sub publish failed: {e}")
        return False

    logger.info(
        f"📤 Delegated job {job_id} to chatrag-worker "
        f"(msg={message_id}, files={len(file_paths)})"
    )
    log_processing_event(
        conversation_id,
        ",".join(Path(fp.split('|', 1)[0]).name for fp in file_paths),
        "job_delegated",
        status="queued",
        detail=f"job_id={job_id} msg={message_id}",
    )
    if on_progress:
        on_progress("delegated", {"job_id": job_id, "worker_name": worker_name})
    return True


def _index_documents_inline(
    conversation_id: str,
    collection_name: str,
    file_paths: list[str],
    on_progress: Callable[[str, dict], None] | None = None,
    user_language: str | None = None,
) -> dict:
    log_processing_event(
        conversation_id,
        ",".join(Path(fp).name for fp in file_paths),
        "indexing_started",
        status="running",
        detail=f"{len(file_paths)} file(s)",
    )

    # Extract file metadata (EXIF, PDF info, etc.)
    with trace_step(conversation_id, "*", "extract_metadata", detail=f"{len(file_paths)} files"):
        file_metadata = extract_metadata_many(file_paths)

    # Pre-compute file types for contextual question prompts
    file_types: dict[str, str] = {}
    for fp in file_paths:
        p = Path(fp)
        suffix = p.suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}:
            file_types[p.name] = "image"
        elif suffix == ".pdf":
            file_types[p.name] = "pdf"
        else:
            file_types[p.name] = "document"
    file_name_list = [Path(fp).name for fp in file_paths]

    # ── Parallel per-page processing ─────────────────────────────────
    # PDFs get parallel page-level processing; other files processed individually.
    # For scanned/OCR PDFs, we start welcome message generation early via callback
    # so the user doesn't wait for all N OCR calls before seeing the welcome.
    file_results: list[FileProcessingResult] = []
    early_describe_future: Future | None = None
    welcome_emitted = False

    def _emit_welcome(result: DescribeResult | None) -> None:
        nonlocal welcome_emitted
        if welcome_emitted or not on_progress or not result:
            return
        welcome_text = result.get("welcome_message") or ""
        if not welcome_text:
            return

        # The [mindmap]...[/mindmap] block is kept embedded in the welcome message.
        # The frontend extracts it when the user clicks "Mapa Myśli" and
        # hides it from the main chat view during rendering.
        on_progress("welcome_message", {
            "welcome_message": welcome_text,
            "suggested_questions": result.get("suggested_questions") or [],
            "file_metadata": file_metadata or {},
        })
        welcome_emitted = True

    def _set_early_describe_future(future: Future) -> None:
        nonlocal early_describe_future
        early_describe_future = future

        def _done(done_future: Future) -> None:
            try:
                result = done_future.result()
            except Exception as e:
                logger.warning(f"⚠️ Early welcome generation failed: {e}")
                return
            _emit_welcome(result)

        future.add_done_callback(_done)

    def _on_early_text(early_text: str, early_summaries: list[dict]) -> None:
        """Callback: start welcome message generation with early OCR results.

        Called by process_pdf_parallel after early_text_timeout_s, while
        remaining pages are still being processed. Submits describe_documents
        to a background thread so it runs in parallel with page processing.
        """
        nonlocal early_describe_future
        if early_describe_future is not None:
            return  # Already started
        early_lang = detect_language(early_text[:2000]) if early_text else None
        early_extracted = [
            {
                "file_path": file_paths[0] if file_paths else "",
                "file_name": Path(file_paths[0]).name if file_paths else "",
                "text": early_text,
            }
        ]
        logger.info(
            f"⏱️  Starting early welcome message generation "
            f"({len(early_text)} chars, lang={early_lang})"
        )
        _set_early_describe_future(
            _describe_pool.submit(
                describe_documents,
                early_extracted,
                [],
                language=early_lang,
                file_metadata=file_metadata,
                page_summaries=early_summaries or None,
                file_names=file_name_list,
                file_types=file_types,
                user_language=user_language,
            )
        )

    def _prefetch_pdf_welcome(file_path: str) -> DescribeResult | None:
        try:
            text = extract_pdf(Path(file_path))
        except Exception as e:
            logger.warning(f"⚠️ Fast PDF welcome prefetch failed for {Path(file_path).name}: {e}")
            return None

        word_count = len(text.split())
        if word_count < 500:
            # Very little native text → likely a scanned / image-based PDF.
            # Fall back to parallel OCR of the first pages so the welcome is
            # still served promptly despite having no text layer.
            logger.info(
                f"⏱️  Scanned PDF detected for {Path(file_path).name} ({word_count} words) "
                f"— switching to OCR-prefetch welcome strategy"
            )
            return _ocr_prefetch_welcome(
                file_path,
                file_metadata,
                file_name_list,
                file_types,
                conversation_id=conversation_id,
                user_language=user_language,
            )

        quick_chapters = chapters_to_serializable(detect_chapters(file_path))
        quick_lang = detect_language(text[:2000]) if text else None
        logger.info(
            f"⏱️  Starting fast full-book welcome prefetch for {Path(file_path).name} "
            f"({len(text)} chars, {word_count} words)"
        )
        return describe_documents(
            [
                {
                    "file_path": file_path,
                    "file_name": Path(file_path).name,
                    "text": text,
                }
            ],
            [],
            language=quick_lang,
            file_metadata=file_metadata,
            file_names=file_name_list,
            file_types=file_types,
            chapters=quick_chapters or None,
            user_language=user_language,
        )

    for file_path in file_paths:
        p = Path(file_path)
        suffix = p.suffix.lower()

        if suffix == ".pdf":
            output_dir = str(p.parent)
            if early_describe_future is None:
                _set_early_describe_future(_describe_pool.submit(_prefetch_pdf_welcome, file_path))
            if is_cloud_mode():
                # Cloud mode: stream pages through our hybrid OCR+upsert processor.
                # This replaces the previous per-page Cloud Run Jobs dispatch —
                # far cheaper (no container spin-ups), faster (parallel OCR from
                # a single process), and searchable mid-indexing (chunks upserted
                # per page instead of in one batch at the end).
                from .pdf_pages_db import save_page
                from .streaming_pdf import process_pdf_streaming

                logger.info(f"☁️ Cloud mode: streaming {p.name} with hybrid OCR")

                # Pre-compute chapter map so each page's chunks get enriched
                # metadata before their incremental upsert to Chroma.
                _chapters = detect_chapters(file_path)
                _page_to_chapter_nr: dict[int, int] = (
                    build_page_to_chapter_map(_chapters) if _chapters else {}
                )
                _page_to_chapter_name: dict[int, str] = {}
                for _ch in _chapters or []:
                    if _ch.chapter_name:
                        for _pg in range(_ch.start_page, _ch.end_page + 1):
                            _page_to_chapter_name[_pg] = _ch.chapter_name

                local_chunks: list[Chunk] = []
                early_page_texts: list[str] = []
                early_page_summaries: list[dict] = []
                cloud_early_started = False
                chunks_lock = threading.Lock()

                def _on_page_ready(outcome) -> None:
                    nonlocal cloud_early_started
                    chapter_nr = _page_to_chapter_nr.get(outcome.page_nr)
                    # Persist the page so we can regenerate the welcome and
                    # recover mid-indexing without re-OCR'ing on restart.
                    save_page(
                        conversation_id=conversation_id,
                        file_name=p.name,
                        page_nr=outcome.page_nr,
                        text=outcome.text,
                        source=outcome.source,
                        chapter_nr=chapter_nr,
                        error_message=outcome.error,
                    )
                    if outcome.source == "failed" or not outcome.text.strip():
                        return
                    # Chunk this page and upsert to Chroma immediately so
                    # answers can reference it before indexing finishes.
                    page_chunks = split_into_chunks(
                        p.name, outcome.text, page_num=outcome.page_nr
                    )
                    # Enrich with chapter metadata so retrieval works the same
                    # as in the non-streaming path.
                    if chapter_nr is not None:
                        ch_name = _page_to_chapter_name.get(outcome.page_nr)
                        for _c in page_chunks:
                            _c.metadata["chapter_number"] = chapter_nr
                            if ch_name:
                                _c.metadata["chapter_name"] = ch_name
                    if page_chunks:
                        try:
                            upsert_chunks(
                                collection_name=collection_name,
                                conversation_id=conversation_id,
                                chunks=page_chunks,
                            )
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Incremental upsert failed for p.{outcome.page_nr}: {e}"
                            )
                        with chunks_lock:
                            local_chunks.extend(page_chunks)
                            early_page_texts.append(outcome.text)
                            summary = _build_page_summary(outcome.text)
                            if summary:
                                early_page_summaries.append(
                                    {
                                        "page": outcome.page_nr,
                                        "file_name": p.name,
                                        "summary": summary,
                                    }
                                )
                            early_target = max(
                                1, min(_EARLY_WELCOME_PAGE_TARGET, outcome.page_nr)
                            )
                            should_start_early = (
                                not cloud_early_started
                                and len(early_page_texts) >= early_target
                            )
                        if should_start_early:
                            _on_early_text(
                                "\n\n".join(early_page_texts),
                                list(early_page_summaries),
                            )
                            cloud_early_started = True
                            logger.info(
                                f"⏱️  Cloud-stream early welcome started after "
                                f"{len(early_page_texts)} pages"
                            )

                def _stream_progress(parsed: int, total: int) -> None:
                    if on_progress:
                        on_progress("page_progress", {"parsed": parsed, "total": total})

                stream_result = process_pdf_streaming(
                    file_path,
                    conversation_id=conversation_id,
                    on_page_ready=_on_page_ready,
                    on_progress=_stream_progress,
                )
                total_pages = stream_result.total_pages

                # Small PDFs may complete before reaching the early target.
                if not cloud_early_started and early_page_texts:
                    _on_early_text(
                        "\n\n".join(early_page_texts),
                        list(early_page_summaries),
                    )
                    cloud_early_started = True

                full_text = stream_result.full_text
                logger.info(
                    f"📄 Streamed {len(full_text)} chars, "
                    f"{len(local_chunks)} chunks for {p.name} "
                    f"(OCR pages: {stream_result.ocr_page_count}, "
                    f"failed: {stream_result.failed_page_count})"
                )

                result = FileProcessingResult(
                    file_name=p.name,
                    file_path=file_path,
                    total_pages=total_pages,
                )
                result.full_text = full_text
                # Already upserted per page — set to empty so the end-of-indexing
                # upsert becomes a no-op for this file. streaming_meta carries
                # the chunks for downstream reporting + welcome regeneration.
                result.all_chunks = []
                result.streaming_meta = {
                    "chunks_already_upserted": local_chunks,
                    "is_heavy_ocr": stream_result.is_heavy_ocr,
                    "ocr_page_count": stream_result.ocr_page_count,
                    "chapters": chapters_to_serializable(_chapters) if _chapters else [],
                }
                for outcome in stream_result.pages:
                    if outcome.source == "failed":
                        result.errors.append(
                            {"page": outcome.page_nr, "error": outcome.error or "unknown"}
                        )
            else:
                # Local mode (default): parallel threads
                def _on_page_done(parsed: int, total: int) -> None:
                    if on_progress:
                        on_progress("page_progress", {"parsed": parsed, "total": total})

                result = process_pdf_parallel(
                    file_path, output_dir, conversation_id,
                    on_early_text=_on_early_text,
                    document_context=_build_document_context(file_path, file_metadata),
                    on_page_done=_on_page_done,
                )
        else:
            result = process_standalone_file(file_path, conversation_id)

        file_results.append(result)

    # ── Content moderation: block sexual content before bulk upsert ──────────
    # Runs after text extraction so we have content to check.  In cloud streaming
    # mode some chunks may already be in Chroma (upserted per-page).
    # SexualContentError deletes the entire Chroma collection so no searchable
    # data is left behind, then propagates up so the caller marks the
    # conversation as failed and the user sees the error message.
    try:
        for fr in file_results:
            p = Path(fr.file_path)
            suffix = p.suffix.lower()
            image_bytes: bytes | None = None
            mime_type = "image/png"

            if suffix in IMAGE_EXTENSIONS:
                try:
                    image_bytes = p.read_bytes()
                    mime_type = _MIME_TYPES.get(suffix, "image/png")
                except OSError as read_err:
                    logger.warning(
                        "⚠️ Could not read image for moderation check (%s): %s",
                        fr.file_name,
                        read_err,
                    )

            check_content_moderation(
                fr.full_text or "",
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
    except SexualContentError:
        # Remove any chunks that were already upserted during streaming so
        # the rejected content is not searchable.
        delete_collection(collection_name)
        raise

    # Aggregate chunks, images, text across all files
    all_chunks: list[Chunk] = []
    # Chunks that were already upserted per-page during streaming. Kept
    # separately so the final batch upsert does not re-add them (Chroma would
    # reject duplicate IDs), but they still count toward total chunk_count
    # and appear in chapter reporting.
    streaming_chunks: list[Chunk] = []
    all_images: list[dict] = []
    extracted: list[dict] = []
    detected_language = None
    all_errors: list[dict] = []
    all_page_summaries: list[dict] = []

    for fr in file_results:
        # Build extracted doc format for describe_documents compatibility
        extracted.append(
            {
                "file_path": fr.file_path,
                "file_name": fr.file_name,
                "text": fr.full_text,
            }
        )
        all_chunks.extend(fr.all_chunks)
        if getattr(fr, "streaming_meta", None):
            streaming_chunks.extend(
                fr.streaming_meta.get("chunks_already_upserted") or []
            )
        all_images.extend(fr.all_images)
        all_errors.extend(fr.errors)

        # Collect per-page summaries for large-document describe strategy
        for pr in fr.page_results:
            if pr.description_summary:
                all_page_summaries.append(
                    {
                        "page": pr.page_number,
                        "file_name": pr.file_name,
                        "summary": pr.description_summary,
                    }
                )

        if fr.full_text:
            fr_lang = detect_language(fr.full_text[:2000])
            if detected_language is None:
                detected_language = fr_lang
            # Store per-file detected language in file_metadata so the backend can
            # persist it to uploaded_files.metadata_json. This lets the frontend and
            # RAG engine know the source document language independently of the
            # [language] tag, which now encodes the response/content language.
            if fr.file_name in file_metadata:
                file_metadata[fr.file_name]["detected_language"] = fr_lang

    # Add image chunks (description text gets embedded alongside regular chunks)
    if all_images:
        img_chunks = _image_chunks(all_images, "")
        logger.info(f"🖼️  Adding {len(img_chunks)} image chunks")
        all_chunks.extend(img_chunks)

    logger.info(
        f"✅ Processed {len(file_results)} file(s): "
        f"{len(all_chunks)} chunks, {len(all_images)} images"
    )

    # ── Chapter detection ────────────────────────────────────────────
    # Detect chapters in PDFs and enrich chunk metadata with chapter_number + chapter_name
    all_chapters: dict[str, list[dict]] = {}  # file_name -> chapters (serializable)
    page_to_chapter_maps: dict[str, dict[int, int]] = {}  # file_name -> {page: chapter_nr}
    page_to_chapter_name: dict[str, dict[int, str]] = {}  # file_name -> {page: chapter_name}
    for file_path in file_paths:
        p = Path(file_path)
        if p.suffix.lower() == ".pdf":
            chapters = detect_chapters(file_path)
            if chapters:
                all_chapters[p.name] = chapters_to_serializable(chapters)
                page_to_chapter_maps[p.name] = build_page_to_chapter_map(chapters)
                # Build page -> chapter_name map
                name_map: dict[int, str] = {}
                for ch in chapters:
                    if ch.chapter_name:
                        for pg in range(ch.start_page, ch.end_page + 1):
                            name_map[pg] = ch.chapter_name
                page_to_chapter_name[p.name] = name_map
                logger.info(
                    f"📖 {p.name}: {len(chapters)} chapters detected, "
                    f"pages mapped: {len(page_to_chapter_maps[p.name])}"
                )

    # Enrich chunks with chapter_number and chapter_name metadata
    if page_to_chapter_maps:
        enriched_count = 0
        for chunk in all_chunks:
            page_map = page_to_chapter_maps.get(chunk.file_name)
            if page_map and chunk.page is not None:
                chapter_nr = page_map.get(chunk.page)
                if chapter_nr is not None:
                    chunk.metadata["chapter_number"] = chapter_nr
                    name = page_to_chapter_name.get(chunk.file_name, {}).get(chunk.page)
                    if name:
                        chunk.metadata["chapter_name"] = name
                    enriched_count += 1
        logger.info(f"📖 Enriched {enriched_count}/{len(all_chunks)} chunks with chapter metadata")

    describe_chapters = all_chapters.get(file_name_list[0]) if len(file_name_list) == 1 else None

    # Save raw text and page summaries to disk for follow-up answer context
    storage_dir = str(Path(file_paths[0]).parent) if file_paths else None
    if storage_dir:
        try:
            raw_texts = {}
            for doc in extracted:
                if doc.get("text"):
                    raw_texts[doc["file_name"]] = doc["text"]
            if raw_texts:
                raw_text_path = Path(storage_dir) / "_raw_text.json"
                raw_text_path.write_text(
                    json.dumps(raw_texts, ensure_ascii=False), encoding="utf-8"
                )
                total_raw = sum(len(t) for t in raw_texts.values())
                logger.info(
                    f"💾 Saved raw text to {raw_text_path} "
                    f"({total_raw} chars, {len(raw_texts)} files)"
                )
            if all_page_summaries:
                summaries_path = Path(storage_dir) / "_page_summaries.json"
                summaries_path.write_text(
                    json.dumps(all_page_summaries, ensure_ascii=False), encoding="utf-8"
                )
                logger.info(
                    f"💾 Saved {len(all_page_summaries)} page summaries to {summaries_path}"
                )
            if all_chapters:
                chapters_path = Path(storage_dir) / "_chapters.json"
                chapters_path.write_text(
                    json.dumps(all_chapters, ensure_ascii=False), encoding="utf-8"
                )
                logger.info(
                    f"💾 Saved chapter data for {len(all_chapters)} file(s) to {chapters_path}"
                )
        except Exception as e:
            logger.warning(f"⚠️ Failed to save raw text / page summaries: {e}")

    # Run vector upsert and description in parallel first (both are IO-bound API calls)
    logger.info(f"📦 Upserting {len(all_chunks)} chunks + generating description in parallel...")
    chunk_texts = [chunk.text for chunk in all_chunks]

    with (
        trace_step(
            conversation_id,
            "*",
            "upsert_and_describe",
            detail=f"{len(all_chunks)} chunks",
        ),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        upsert_future = pool.submit(
            upsert_chunks,
            collection_name=collection_name,
            conversation_id=conversation_id,
            chunks=all_chunks,
        )

        # If early describe was started during processing, try to reuse it.
        # Otherwise, start a fresh describe with the full extracted text.
        describe_result: DescribeResult | None = None
        if early_describe_future is not None:
            logger.info("⏱️  Resolving precomputed welcome message")
            try:
                describe_result = early_describe_future.result()
            except Exception as e:
                logger.warning(f"⚠️ Early welcome result failed, regenerating: {e}")
                describe_result = None

        if describe_result is None:
            describe_future = pool.submit(
                describe_documents,
                extracted,
                all_images,
                language=detected_language,
                file_metadata=file_metadata,
                page_summaries=all_page_summaries or None,
                file_names=file_name_list,
                file_types=file_types,
                chapters=describe_chapters,
                user_language=user_language,
            )
            describe_result = describe_future.result()

        # Get welcome message + suggested questions ASAP — don't wait for upsert
        welcome_message = describe_result["welcome_message"]
        suggested_questions = describe_result["suggested_questions"]

        # Emit welcome_message event immediately so the frontend can show it
        _emit_welcome(describe_result)
        # Refresh: _emit_welcome may have stripped an embedded [mindmap] block in-place.
        welcome_message = describe_result.get("welcome_message") or welcome_message

        upsert_result = upsert_future.result()

    # If describe didn't produce questions (e.g. split+synthesize for very large docs),
    # fall back to the separate suggest_questions_from_chunks call.
    if not suggested_questions and chunk_texts:
        logger.info("💡 Generating suggested prompts via fallback (separate call)...")
        # Extract page_count from file_metadata for large-chapter detection
        page_count_for_suggestions = None
        if file_metadata:
            for meta in file_metadata.values():
                if isinstance(meta, dict) and meta.get("page_count"):
                    try:
                        page_count_for_suggestions = int(meta["page_count"])
                        break
                    except (TypeError, ValueError):
                        pass

        with trace_step(conversation_id, "*", "generate_suggested_questions"):
            suggested_questions = suggest_questions_from_chunks(
                chunk_texts,
                language=user_language or detected_language,
                description=welcome_message or "",
                file_names=file_name_list,
                file_types=file_types,
                welcome_message=welcome_message or "",
                page_count=page_count_for_suggestions,
            )
    else:
        logger.info("💡 Suggested questions generated inline with welcome message")

    # ── Welcome regeneration for heavy-OCR PDFs ────────────────────────
    # When the initial welcome was generated from only the first ~N pages of a
    # scanned book (e.g. 611-page Arabic Mathnawi), the description is bound
    # to be generic. Now that OCR has finished for every page, regenerate the
    # welcome using the full aggregated text so the user sees a richer
    # description. Only runs when the streaming path reported heavy OCR
    # (>= 40% OCR pages) to keep the normal/native path untouched.
    regenerated_welcome = _maybe_regenerate_heavy_ocr_welcome(
        file_results=file_results,
        extracted=extracted,
        file_metadata=file_metadata,
        file_name_list=file_name_list,
        file_types=file_types,
        detected_language=detected_language,
        describe_chapters=describe_chapters,
        current_welcome=welcome_message or "",
        on_progress=on_progress,
        user_language=user_language,
    )
    if regenerated_welcome:
        welcome_message = regenerated_welcome.get("welcome_message") or welcome_message
        if regenerated_welcome.get("suggested_questions"):
            suggested_questions = regenerated_welcome["suggested_questions"]

    logger.info("✅ Indexing complete")
    logger.info(
        f"💡 Generated "
        f"{len(suggested_questions) if suggested_questions else 0} "
        f"suggested questions (lang={detected_language})"
    )
    logger.info(
        f"👋 Welcome message: {welcome_message[:100]}..."
        if welcome_message
        else "👋 No welcome message generated"
    )

    log_processing_event(
        conversation_id,
        ",".join(Path(fp).name for fp in file_paths),
        "indexing_completed",
        status="completed",
        detail=(
            f"{len(all_chunks)} chunks, {len(all_images)} images, "
            f"{len(suggested_questions or [])} questions"
            f"{f', {len(all_errors)} page errors' if all_errors else ''}"
        ),
    )

    result = {
        "conversation_id": conversation_id,
        "collection_name": collection_name,
        "file_count": len(file_paths),
        "chunk_count": len(all_chunks) + len(streaming_chunks),
        "suggested_questions": suggested_questions,
        "welcome_message": welcome_message,
        "detected_language": detected_language,
        "file_metadata": file_metadata,
        "processing_errors": all_errors if all_errors else None,
        **upsert_result,
    }

    # ── Internal "idea file" / wiki (Karpathy-style) ────────────────────
    # Generated AFTER the user-facing welcome message has been shown. Stored
    # as an internal (hidden) message and injected into ANSWER_PROMPT on
    # subsequent /ask calls, so the assistant has a structured, compounding
    # artifact instead of re-deriving the document's shape every turn.
    # Failures are swallowed — wiki is a best-effort enhancement.
    try:
        if welcome_message and collection_name:
            wiki_title = ", ".join(
                clean_file_name(name) for name in file_name_list[:3]
            ) or "Conversation"
            # Extract total page count so the wiki can scale extraction depth.
            wiki_page_count: int | None = None
            if file_metadata:
                for meta in file_metadata.values():
                    if isinstance(meta, dict) and meta.get("page_count"):
                        try:
                            wiki_page_count = int(meta["page_count"])
                            break
                        except (TypeError, ValueError):
                            pass
            with trace_step(conversation_id, "*", "build_conversation_wiki"):
                wiki_text = build_conversation_wiki(
                    conversation_id=conversation_id,
                    collection_name=collection_name,
                    conversation_title=wiki_title,
                    welcome_message=welcome_message,
                    storage_dir=storage_dir,
                    language=detected_language,
                    page_count=wiki_page_count,
                )
            if wiki_text and on_progress:
                on_progress(
                    "wiki_message",
                    {
                        "wiki_message": wiki_text,
                        "internal_kind": "wiki",
                    },
                )
                result["wiki_message"] = wiki_text
    except Exception as exc:
        # Never let wiki generation break indexing.
        logger.warning("📚 Wiki step failed (conv=%s): %s", conversation_id, exc)

    if on_progress:
        on_progress("complete", result)

    return result
