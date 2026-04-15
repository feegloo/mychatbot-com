from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .extractors import extract_many
from .chunkers import Chunk, split_into_chunks
from .suggested_questions import suggest_questions_from_chunks
from .describe import describe_documents
from .lang_detect import detect_language
from .vector_store import upsert_chunks
from .metadata import extract_metadata_many

logger = logging.getLogger(__name__)


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
        chunks.append(Chunk(
            chunk_id=f"{Path(img['file_name']).stem}_img_{idx}",
            file_name=img["file_name"],
            text=img["description"],
            section=section,
            page=page,
            metadata={
                "is_image": True,
                "image_name": image_name,
            },
        ))
    return chunks


def index_documents(conversation_id: str, collection_name: str, file_paths: list[str]) -> dict:
    logger.info(f"📁 Starting indexing of {len(file_paths)} file(s) for collection: {collection_name}")

    # Extract file metadata (EXIF, PDF info, etc.)
    logger.info(f"📋 Extracting file metadata...")
    file_metadata = extract_metadata_many(file_paths)

    extracted, images = extract_many(file_paths)
    logger.info(f"✅ Extracted {len(extracted)} document(s), {len(images)} image(s)")

    all_chunks = []
    detected_language = None
    for document in extracted:
        logger.info(f"🔪 Chunking: {document['file_name']}")
        chunks = split_into_chunks(document["file_name"], document["text"])
        logger.info(f"   → Created {len(chunks)} chunks")
        all_chunks.extend(chunks)
        # Detect language from the first document's text (first 2000 chars)
        if detected_language is None and document["text"]:
            detected_language = detect_language(document["text"][:2000])

    # Add image chunks (description text gets embedded alongside regular chunks)
    if images:
        img_chunks = _image_chunks(images, "")
        logger.info(f"🖼️  Adding {len(img_chunks)} image chunks")
        all_chunks.extend(img_chunks)

    # Run vector upsert and description in parallel first (both are IO-bound API calls)
    logger.info(f"📦 Upserting {len(all_chunks)} chunks + generating description in parallel...")
    chunk_texts = [chunk.text for chunk in all_chunks]
    with ThreadPoolExecutor(max_workers=2) as pool:
        upsert_future = pool.submit(
            upsert_chunks,
            collection_name=collection_name,
            conversation_id=conversation_id,
            chunks=all_chunks,
        )
        describe_future = pool.submit(
            describe_documents,
            extracted,
            images,
            language=detected_language,
            file_metadata=file_metadata,
        )
        upsert_result = upsert_future.result()
        welcome_message = describe_future.result()

    # Now generate suggested questions with the description for contextual prompts
    logger.info(f"💡 Generating suggested prompts (with description context)...")

    # Determine file types for contextual prompts
    file_types = {}
    for fp in file_paths:
        p = Path(fp)
        suffix = p.suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}:
            file_types[p.name] = "image"
        elif suffix == ".pdf":
            file_types[p.name] = "pdf"
        else:
            file_types[p.name] = "document"

    suggested_questions = suggest_questions_from_chunks(
        chunk_texts,
        language=detected_language,
        description=welcome_message or "",
        file_names=[Path(fp).name for fp in file_paths],
        file_types=file_types,
        welcome_message=welcome_message or "",
    )

    logger.info(f"✅ Indexing complete")
    logger.info(f"💡 Generated {len(suggested_questions) if suggested_questions else 0} suggested questions (lang={detected_language})")
    logger.info(f"👋 Welcome message: {welcome_message[:100]}..." if welcome_message else "👋 No welcome message generated")

    return {
        "conversation_id": conversation_id,
        "collection_name": collection_name,
        "file_count": len(file_paths),
        "chunk_count": len(all_chunks),
        "suggested_questions": suggested_questions,
        "welcome_message": welcome_message,
        "detected_language": detected_language,
        "file_metadata": file_metadata,
        **upsert_result,
    }
