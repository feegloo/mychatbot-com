"""Parallel per-page PDF worker with telemetry.

Processes each PDF page (or standalone file) as an independent unit of work:
  1. Extract text from page
  2. Extract images from page (with dedup)
  3. Describe images via Vision API (parallel)
  4. Chunk text
  5. Generate embeddings

Supports two execution modes:
  - LOCAL: ThreadPoolExecutor using all available CPU cores
  - CLOUD_RUN: Dispatches Cloud Run Jobs (pre-built container, fast cold start)

Each page worker reports telemetry to processing_jobs via shared.telemetry.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from .chunkers import Chunk, split_into_chunks
from .extractors import (
    IMAGE_EXTENSIONS,
    MAX_IMAGE_ASPECT_RATIO,
    MIN_IMAGE_DIM,
    MIN_IMAGE_SIZE,
    _describe_image_with_context,
    _reflow_pdf_text,
    _sanitize_text,
    claim_xref_if_drawn_on_page,
    extract_text,
    ocr_pdf_page,
    page_needs_ocr,
)
from .telemetry import log_processing_error, log_processing_event, trace_step

logger = logging.getLogger(__name__)


def _read_worker_count(
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    # Invalid/non-numeric values use `default`.
    # Numeric values are clamped to [minimum, maximum] when `maximum` is provided.
    # If `maximum` is None, only the minimum bound is enforced.
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        if value < minimum:
            logger.warning(
                f"{name}={value} is below minimum {minimum}; using {minimum}"
            )
            return minimum
        if maximum is not None and value > maximum:
            logger.warning(
                f"{name}={value} is above maximum {maximum}; using {maximum}"
            )
            return maximum
        return value
    except ValueError:
        logger.warning(f"{name}={raw!r} is invalid; using {default}")
        return default


# IMPORTANT: keep PDF page workers conservative by default.
# PyMuPDF page extraction in highly parallel mode can be unstable on some PDFs
# (especially large scanned/OCR-heavy books), leading to process crashes and
# backend "fetch failed" errors. Allow opt-in scaling via env override.
_CPU_COUNT = os.cpu_count() or 1
_PAGE_WORKERS = _read_worker_count(
    "PDF_PAGE_WORKERS",
    default=1,
    minimum=1,
    maximum=_CPU_COUNT,
)
# Image description is IO-bound — parallelism is configurable and safe to keep higher.
_IMAGE_WORKERS = _read_worker_count(
    "PDF_IMAGE_WORKERS",
    default=_CPU_COUNT * 2,
    minimum=1,
    maximum=_CPU_COUNT * 4,
)


@dataclass
class PageResult:
    """Result of processing a single page."""

    page_number: int
    file_name: str
    chunks: list[Chunk] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    text: str = ""
    description_summary: str = ""
    error: str | None = None
    error_uid: str | None = None
    duration_ms: int = 0


@dataclass
class FileProcessingResult:
    """Aggregated result of processing all pages in a file."""

    file_name: str
    file_path: str
    total_pages: int
    page_results: list[PageResult] = field(default_factory=list)
    all_chunks: list[Chunk] = field(default_factory=list)
    all_images: list[dict] = field(default_factory=list)
    full_text: str = ""
    # Text from the first pages that completed within the early-text timeout.
    # Used by describe_documents to generate welcome messages without waiting
    # for all pages (critical for scanned/OCR PDFs with hundreds of pages).
    early_text: str = ""
    errors: list[dict] = field(default_factory=list)
    # Optional metadata populated by the streaming cloud-mode path. Carries
    # the chunks that were already upserted per-page so the caller can skip
    # the final batch upsert for this file, plus OCR stats for welcome regen.
    streaming_meta: dict | None = None


def _extract_page_text(doc: fitz.Document, page_idx: int) -> str:
    """Extract and reflow text from a single PDF page."""
    page = doc[page_idx]
    raw = page.get_text() or ""
    reflowed = _reflow_pdf_text(raw.strip())
    return _sanitize_text(f"# Page {page_idx + 1}\n\n{reflowed}")


def _extract_page_images(
    doc: fitz.Document,
    page_idx: int,
    output_dir: Path,
    pdf_stem: str,
    seen_xrefs: set[int],
    seen_xrefs_lock: threading.Lock,
) -> list[dict]:
    """Extract images from a single PDF page, deduplicating by xref.

    ``seen_xrefs`` is shared across page threads; ``seen_xrefs_lock`` makes
    the check-and-claim step atomic so two threads can't both extract the
    same xref. See ``claim_xref_if_drawn_on_page`` for the page-attribution
    logic that fixes images mislabelled with the wrong page number.
    """
    page = doc[page_idx]
    image_list = page.get_images(full=True)
    saved: list[dict] = []

    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]

        if not claim_xref_if_drawn_on_page(page, xref, seen_xrefs, seen_xrefs_lock):
            continue

        try:
            base_image = doc.extract_image(xref)
        except Exception:
            continue

        image_bytes = base_image["image"]
        width = base_image.get("width", 0)
        height = base_image.get("height", 0)

        if len(image_bytes) < MIN_IMAGE_SIZE or width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
            continue
        if min(width, height) > 0 and max(width, height) / min(width, height) > MAX_IMAGE_ASPECT_RATIO:
            continue

        img_ext = base_image.get("ext", "png")
        image_name = f"{pdf_stem}_page{page_idx + 1}_img{img_idx + 1}.png"
        image_path = output_dir / image_name

        if img_ext == "png":
            image_path.write_bytes(image_bytes)
        else:
            pix = fitz.Pixmap(image_bytes)
            if pix.n > 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            pix.save(str(image_path))

        png_bytes = image_path.read_bytes()
        saved.append(
            {
                "image_path": str(image_path),
                "image_name": image_name,
                "file_name": pdf_stem + ".pdf",
                "png_bytes": png_bytes,
                "page": page_idx + 1,
            }
        )

    return saved


def _describe_images_parallel(
    images: list[dict],
    conversation_id: str,
    file_name: str,
    *,
    document_context: str = "",
    page_text: str = "",
) -> list[dict]:
    """Describe a batch of images in parallel using Vision API."""
    if not images:
        return []

    described: list[dict] = []

    def _describe_one(item: dict) -> dict:
        try:
            with trace_step(
                conversation_id,
                file_name,
                "describe_image",
                page_number=item["page"],
                detail=f"image={item['image_name']} size={len(item['png_bytes'])} bytes",
            ):
                description = _describe_image_with_context(
                    item["png_bytes"],
                    document_context=document_context,
                    page_text=page_text,
                    conversation_id=conversation_id,
                )
        except Exception as e:
            logger.warning(f"⚠️ Failed to describe {item['image_name']}: {e}")
            description = f"Image from page {item['page']} of {item['file_name']}"
        return {
            "image_path": item["image_path"],
            "image_name": item["image_name"],
            "file_name": item["file_name"],
            "description": description,
            "page": item["page"],
        }

    with ThreadPoolExecutor(max_workers=_IMAGE_WORKERS) as pool:
        futures = {pool.submit(_describe_one, img): img for img in images}
        for future in as_completed(futures):
            described.append(future.result())

    described.sort(key=lambda x: (x["page"], x["image_path"]))
    return described


def process_pdf_page(
    pdf_path: str,
    page_idx: int,
    total_pages: int,
    output_dir: str,
    conversation_id: str,
    seen_xrefs: set[int],
    worker_id: str | None = None,
    document_context: str = "",
    seen_xrefs_lock: threading.Lock | None = None,
) -> PageResult:
    """Process a single PDF page: extract text, images, chunk, describe.

    This is the unit of work that can run in a thread or Cloud Run Job task.

    ``seen_xrefs_lock`` makes the shared-``seen_xrefs`` check-and-claim atomic
    across page threads. A private lock is created when not supplied (e.g. the
    standalone Cloud Run worker, which runs one task per process).
    """
    if seen_xrefs_lock is None:
        seen_xrefs_lock = threading.Lock()

    p = Path(pdf_path)
    file_name = p.name
    page_num = page_idx + 1
    result = PageResult(page_number=page_num, file_name=file_name)
    start = time.monotonic()

    try:
        doc = fitz.open(str(pdf_path))

        # Step 1: Extract text
        with trace_step(
            conversation_id,
            file_name,
            "extract_page_text",
            page_number=page_num,
            total_pages=total_pages,
            worker_id=worker_id,
        ) as ctx:
            page_text = _extract_page_text(doc, page_idx)
            result.text = page_text
            ctx["detail"] = f"{len(page_text)} chars"

        # Step 1b: OCR fallback for scanned/image-based pages
        if page_needs_ocr(page_text):
            with trace_step(
                conversation_id,
                file_name,
                "ocr_page_fallback",
                page_number=page_num,
                total_pages=total_pages,
                worker_id=worker_id,
            ) as ctx:
                try:
                    ocr_text = ocr_pdf_page(
                        str(pdf_path), page_idx, conversation_id=conversation_id
                    )
                    if ocr_text and len(ocr_text.strip()) > len(page_text.strip()):
                        page_text = _sanitize_text(f"# Page {page_num}\n\n{ocr_text}")
                        result.text = page_text
                        ctx["detail"] = f"OCR extracted {len(ocr_text)} chars"
                        logger.info(f"🔍 OCR page {page_num}: {len(ocr_text)} chars extracted")
                    else:
                        ctx["detail"] = "OCR returned no improvement"
                except Exception as e:
                    ctx["detail"] = f"OCR failed: {e}"
                    logger.warning(f"⚠️ OCR failed for page {page_num}: {e}")

        # Step 2: Extract images from page
        with trace_step(
            conversation_id,
            file_name,
            "extract_page_images",
            page_number=page_num,
            total_pages=total_pages,
            worker_id=worker_id,
        ) as ctx:
            raw_images = _extract_page_images(
                doc,
                page_idx,
                Path(output_dir),
                p.stem,
                seen_xrefs,
                seen_xrefs_lock,
            )
            ctx["detail"] = f"{len(raw_images)} images found"

        doc.close()

        # Step 3: Describe images (parallel API calls)
        if raw_images:
            with trace_step(
                conversation_id,
                file_name,
                "describe_page_images",
                page_number=page_num,
                total_pages=total_pages,
                detail=f"{len(raw_images)} images",
                worker_id=worker_id,
            ):
                described = _describe_images_parallel(
                    raw_images,
                    conversation_id,
                    file_name,
                    document_context=document_context,
                    page_text=page_text,
                )
                result.images = described

        # Step 4: Chunk the page text
        with trace_step(
            conversation_id,
            file_name,
            "chunk_page_text",
            page_number=page_num,
            total_pages=total_pages,
            worker_id=worker_id,
        ) as ctx:
            chunks = split_into_chunks(file_name, page_text, page_num=page_num)
            result.chunks = chunks
            ctx["detail"] = f"{len(chunks)} chunks"

        # Step 5: Generate short page summary for welcome page
        if len(page_text.strip()) > 50:
            # Take ~10% of page text (min 200 chars, max 600 chars) as a summary
            summary_len = max(200, min(600, len(page_text) // 10))
            result.description_summary = page_text[:summary_len].replace("\n", " ").strip()

    except Exception as e:
        result.error = str(e)[:500]
        logger.error(f"❌ Page {page_num} of {file_name} failed: {e}")
        error_uid = log_processing_error(
            conversation_id,
            file_name,
            e,
            step="page_processing",
            page_number=page_num,
            content=result.text or None,
            content_type="text" if result.text else None,
            worker_id=worker_id,
        )
        result.error_uid = error_uid
        log_processing_event(
            conversation_id,
            file_name,
            "page_processing",
            page_number=page_num,
            total_pages=total_pages,
            status="failed",
            error_message=str(e)[:500],
            detail=f"error_uid={error_uid}",
            worker_id=worker_id,
        )

    result.duration_ms = int((time.monotonic() - start) * 1000)
    return result


def process_pdf_parallel(
    pdf_path: str,
    output_dir: str,
    conversation_id: str,
    max_retries: int = 1,
    early_text_timeout_s: float = 5.0,
    early_text_target_pages: int = 100,
    on_early_text: Callable[[str, list[dict]], None] | None = None,
    document_context: str = "",
    on_page_done: Callable[[int, int], None] | None = None,
) -> FileProcessingResult:
    """Process all pages of a PDF in parallel using ThreadPoolExecutor.

    Each page is an independent unit of work. Failed pages are retried once.

    For scanned/OCR PDFs, early text is captured when either:
      - enough pages are processed (early_text_target_pages, capped by total pages), or
      - early_text_timeout_s elapses after at least one page result.
    When on_early_text is provided, it is called immediately after capture,
    allowing welcome message generation in parallel with remaining processing.

    on_page_done(parsed, total) is called after each page completes so callers
    can stream live parsing progress to connected clients.
    """
    p = Path(pdf_path)
    file_name = p.name
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()

    logger.info(f"📄 Processing {file_name}: {total_pages} pages with {_PAGE_WORKERS} workers")

    with trace_step(
        conversation_id,
        file_name,
        "file_processing_started",
        total_pages=total_pages,
        detail=f"{total_pages} pages, {_PAGE_WORKERS} workers",
    ):
        pass  # Just mark the start

    # Shared xref set for cross-page image deduplication. The accompanying
    # lock makes check-and-claim atomic across page threads.
    seen_xrefs: set[int] = set()
    seen_xrefs_lock = threading.Lock()
    worker_id = f"local-{uuid.uuid4().hex[:8]}"

    file_result = FileProcessingResult(
        file_name=file_name,
        file_path=pdf_path,
        total_pages=total_pages,
    )

    page_results: dict[int, PageResult] = {}

    # Phase 1: Process all pages in parallel, capturing early results for welcome message
    early_page_texts: dict[int, str] = {}
    early_page_summaries: dict[int, dict] = {}
    early_text_captured = False
    processing_start = time.monotonic()
    early_target = max(1, min(early_text_target_pages, total_pages))

    with ThreadPoolExecutor(max_workers=_PAGE_WORKERS) as pool:
        futures: dict[Future, int] = {}
        for page_idx in range(total_pages):
            future = pool.submit(
                process_pdf_page,
                pdf_path,
                page_idx,
                total_pages,
                output_dir,
                conversation_id,
                seen_xrefs,
                worker_id,
                document_context,
                seen_xrefs_lock,
            )
            futures[future] = page_idx

        for future in as_completed(futures):
            page_idx = futures[future]
            try:
                result = future.result()
                page_results[page_idx] = result
                # Collect text for early snapshot
                if not early_text_captured:
                    if result.text:
                        early_page_texts[page_idx] = result.text
                    if result.description_summary:
                        early_page_summaries[page_idx] = {
                            "page": result.page_number,
                            "file_name": result.file_name,
                            "summary": result.description_summary,
                        }
            except Exception as e:
                logger.error(f"❌ Page {page_idx + 1} worker crashed: {e}")
                error_uid = log_processing_error(
                    conversation_id,
                    file_name,
                    e,
                    step="page_worker_crash",
                    page_number=page_idx + 1,
                    worker_id=worker_id,
                )
                page_results[page_idx] = PageResult(
                    page_number=page_idx + 1,
                    file_name=file_name,
                    error=str(e)[:500],
                    error_uid=error_uid,
                )

            if on_page_done is not None:
                try:
                    on_page_done(len(page_results), total_pages)
                except Exception as e:
                    logger.warning(f"⚠️ on_page_done callback failed: {e}")

            # Snapshot early text once target pages are processed, or timeout is reached.
            # Fire callback so caller can start welcome message generation immediately.
            if (
                not early_text_captured
                and early_page_texts
                and (
                    len(early_page_texts) >= early_target
                    or (time.monotonic() - processing_start) >= early_text_timeout_s
                )
            ):
                early_text_captured = True
                sorted_texts = [
                    early_page_texts[idx] for idx in sorted(early_page_texts.keys())
                ]
                file_result.early_text = "\n\n".join(sorted_texts)
                sorted_summaries = [
                    early_page_summaries[idx]
                    for idx in sorted(early_page_summaries.keys())
                ]
                logger.info(
                    f"⏱️  Early text snapshot: {len(early_page_texts)} pages, "
                    f"{len(file_result.early_text)} chars "
                    f"(target={early_target}, after {time.monotonic() - processing_start:.1f}s)"
                )
                if on_early_text:
                    try:
                        on_early_text(file_result.early_text, sorted_summaries)
                    except Exception as e:
                        logger.warning(f"⚠️ on_early_text callback failed: {e}")

    # If all pages completed before timeout, early_text = full_text (set below).
    # Fire callback if it hasn't been fired yet.
    if not early_text_captured and early_page_texts:
        sorted_texts = [early_page_texts[idx] for idx in sorted(early_page_texts.keys())]
        file_result.early_text = "\n\n".join(sorted_texts)
        if on_early_text:
            sorted_summaries = [
                early_page_summaries[idx]
                for idx in sorted(early_page_summaries.keys())
                if idx in early_page_summaries
            ]
            try:
                on_early_text(file_result.early_text, sorted_summaries)
            except Exception as e:
                logger.warning(f"⚠️ on_early_text callback failed: {e}")

    # Phase 2: Retry failed pages (max once)
    failed_pages = [idx for idx, r in page_results.items() if r.error]
    if failed_pages and max_retries > 0:
        logger.info(f"🔄 Retrying {len(failed_pages)} failed pages...")
        for page_idx in failed_pages:
            log_processing_event(
                conversation_id,
                file_name,
                "page_retry",
                page_number=page_idx + 1,
                total_pages=total_pages,
                status="retrying",
                detail=f"retry 1 of {max_retries}",
            )
            try:
                result = process_pdf_page(
                    pdf_path,
                    page_idx,
                    total_pages,
                    output_dir,
                    conversation_id,
                    seen_xrefs,
                    worker_id,
                    document_context,
                    seen_xrefs_lock,
                )
                if not result.error:
                    page_results[page_idx] = result
                    logger.info(f"✅ Page {page_idx + 1} succeeded on retry")
            except Exception as e:
                logger.error(f"❌ Page {page_idx + 1} retry failed: {e}")
                log_processing_error(
                    conversation_id,
                    file_name,
                    e,
                    step="page_retry",
                    page_number=page_idx + 1,
                    worker_id=worker_id,
                    retry_count=1,
                )

    # Aggregate results in page order
    for page_idx in sorted(page_results.keys()):
        pr = page_results[page_idx]
        file_result.page_results.append(pr)
        if not pr.error:
            file_result.all_chunks.extend(pr.chunks)
            file_result.all_images.extend(pr.images)
            file_result.full_text += pr.text + "\n\n"
        else:
            file_result.errors.append(
                {
                    "page": pr.page_number,
                    "error": pr.error,
                    "error_uid": pr.error_uid,
                }
            )

    # Log summary
    succeeded = sum(1 for r in file_result.page_results if not r.error)
    log_processing_event(
        conversation_id,
        file_name,
        "file_processing_completed",
        total_pages=total_pages,
        status="completed",
        detail=(
            f"{succeeded}/{total_pages} pages OK, "
            f"{len(file_result.all_chunks)} chunks, "
            f"{len(file_result.all_images)} images"
            f"{f', {len(file_result.errors)} errors' if file_result.errors else ''}"
        ),
    )

    return file_result


def process_standalone_file(
    file_path: str,
    conversation_id: str,
) -> FileProcessingResult:
    """Process a non-PDF file (image, docx, txt, etc.) with telemetry."""
    p = Path(file_path)
    file_name = p.name
    suffix = p.suffix.lower()

    file_result = FileProcessingResult(
        file_name=file_name,
        file_path=file_path,
        total_pages=1,
    )

    with trace_step(
        conversation_id,
        file_name,
        "file_processing_started",
        detail=f"type={suffix}",
    ):
        pass

    try:
        # Extract text (includes image description for image files)
        with trace_step(
            conversation_id,
            file_name,
            "extract_text",
            detail=f"type={suffix}",
        ) as ctx:
            text = extract_text(file_path, conversation_id=conversation_id)
            file_result.full_text = text
            ctx["detail"] = f"{len(text)} chars"

        # For images, also register as image entry
        if suffix in IMAGE_EXTENSIONS:
            file_result.all_images.append(
                {
                    "image_path": str(p),
                    "image_name": p.name,
                    "file_name": p.name,
                    "description": text,
                    "page": None,
                }
            )

        # Chunk text
        with trace_step(
            conversation_id,
            file_name,
            "chunk_text",
            detail=f"type={suffix}",
        ) as ctx:
            chunks = split_into_chunks(file_name, text)
            file_result.all_chunks = chunks
            ctx["detail"] = f"{len(chunks)} chunks"

        page_result = PageResult(
            page_number=1,
            file_name=file_name,
            chunks=chunks,
            text=text,
        )
        file_result.page_results.append(page_result)

    except Exception as e:
        error_uid = log_processing_error(
            conversation_id,
            file_name,
            e,
            step="file_processing",
            page_number=1,
            content=file_result.full_text or None,
            content_type="text" if file_result.full_text else None,
        )
        file_result.errors.append(
            {"page": 1, "error": str(e)[:500], "error_uid": error_uid}
        )
        log_processing_event(
            conversation_id,
            file_name,
            "file_processing",
            status="failed",
            error_message=str(e)[:500],
            detail=f"error_uid={error_uid}",
        )

    log_processing_event(
        conversation_id,
        file_name,
        "file_processing_completed",
        status="completed",
        detail=f"{len(file_result.all_chunks)} chunks, {len(file_result.all_images)} images",
    )

    return file_result
