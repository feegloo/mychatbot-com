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
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from .chunkers import Chunk, split_into_chunks
from .extractors import (
    IMAGE_EXTENSIONS,
    MIN_IMAGE_DIM,
    MIN_IMAGE_SIZE,
    _describe_image,
    _reflow_pdf_text,
    _sanitize_text,
    extract_text,
)
from .telemetry import log_processing_event, trace_step

logger = logging.getLogger(__name__)


def _read_worker_count(
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    # Invalid/non-numeric values use `default`.
    # Numeric out-of-range values are clamped to [minimum, maximum].
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
    errors: list[dict] = field(default_factory=list)


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
) -> list[dict]:
    """Extract images from a single PDF page, deduplicating by xref."""
    page = doc[page_idx]
    image_list = page.get_images(full=True)
    saved: list[dict] = []

    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        try:
            base_image = doc.extract_image(xref)
        except Exception:
            continue

        image_bytes = base_image["image"]
        width = base_image.get("width", 0)
        height = base_image.get("height", 0)

        if len(image_bytes) < MIN_IMAGE_SIZE or width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
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
    images: list[dict], conversation_id: str, file_name: str
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
                description = _describe_image(item["png_bytes"])
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
) -> PageResult:
    """Process a single PDF page: extract text, images, chunk, describe.

    This is the unit of work that can run in a thread or Cloud Run Job task.
    """
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
                described = _describe_images_parallel(raw_images, conversation_id, file_name)
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
        log_processing_event(
            conversation_id,
            file_name,
            "page_processing",
            page_number=page_num,
            total_pages=total_pages,
            status="failed",
            error_message=str(e)[:500],
            worker_id=worker_id,
        )

    result.duration_ms = int((time.monotonic() - start) * 1000)
    return result


def process_pdf_parallel(
    pdf_path: str,
    output_dir: str,
    conversation_id: str,
    max_retries: int = 1,
) -> FileProcessingResult:
    """Process all pages of a PDF in parallel using ThreadPoolExecutor.

    Each page is an independent unit of work. Failed pages are retried once.
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

    # Shared xref set for cross-page image deduplication (thread-safe via GIL for set.add)
    seen_xrefs: set[int] = set()
    worker_id = f"local-{uuid.uuid4().hex[:8]}"

    file_result = FileProcessingResult(
        file_name=file_name,
        file_path=pdf_path,
        total_pages=total_pages,
    )

    page_results: dict[int, PageResult] = {}

    # Phase 1: Process all pages in parallel
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
            )
            futures[future] = page_idx

        for future in as_completed(futures):
            page_idx = futures[future]
            try:
                result = future.result()
                page_results[page_idx] = result
            except Exception as e:
                logger.error(f"❌ Page {page_idx + 1} worker crashed: {e}")
                page_results[page_idx] = PageResult(
                    page_number=page_idx + 1,
                    file_name=file_name,
                    error=str(e)[:500],
                )

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
                )
                if not result.error:
                    page_results[page_idx] = result
                    logger.info(f"✅ Page {page_idx + 1} succeeded on retry")
            except Exception as e:
                logger.error(f"❌ Page {page_idx + 1} retry failed: {e}")

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
            text = extract_text(file_path)
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
        file_result.errors.append({"page": 1, "error": str(e)[:500]})
        log_processing_event(
            conversation_id,
            file_name,
            "file_processing",
            status="failed",
            error_message=str(e)[:500],
        )

    log_processing_event(
        conversation_id,
        file_name,
        "file_processing_completed",
        status="completed",
        detail=f"{len(file_result.all_chunks)} chunks, {len(file_result.all_images)} images",
    )

    return file_result
