from __future__ import annotations

import logging
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

EMBED_BATCH_SIZE = 2048  # OpenAI API max items per request
EMBED_MAX_TOKENS_PER_BATCH = 200_000  # Stay well under OpenAI's 300K limit; 200K gives room for non-English text
EMBED_CHARS_PER_TOKEN = 2  # Conservative estimate for non-English text (Polish, CJK, etc.)
EMBED_MAX_WORKERS = 4  # Parallel embedding requests for very large batches
CHROMA_BATCH_SIZE = 5000  # Chroma add() limit is ~5461

# ---------------------------------------------------------------------------
# Feature flag — set to True to enable hybrid L2 + cosine re-ranking.
# False  → original L2-only path (fast, no extra Chroma round-trip overhead).
# True   → hybrid path: fetches more candidates, re-ranks by combined score.
# ---------------------------------------------------------------------------
HYBRID_RETRIEVAL_ENABLED: bool = False

# Hybrid retrieval weights — L2 similarity and cosine similarity are combined
# into a single ranking score.  Both sit in [0, 1] after normalisation, so the
# weights are directly comparable.  L2 is the primary signal (Chroma's native
# distance); cosine adds a rotationally-invariant secondary signal that catches
# cases where two embeddings have slightly different norms but point in nearly
# the same direction.  For perfectly unit-normalised vectors (as returned by
# OpenAI) the two metrics are equivalent, but in practice floating-point
# rounding and batching produce small norm deviations that the hybrid scoring
# smoothes out.
HYBRID_L2_WEIGHT = 0.5
HYBRID_COSINE_WEIGHT = 0.5
# Pull more candidates than requested so the re-ranker has room to promote
# results that score well on cosine but are ranked lower by raw L2.
HYBRID_FETCH_MULTIPLIER = 3


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
    # Explicit timeout prevents a stalled embedding call from hanging the
    # indexing pipeline indefinitely (default SDK timeout is 600 s = 10 min).
    _openai_client = OpenAI(api_key=settings.openai_api_key, timeout=120.0)
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

        # Build token-budget-aware batches: respect both item count AND token limit
        batches = _build_token_aware_batches(texts)

        if len(batches) == 1:
            start_idx, batch = batches[0]
            response = client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch,
            )
            tokens_used = getattr(response, "usage", None)
            if tokens_used:
                span.set_data("total_tokens", tokens_used.total_tokens)
                logger.info(f"⚡ Embedded {len(texts)} texts, {tokens_used.total_tokens} tokens")
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        # For multiple batches, parallelize
        all_vectors: list[list[float] | None] = [None] * len(texts)
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


def _build_token_aware_batches(texts: list[str]) -> list[tuple[int, list[str]]]:
    """Split texts into batches that respect both item count and token budget.

    Each batch stays under EMBED_BATCH_SIZE items AND EMBED_MAX_TOKENS_PER_BATCH
    estimated tokens to avoid OpenAI's per-request token limit.
    """
    batches: list[tuple[int, list[str]]] = []
    current_batch: list[str] = []
    current_start = 0
    current_tokens = 0

    for i, text in enumerate(texts):
        estimated_tokens = max(len(text) // EMBED_CHARS_PER_TOKEN, 1)

        would_exceed_tokens = current_tokens + estimated_tokens > EMBED_MAX_TOKENS_PER_BATCH
        would_exceed_count = len(current_batch) >= EMBED_BATCH_SIZE

        if current_batch and (would_exceed_tokens or would_exceed_count):
            batches.append((current_start, current_batch))
            current_batch = []
            current_start = i
            current_tokens = 0

        current_batch.append(text)
        current_tokens += estimated_tokens

    if current_batch:
        batches.append((current_start, current_batch))

    return batches


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
    """Cosine similarity between two vectors.

    OpenAI embeddings are unit-normalised, so this reduces to the dot
    product — but we compute the full formula for correctness in case a
    vector arrives with a slightly non-unit norm due to float rounding.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
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
    """Return the most relevant chunks for *question* from the given collection.

    When ``HYBRID_RETRIEVAL_ENABLED`` is ``True`` the function uses a two-stage
    approach: a wider L2 candidate fetch followed by cosine re-ranking.  When
    the flag is ``False`` the original L2-only path is used (lower latency,
    no stored-embedding round-trip).
    """
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)

    if collection.count() == 0:
        logger.warning(
            f"⚠️ Collection {collection_name} is empty — "
            f"Chroma data may have been lost (ephemeral storage)"
        )
        return []

    query_vector = list(_embed_single_cached(question))

    if HYBRID_RETRIEVAL_ENABLED:
        return _query_chunks_hybrid(collection, query_vector, top_k, max_distance)
    return _query_chunks_l2(collection, query_vector, top_k, max_distance)


def _query_chunks_l2(
    collection,
    query_vector: list[float],
    top_k: int,
    max_distance: float,
) -> list[dict]:
    """Original L2-only retrieval path."""
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    rows = []
    for chunk_id, document, metadata, distance in zip(
        ids, documents, metadatas, distances, strict=False
    ):
        if distance > max_distance:
            continue
        rows.append(
            {
                "chunk_id": chunk_id,
                "text": document,
                "file_name": metadata.get("file_name", "Unknown file"),
                "section": metadata.get("section") or None,
                "page": None if metadata.get("page", -1) == -1 else metadata.get("page"),
                "chapter_number": metadata.get("chapter_number") or None,
                "chapter_name": metadata.get("chapter_name") or None,
                "distance": distance,
                "metadata": metadata,
                "image_name": metadata.get("image_name") or None,
            }
        )
    return rows


def _query_chunks_hybrid(
    collection,
    query_vector: list[float],
    top_k: int,
    max_distance: float,
) -> list[dict]:
    """Hybrid L2 + cosine re-ranking retrieval path.

    Steps:
    1. Fetch ``top_k * HYBRID_FETCH_MULTIPLIER`` candidates via Chroma's native
       L2 HNSW index, requesting stored embeddings for cosine computation.
    2. Filter candidates whose raw L2 distance exceeds ``max_distance``.
    3. Score each survivor: ``hybrid = L2_WEIGHT * l2_sim + COSINE_WEIGHT * cosine``
       where ``l2_sim = 1 - l2_dist / 2`` maps the [0, 2] L2 range to [1, 0].
    4. Re-sort by hybrid score descending and return the best ``top_k``.
    """
    fetch_k = min(top_k * HYBRID_FETCH_MULTIPLIER, collection.count())
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=fetch_k,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    embeddings = result.get("embeddings", [[]])[0]

    candidates: list[dict] = []
    for chunk_id, document, metadata, l2_dist, doc_emb in zip(
        ids, documents, metadatas, distances, embeddings, strict=False
    ):
        if l2_dist > max_distance:
            continue

        # l2_sim ∈ [0, 1]: 1 = identical, 0 = maximally distant (L2 = 2)
        l2_sim = 1.0 - l2_dist / 2.0
        cosine = _cosine_similarity(query_vector, list(doc_emb))
        hybrid_score = HYBRID_L2_WEIGHT * l2_sim + HYBRID_COSINE_WEIGHT * cosine

        candidates.append(
            {
                "chunk_id": chunk_id,
                "text": document,
                "file_name": metadata.get("file_name", "Unknown file"),
                "section": metadata.get("section") or None,
                "page": None if metadata.get("page", -1) == -1 else metadata.get("page"),
                "chapter_number": metadata.get("chapter_number") or None,
                "chapter_name": metadata.get("chapter_name") or None,
                "distance": l2_dist,
                "cosine_similarity": cosine,
                "hybrid_score": hybrid_score,
                "metadata": metadata,
                "image_name": metadata.get("image_name") or None,
            }
        )

    candidates.sort(key=lambda r: r["hybrid_score"], reverse=True)
    best = candidates[:top_k]

    logger.info(
        f"🔎 Hybrid retrieval: {len(ids)} fetched → {len(candidates)} passed L2 filter "
        f"→ {len(best)} returned (top_k={top_k}, max_distance={max_distance})"
    )
    return best
