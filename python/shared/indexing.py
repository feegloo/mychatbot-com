from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from .chapters import (
    build_page_to_chapter_map,
    chapters_to_serializable,
    detect_chapters,
)
from .chunkers import Chunk, split_into_chunks
from .cloud_dispatch import dispatch_page_jobs, is_cloud_mode
from .describe import DescribeResult, describe_documents
from .lang_detect import detect_language
from .metadata import extract_metadata_many
from .page_worker import FileProcessingResult, process_pdf_parallel, process_standalone_file
from .suggested_questions import suggest_questions_from_chunks
from .telemetry import log_processing_event, trace_step
from .vector_store import upsert_chunks

logger = logging.getLogger(__name__)

# Thread pool for background welcome message generation (started early via callback)
_describe_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="early-describe")
_EARLY_WELCOME_PAGE_TARGET = 100


def _image_chunks(images: list[dict], file_name: str) -> list[Chunk]:
    """Convert extracted image dicts into Chunk objects.

    The chunk text is the vision-model description so it gets embedded
    alongside regular text chunks in the same vector space.
    """
    chunks = []
    for idx, img in enumerate(images):
        # Store image_path relative to storage root (conversationId/filename.png)
        abs_path = Path(img["image_path"])
        # The image sits in storage/<conversationId>/<image_name>
        # We store just the filename; the backend route resolves the rest
        image_name = abs_path.name

        page = img["page"]
        section = f"Image (page {page})" if page is not None else "Image"
        chunks.append(
            Chunk(
                chunk_id=f"{Path(img['file_name']).stem}_img_{idx}",
                file_name=img["file_name"],
                text=img["description"],
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
    on_progress: "Callable[[str, dict], None] | None" = None,
) -> dict:
    logger.info(
        f"📁 Starting indexing of {len(file_paths)} file(s) for collection: {collection_name}"
    )

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
        early_describe_future = _describe_pool.submit(
            describe_documents,
            early_extracted,
            [],
            language=early_lang,
            file_metadata=file_metadata,
            page_summaries=early_summaries or None,
            file_names=file_name_list,
            file_types=file_types,
        )

    for file_path in file_paths:
        p = Path(file_path)
        suffix = p.suffix.lower()

        if suffix == ".pdf":
            output_dir = str(p.parent)
            if is_cloud_mode():
                # Cloud Run Jobs: dispatch per-page containers for image extraction.
                # Always chunk text locally as fallback (cloud workers may fail).
                logger.info(f"☁️ Cloud mode: dispatching Cloud Run Jobs for {p.name}")
                import fitz

                from .extractors import _reflow_pdf_text, _sanitize_text, ocr_pdf_page, page_needs_ocr

                doc = fitz.open(file_path)
                total_pages = len(doc)
                early_target = max(1, min(_EARLY_WELCOME_PAGE_TARGET, total_pages))

                # Extract + chunk text locally so all_chunks is always populated
                page_texts: list[str] = []
                local_chunks: list[Chunk] = []
                early_page_texts: list[str] = []
                early_page_summaries: list[dict] = []
                for page_idx in range(total_pages):
                    try:
                        page = doc[page_idx]
                        raw = page.get_text() or ""
                        reflowed = _reflow_pdf_text(raw.strip())
                        page_text = _sanitize_text(f"# Page {page_idx + 1}\n\n{reflowed}")
                        # OCR fallback for scanned/image-based pages
                        if page_needs_ocr(page_text):
                            try:
                                ocr_text = ocr_pdf_page(file_path, page_idx)
                                if ocr_text and len(ocr_text.strip()) > len(page_text.strip()):
                                    page_text = _sanitize_text(
                                        f"# Page {page_idx + 1}\n\n{ocr_text}"
                                    )
                                    logger.info(
                                        f"🔍 OCR page {page_idx + 1}: "
                                        f"{len(ocr_text)} chars extracted"
                                    )
                            except Exception as ocr_err:
                                logger.warning(
                                    f"⚠️ OCR failed for page {page_idx + 1}: {ocr_err}"
                                )
                        page_texts.append(page_text)
                        if page_text:
                            early_page_texts.append(page_text)
                            if len(page_text.strip()) > 50:
                                summary_len = max(200, min(600, len(page_text) // 10))
                                early_page_summaries.append(
                                    {
                                        "page": page_idx + 1,
                                        "file_name": p.name,
                                        "summary": page_text[:summary_len].replace("\n", " ").strip(),
                                    }
                                )
                        if early_describe_future is None and len(early_page_texts) >= early_target:
                            _on_early_text("\n\n".join(early_page_texts), early_page_summaries)
                            logger.info(
                                f"⏱️  Cloud mode early welcome started after "
                                f"{len(early_page_texts)}/{total_pages} pages"
                            )
                        # Chunk locally so we always have text chunks even if cloud workers fail
                        chunks = split_into_chunks(p.name, page_text, page_num=page_idx + 1)
                        local_chunks.extend(chunks)
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Local text extraction failed for page {page_idx + 1}: {e}"
                        )
                        page_texts.append("")
                doc.close()

                # Small PDFs may complete before reaching early target.
                if early_describe_future is None and early_page_texts:
                    _on_early_text("\n\n".join(early_page_texts), early_page_summaries)
                    logger.info(
                        f"⏱️  Cloud mode early welcome started after full local pre-pass "
                        f"({len(early_page_texts)}/{total_pages} pages)"
                    )

                full_text = "\n\n".join(page_texts)
                logger.info(
                    f"📄 Extracted {len(full_text)} chars, "
                    f"{len(local_chunks)} local chunks for {p.name}"
                )

                cloud_results = dispatch_page_jobs(
                    pdf_gcs_uri=file_path,
                    total_pages=total_pages,
                    output_dir=output_dir,
                    conversation_id=conversation_id,
                    collection_name=collection_name,
                )
                # Build FileProcessingResult with local text + chunks
                result = FileProcessingResult(
                    file_name=p.name,
                    file_path=file_path,
                    total_pages=total_pages,
                )
                result.full_text = full_text
                result.all_chunks = local_chunks
                for cr in cloud_results:
                    if cr["status"] != "completed":
                        result.errors.append(
                            {"page": cr["page"], "error": cr.get("error", "unknown")}
                        )
            else:
                # Local mode (default): parallel threads
                result = process_pdf_parallel(
                    file_path, output_dir, conversation_id,
                    on_early_text=_on_early_text,
                )
        else:
            result = process_standalone_file(file_path, conversation_id)

        file_results.append(result)

    # Aggregate chunks, images, text across all files
    all_chunks: list[Chunk] = []
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

        if detected_language is None and fr.full_text:
            detected_language = detect_language(fr.full_text[:2000])

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

        # If early describe was started during processing, use its result.
        # Otherwise, start a fresh describe with the full extracted text.
        if early_describe_future is not None:
            logger.info("⏱️  Using early welcome message (started during page processing)")
            describe_future = early_describe_future
        else:
            describe_future = pool.submit(
                describe_documents,
                extracted,
                all_images,
                language=detected_language,
                file_metadata=file_metadata,
                page_summaries=all_page_summaries or None,
                file_names=file_name_list,
                file_types=file_types,
            )

        # Get welcome message + suggested questions ASAP — don't wait for upsert
        describe_result: DescribeResult = describe_future.result()
        welcome_message = describe_result["welcome_message"]
        suggested_questions = describe_result["suggested_questions"]

        # Emit welcome_message event immediately so the frontend can show it
        if on_progress and welcome_message:
            on_progress("welcome_message", {
                "welcome_message": welcome_message,
                "suggested_questions": suggested_questions,
                "file_metadata": file_metadata or {},
            })

        upsert_result = upsert_future.result()

    # If describe didn't produce questions (e.g. split+synthesize for very large docs),
    # fall back to the separate suggest_questions_from_chunks call.
    if not suggested_questions and chunk_texts:
        logger.info("💡 Generating suggested prompts via fallback (separate call)...")
        with trace_step(conversation_id, "*", "generate_suggested_questions"):
            suggested_questions = suggest_questions_from_chunks(
                chunk_texts,
                language=detected_language,
                description=welcome_message or "",
                file_names=file_name_list,
                file_types=file_types,
                welcome_message=welcome_message or "",
            )
    else:
        logger.info("💡 Suggested questions generated inline with welcome message")

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
        "chunk_count": len(all_chunks),
        "suggested_questions": suggested_questions,
        "welcome_message": welcome_message,
        "detected_language": detected_language,
        "file_metadata": file_metadata,
        "processing_errors": all_errors if all_errors else None,
        **upsert_result,
    }

    if on_progress:
        on_progress("complete", result)

    return result
