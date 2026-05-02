"""Streaming PDF page processor with incremental Chroma upsert.

This replaces the serial-loop behaviour in cloud mode for large OCR-heavy
PDFs (e.g. the 611-page Arabic Mathnawi). The algorithm:

  1. Iterate every page of the PDF in order.
  2. Extract native text with fitz. If the text is too sparse, submit the
     page to a thread pool for GPT-Vision OCR (non-blocking).
  3. As each page (either native or OCR'd) becomes ready — possibly out of
     order — call ``on_page_ready(page_nr, text, source)``. Callers use this
     to:
        • persist the page text to ``pdf_pages``,
        • chunk and upsert embeddings to Chroma, and
        • emit a live progress event.
  4. Return ``StreamingPdfResult`` with aggregated text + chunks for
     downstream steps (welcome regen, chapter enrichment, etc.).

Pure function shape: the processor knows nothing about Chroma or Postgres.
All side effects are wired via callbacks so this module is test-friendly.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import fitz

from .chunkers import Chunk
from .extractors import _reflow_pdf_text, _sanitize_text, ocr_pdf_page, page_needs_ocr

logger = logging.getLogger(__name__)

PageSource = Literal["raw", "ocr", "failed"]

# Concurrency cap for OCR: OpenAI Vision is rate-limited and each call costs
# a few cents. 8 keeps throughput high without hammering rate limits for the
# 611-page worst case.
_OCR_WORKERS = 8

# If a page passes the basic page_needs_ocr check (has some text) but still has
# fewer than this many content chars AND the page contains large rendered images,
# force a full-page OCR pass. This catches PDFs where the majority of the page
# content is embedded as inline bitmaps or drawn graphics — visible when rendered
# but missing from native text extraction (e.g. scanned newspaper pages that mix
# image-rendered article text with a small vector-text caption box).
_MIN_TEXT_CHARS_WITH_IMAGES = 500

# Minimum rendered image area in PDF points² to consider an image "significant".
# ~70×70 pts ≈ 100×100 px at 100 DPI — larger than decorative icons or rule lines.
_MIN_RENDERED_IMAGE_AREA_PTS2 = 5_000


def _page_has_significant_images(page: fitz.Page) -> bool:
    """Return True when the page has at least one large visually-rendered image.

    Skips soft-mask (smask) images, which are alpha channels for other images
    and are never rendered independently. Uses get_image_rects to confirm the
    image is actually drawn on this specific page rather than merely inherited
    from a parent resource dictionary.
    """
    # Collect xrefs that serve as soft masks for other images so we can skip them.
    smask_xrefs: set[int] = {
        img[1] for img in page.get_images(full=True) if img[1] != 0
    }
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        if xref in smask_xrefs:
            continue
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for rect in rects:
            area = abs(rect.x1 - rect.x0) * abs(rect.y1 - rect.y0)
            if area >= _MIN_RENDERED_IMAGE_AREA_PTS2:
                return True
    return False


@dataclass
class PageOutcome:
    page_nr: int  # 1-based
    text: str
    source: PageSource
    error: str | None = None


@dataclass
class StreamingPdfResult:
    file_path: str
    file_name: str
    total_pages: int
    pages: list[PageOutcome] = field(default_factory=list)
    ocr_page_count: int = 0
    failed_page_count: int = 0

    @property
    def full_text(self) -> str:
        """Concatenate successful page text in order, skipping failures.

        Each page is prefixed with a ``# Page N`` marker so downstream
        consumers (notably ``describe_documents``) can auto-detect page
        boundaries and route very large OCR'd books through the chapter /
        page-range compaction strategy instead of attempting a single
        whole-book prompt that would exceed the 300k TPM request cap.
        """
        parts: list[str] = []
        for p in sorted(self.pages, key=lambda x: x.page_nr):
            if p.source == "failed" or not p.text.strip():
                continue
            parts.append(f"# Page {p.page_nr}\n{p.text}")
        return "\n\n".join(parts)

    @property
    def is_heavy_ocr(self) -> bool:
        """Whether at least 40% of pages required OCR.

        Used to decide if the initial "fast" welcome message should be
        regenerated against the full parsed text once indexing finishes.
        """
        if self.total_pages == 0:
            return False
        return (self.ocr_page_count / self.total_pages) >= 0.4


def process_pdf_streaming(
    pdf_path: str,
    *,
    conversation_id: str,
    on_page_ready: Callable[[PageOutcome], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    ocr_workers: int = _OCR_WORKERS,
) -> StreamingPdfResult:
    """Parse a PDF page-by-page, OCR'ing in parallel where needed.

    Parameters
    ----------
    pdf_path:
        Absolute path to the PDF on local disk.
    conversation_id:
        Passed to the OCR call for per-conversation prompt-history logging.
    on_page_ready:
        Called exactly once per page as soon as its text (native, OCR'd, or
        failed) is available. May be invoked from worker threads, so the
        callback must be thread-safe. Upsertion to Chroma + DB persistence
        belongs here.
    on_progress:
        Called after each ``on_page_ready`` with ``(parsed, total)`` for
        streaming progress events to the frontend.
    ocr_workers:
        Max concurrent OCR calls to OpenAI Vision. Defaults to
        ``_OCR_WORKERS``.
    """
    p = Path(pdf_path)
    file_name = p.name

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    result = StreamingPdfResult(
        file_path=str(pdf_path), file_name=file_name, total_pages=total_pages
    )
    # Lock protects ``result.pages`` / counters since callbacks fire from
    # worker threads.
    lock = threading.Lock()
    parsed = 0

    def _emit(outcome: PageOutcome) -> None:
        nonlocal parsed
        with lock:
            result.pages.append(outcome)
            if outcome.source == "ocr":
                result.ocr_page_count += 1
            elif outcome.source == "failed":
                result.failed_page_count += 1
            parsed += 1
            current = parsed
        # Fire callbacks outside the lock so Chroma upsert / Postgres insert
        # don't serialize OCR thread completions.
        if on_page_ready is not None:
            try:
                on_page_ready(outcome)
            except Exception as e:
                logger.warning(
                    f"⚠️ on_page_ready callback failed for p.{outcome.page_nr}: {e}"
                )
        if on_progress is not None:
            with contextlib.suppress(Exception):
                on_progress(current, total_pages)

    start = time.monotonic()
    logger.info(
        f"📄 Streaming PDF {file_name}: {total_pages} pages (OCR workers={ocr_workers})"
    )

    # Phase 1 — cheap extraction pass in the main thread; queue OCR work
    # for any page whose native text is sparse.
    ocr_jobs: dict[Future, int] = {}
    pool = ThreadPoolExecutor(max_workers=ocr_workers, thread_name_prefix="ocr-page")
    try:
        for page_idx in range(total_pages):
            page_nr = page_idx + 1
            try:
                page = doc[page_idx]
                raw = (page.get_text() or "").strip()
                native_text = _sanitize_text(
                    f"# Page {page_nr}\n\n{_reflow_pdf_text(raw)}"
                )
            except Exception as e:
                logger.warning(f"⚠️ Native extract failed on p.{page_nr}: {e}")
                native_text = ""

            if native_text and not page_needs_ocr(native_text):
                # Secondary check: the page may have passed the basic sparse-text
                # threshold but still contain significant image content whose
                # surrounding text was not captured by native extraction (e.g. a
                # scanned article where only a small caption box has vector text).
                # In that case render the full page via GPT-Vision OCR.
                stripped_len = len(native_text.split("\n\n", 1)[-1].strip())
                if (
                    stripped_len < _MIN_TEXT_CHARS_WITH_IMAGES
                    and _page_has_significant_images(page)
                ):
                    logger.info(
                        "🔍 p.%d: %d text chars with large images → forcing full-page OCR",
                        page_nr,
                        stripped_len,
                    )
                else:
                    _emit(PageOutcome(page_nr=page_nr, text=native_text, source="raw"))
                    continue

            # Queue OCR; keep native_text as fallback if OCR fails.
            future = pool.submit(
                _ocr_page_job, pdf_path, page_idx, conversation_id, native_text
            )
            ocr_jobs[future] = page_nr

        # Phase 2 — drain OCR results as they complete (may arrive out of order).
        from concurrent.futures import as_completed

        for future in as_completed(ocr_jobs):
            page_nr = ocr_jobs[future]
            try:
                text, source, err = future.result()
            except Exception as e:
                text, source, err = "", "failed", str(e)[:500]
            _emit(
                PageOutcome(page_nr=page_nr, text=text, source=source, error=err)
            )
    finally:
        pool.shutdown(wait=True)
        doc.close()

    elapsed = time.monotonic() - start
    logger.info(
        f"✅ Streamed {file_name}: {total_pages} pages "
        f"({result.ocr_page_count} OCR, {result.failed_page_count} failed) in {elapsed:.1f}s"
    )
    return result


def _ocr_page_job(
    pdf_path: str, page_idx: int, conversation_id: str, native_fallback: str
) -> tuple[str, PageSource, str | None]:
    """Run OCR for a single page. Returns (text, source, error)."""
    page_nr = page_idx + 1
    try:
        ocr_text = ocr_pdf_page(pdf_path, page_idx, conversation_id=conversation_id)
    except Exception as e:
        msg = str(e)[:500]
        logger.warning(f"⚠️ OCR failed on p.{page_nr}: {msg}")
        if native_fallback.strip():
            # Keep whatever sparse native text we had rather than losing the page.
            return native_fallback, "raw", msg
        return "", "failed", msg

    if not ocr_text or not ocr_text.strip():
        if native_fallback.strip():
            return native_fallback, "raw", None
        return "", "failed", "empty OCR result"

    from .extractors import _sanitize_text  # local import avoids cycle at load

    final = _sanitize_text(f"# Page {page_nr}\n\n{ocr_text}")
    return final, "ocr", None


def chunks_for_page(
    file_name: str, page_nr: int, text: str, chapter_nr: int | None = None
) -> list[Chunk]:
    """Split a single page's text into Chunk objects, tagged with chapter."""
    from .chunkers import split_into_chunks  # local import avoids cycle

    chunks = split_into_chunks(file_name, text, page_num=page_nr)
    if chapter_nr is not None:
        for c in chunks:
            c.metadata["chapter_number"] = chapter_nr
    return chunks
