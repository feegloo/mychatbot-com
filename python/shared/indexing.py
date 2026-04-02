from __future__ import annotations

import logging

from .extractors import extract_many
from .chunkers import split_into_chunks
from .suggested_questions import suggest_questions_from_chunks
from .vector_store import upsert_chunks

logger = logging.getLogger(__name__)


def index_documents(conversation_id: str, collection_name: str, file_paths: list[str]) -> dict:
    logger.info(f"📁 Starting indexing of {len(file_paths)} file(s) for collection: {collection_name}")
    extracted = extract_many(file_paths)
    logger.info(f"✅ Extracted {len(extracted)} document(s)")

    all_chunks = []
    for document in extracted:
        logger.info(f"🔪 Chunking: {document['file_name']}")
        chunks = split_into_chunks(document["file_name"], document["text"])
        logger.info(f"   → Created {len(chunks)} chunks")
        all_chunks.extend(chunks)

    logger.info(f"📦 Upserting {len(all_chunks)} chunks to vector store...")
    upsert_result = upsert_chunks(
        collection_name=collection_name,
        conversation_id=conversation_id,
        chunks=all_chunks,
    )
    logger.info(f"✅ Indexing complete")

    suggested_questions = suggest_questions_from_chunks([chunk.text for chunk in all_chunks])
    logger.info(f"💡 Generated {len(suggested_questions) if suggested_questions else 0} suggested questions")

    return {
        "conversation_id": conversation_id,
        "collection_name": collection_name,
        "file_count": len(file_paths),
        "chunk_count": len(all_chunks),
        "suggested_questions": suggested_questions,
        **upsert_result,
    }
