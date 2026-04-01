from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings

from .config import get_settings
from .chunkers import Chunk


def get_client():
    settings = get_settings()

    if settings.chroma_mode == "http":
        return chromadb.HttpClient(host=settings.chroma_http_host.replace("http://", "").replace("https://", "").split(":")[0],
                                   port=int(settings.chroma_http_host.rsplit(":", 1)[-1]))
    return chromadb.PersistentClient(path=settings.chroma_persist_dir, settings=ChromaSettings(anonymized_telemetry=False))


def get_embeddings():
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


def upsert_chunks(collection_name: str, conversation_id: str, chunks: list[Chunk]) -> dict:
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)
    embeddings = get_embeddings()

    ids = [chunk.chunk_id for chunk in chunks]
    docs = [chunk.text for chunk in chunks]
    vectors = embeddings.embed_documents(docs)
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

    collection.add(
        ids=ids,
        documents=docs,
        embeddings=vectors,
        metadatas=metadatas,
    )

    return {
        "collection_name": collection_name,
        "chunk_count": len(chunks),
    }


def query_chunks(collection_name: str, conversation_id: str, question: str, top_k: int = 4, max_distance: float = 1.4) -> list[dict]:
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name)
    embeddings = get_embeddings()

    query_vector = embeddings.embed_query(question)
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where={"conversation_id": conversation_id},
        include=["documents", "metadatas", "distances"],
    )

    rows = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        if distance > max_distance:
            continue
        rows.append({
            "chunk_id": chunk_id,
            "text": document,
            "file_name": metadata.get("file_name", "Unknown file"),
            "section": metadata.get("section") or None,
            "page": None if metadata.get("page", -1) == -1 else metadata.get("page"),
            "distance": distance,
            "metadata": metadata,
        })
    return rows
