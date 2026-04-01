from __future__ import annotations

from .extractors import extract_many
from .chunkers import split_into_chunks
from .suggested_questions import suggest_questions_from_chunks
from .vector_store import upsert_chunks


def index_documents(conversation_id: str, collection_name: str, file_paths: list[str]) -> dict:
    extracted = extract_many(file_paths)

    all_chunks = []
    for document in extracted:
        chunks = split_into_chunks(document["file_name"], document["text"])
        all_chunks.extend(chunks)

    upsert_result = upsert_chunks(
        collection_name=collection_name,
        conversation_id=conversation_id,
        chunks=all_chunks,
    )

    suggested_questions = suggest_questions_from_chunks([chunk.text for chunk in all_chunks])

    return {
        "conversation_id": conversation_id,
        "collection_name": collection_name,
        "file_count": len(file_paths),
        "chunk_count": len(all_chunks),
        "suggested_questions": suggested_questions,
        **upsert_result,
    }
