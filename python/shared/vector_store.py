from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

from .config import get_settings
from .chunkers import Chunk

logger = logging.getLogger(__name__)

# Module-level caches — avoids re-creating expensive clients each call
_chroma_client = None
_openai_client = None

EMBED_BATCH_SIZE = 2048  # OpenAI API limit per request
EMBED_MAX_WORKERS = 4    # Parallel embedding requests for very large batches
CHROMA_BATCH_SIZE = 5000  # Chroma add() limit is ~5461


def get_client():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    settings = get_settings()

    if settings.chroma_mode == "cloud":
        _chroma_client = chromadb.CloudClient(
            api_key=settings.chroma_api_key,
            tenant=settings.chroma_tenant,
            database=settings.chroma_database,
        )
    elif settings.chroma_mode == "http":
        _chroma_client = chromadb.HttpClient(host=settings.chroma_http_host.replace("http://", "").replace("https://", "").split(":")[0],
                                   port=int(settings.chroma_http_host.rsplit(":", 1)[-1]))
    else:
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir, settings=ChromaSettings(anonymized_telemetry=False))
    return _chroma_client


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    settings = get_settings()
    _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts using OpenAI API directly (bypasses LangChain/tiktoken overhead)."""
    client = _get_openai_client()
    settings = get_settings()

    if len(texts) <= EMBED_BATCH_SIZE:
        response = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    # For very large batches, split and parallelize
    all_vectors: list[list[float] | None] = [None] * len(texts)
    batches = [(i, texts[i:i + EMBED_BATCH_SIZE]) for i in range(0, len(texts), EMBED_BATCH_SIZE)]

    def _embed_batch(start_idx: int, batch: list[str]):
        resp = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=batch,
        )
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        for j, item in enumerate(sorted_data):
            all_vectors[start_idx + j] = item.embedding

    logger.info(f"⚡ Embedding {len(texts)} texts in {len(batches)} parallel batches")
    with ThreadPoolExecutor(max_workers=EMBED_MAX_WORKERS) as pool:
        futures = [pool.submit(_embed_batch, start, batch) for start, batch in batches]
        for f in futures:
            f.result()

    return all_vectors


def collection_count(collection_name: str) -> int:
    """Return the number of documents in a collection (0 if it doesn't exist)."""
    client = get_client()
    try:
        collection = client.get_or_create_collection(name=collection_name)
        return collection.count()
    except Exception:
        return 0


def upsert_chunks(collection_name: str, conversation_id: str, chunks: list[Chunk]) -> dict:
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)

    ids = [chunk.chunk_id for chunk in chunks]
    docs = [chunk.text for chunk in chunks]

    logger.info(f"⚡ Embedding {len(docs)} chunks...")
    vectors = embed_texts(docs)
    logger.info(f"✅ Embedding complete")

    metadatas = []
    for chunk in chunks:
        metadata = {
            "conversation_id": conversation_id,
            "file_name": chunk.file_name,
            "section": chunk.section or "",
            "page": chunk.page if chunk.page is not None else -1,
            **chunk.metadata,
        }
        metadatas.append(metadata)

    # Batch upsert to respect Chroma's per-call limits
    for i in range(0, len(ids), CHROMA_BATCH_SIZE):
        end = min(i + CHROMA_BATCH_SIZE, len(ids))
        collection.add(
            ids=ids[i:end],
            documents=docs[i:end],
            embeddings=vectors[i:end],
            metadatas=metadatas[i:end],
        )

    return {
        "collection_name": collection_name,
        "chunk_count": len(chunks),
    }


def query_chunks(collection_name: str, conversation_id: str, question: str, top_k: int = 4, max_distance: float = 1.3) -> list[dict]:
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)

    # Check if collection has any data
    if collection.count() == 0:
        logger.warning(f"⚠️ Collection {collection_name} is empty — Chroma data may have been lost (ephemeral storage)")
        return []

    query_vector = embed_texts([question])[0]
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    rows = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        # Chroma returns L2 distance; convert to similarity (cosine) if needed, or use threshold directly
        # For OpenAI embeddings, L2 distance is usually in [0,2], lower is better. We'll use a threshold.
        # similarity = 1 - distance/2 (approx), so threshold 0.7 similarity ~ distance <= 0.3
        if distance > max_distance:
            # continue
        # Only include if similarity >= threshold (i.e., distance <= 0.3)
        # if distance > (1 - similarity_threshold):
            continue
        rows.append({
            "chunk_id": chunk_id,
            "text": document,
            "file_name": metadata.get("file_name", "Unknown file"),
            "section": metadata.get("section") or None,
            "page": None if metadata.get("page", -1) == -1 else metadata.get("page"),
            "distance": distance,
            "metadata": metadata,
            "image_name": metadata.get("image_name") or None,
        })
    return rows
