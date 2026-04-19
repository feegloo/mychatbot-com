from __future__ import annotations

import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

# Disable chromadb's posthog telemetry before importing —
# avoids "capture() takes 1 positional argument but 3 were given" errors
# caused by posthog API incompatibility.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
import sentry_sdk
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

from .chunkers import Chunk
from .config import get_settings

logger = logging.getLogger(__name__)

# Module-level caches — avoids re-creating expensive clients each call
_chroma_client = None
_openai_client = None

EMBED_BATCH_SIZE = 2048  # OpenAI API limit per request
EMBED_MAX_WORKERS = 4  # Parallel embedding requests for very large batches
CHROMA_BATCH_SIZE = 5000  # Chroma add() limit is ~5461


def get_client():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    settings = get_settings()

    no_telemetry = ChromaSettings(anonymized_telemetry=False)

    if settings.chroma_mode == "cloud":
        _chroma_client = chromadb.CloudClient(
            api_key=settings.chroma_api_key,
            tenant=settings.chroma_tenant,
            database=settings.chroma_database,
            settings=no_telemetry,
        )
    elif settings.chroma_mode == "http":
        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_http_host.replace("http://", "")
            .replace("https://", "")
            .split(":")[0],
            port=int(settings.chroma_http_host.rsplit(":", 1)[-1]),
            settings=no_telemetry,
        )
    else:
        _chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir, settings=no_telemetry
        )
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
    if not texts:
        return []
    client = _get_openai_client()
    settings = get_settings()

    with sentry_sdk.start_span(op="embedding", name=f"embed {len(texts)} texts") as span:
        span.set_data("count", len(texts))
        span.set_data("model", settings.openai_embedding_model)

        if len(texts) <= EMBED_BATCH_SIZE:
            response = client.embeddings.create(
                model=settings.openai_embedding_model,
                input=texts,
            )
            tokens_used = getattr(response, "usage", None)
            if tokens_used:
                span.set_data("total_tokens", tokens_used.total_tokens)
                logger.info(f"⚡ Embedded {len(texts)} texts, {tokens_used.total_tokens} tokens")
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        # For very large batches, split and parallelize
        all_vectors: list[list[float] | None] = [None] * len(texts)
        batches = [
            (i, texts[i : i + EMBED_BATCH_SIZE]) for i in range(0, len(texts), EMBED_BATCH_SIZE)
        ]
        total_tokens = 0

        def _embed_batch(start_idx: int, batch: list[str]):
            nonlocal total_tokens
            resp = client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch,
            )
            usage = getattr(resp, "usage", None)
            if usage:
                total_tokens += usage.total_tokens
            sorted_data = sorted(resp.data, key=lambda x: x.index)
            for j, item in enumerate(sorted_data):
                all_vectors[start_idx + j] = item.embedding

        logger.info(f"⚡ Embedding {len(texts)} texts in {len(batches)} parallel batches")
        with ThreadPoolExecutor(max_workers=EMBED_MAX_WORKERS) as pool:
            futures = [pool.submit(_embed_batch, start, batch) for start, batch in batches]
            for f in futures:
                f.result()

        span.set_data("total_tokens", total_tokens)
        logger.info(
            f"⚡ Embedded {len(texts)} texts in {len(batches)} batches, {total_tokens} tokens"
        )
        return all_vectors


@lru_cache(maxsize=128)
def _embed_single_cached(text: str) -> tuple[float, ...]:
    """Cache embedding for a single text (used for repeated query lookups)."""
    return tuple(embed_texts([text])[0])


def collection_count(collection_name: str) -> int:
    """Return the number of documents in a collection (0 if it doesn't exist)."""
    client = get_client()
    try:
        collection = client.get_or_create_collection(name=collection_name)
        return collection.count()
    except Exception:
        return 0


def upsert_chunks(collection_name: str, conversation_id: str, chunks: list[Chunk]) -> dict:
    if not chunks:
        logger.info("⚠️ No chunks to upsert, skipping")
        return {"upserted": 0}
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)

    ids = [chunk.chunk_id for chunk in chunks]
    docs = [chunk.text for chunk in chunks]

    logger.info(f"⚡ Embedding {len(docs)} chunks...")
    with sentry_sdk.start_span(
        op="processing.create_embeddings", name=f"create embeddings for {len(docs)} chunks"
    ):
        vectors = embed_texts(docs)
    logger.info("✅ Embedding complete")

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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors.

    Uses only stdlib math — negligible CPU cost for typical embedding dims (1536–3072).
    Returns a value in [-1, 1]; OpenAI embeddings are unit-normalized so the result
    is effectively in [0, 1] in practice.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def query_chunks(
    collection_name: str,
    conversation_id: str,
    question: str,
    top_k: int = 4,
    max_distance: float = 1.3,
) -> list[dict]:
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)

    # Check if collection has any data
    if collection.count() == 0:
        logger.warning(
            f"⚠️ Collection {collection_name} is empty — Chroma data may have been lost (ephemeral storage)"
        )
        return []

    query_vector = list(_embed_single_cached(question))
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    rows = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    embeddings = result.get("embeddings", [[]])[0]

    for chunk_id, document, metadata, distance, embedding in zip(
        ids, documents, metadatas, distances, embeddings
    ):
        if distance > max_distance:
            continue
        # True cosine similarity between the query and each stored chunk embedding.
        # Chroma may return numpy arrays, so convert to list for the stdlib math computation.
        cosine_sim = _cosine_similarity(query_vector, list(embedding)) if embedding is not None else None
        rows.append(
            {
                "chunk_id": chunk_id,
                "text": document,
                "file_name": metadata.get("file_name", "Unknown file"),
                "section": metadata.get("section") or None,
                "page": None if metadata.get("page", -1) == -1 else metadata.get("page"),
                "chapter_number": metadata.get("chapter_number") or None,
                "distance": distance,
                "cosine_similarity": cosine_sim,
                "metadata": metadata,
                "image_name": metadata.get("image_name") or None,
            }
        )
    return rows
