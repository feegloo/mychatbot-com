"""Cross-conversation reusable-image semantic index.

Every time the chat pipeline generates an image we also index its
description (revised prompt + title) into a single global Chroma
collection. Later, when another conversation is about to spend an
OpenAI image-gen quota on a "write inspired chapter / poem / story"
answer, the backend can query this collection first and — on a
threshold match — reuse the existing image instead of generating a
fresh one.

Design notes:

* One shared collection (``GENERATED_IMAGES_COLLECTION``) holds rows from
  ALL conversations. Per-row metadata carries ``conversation_id``,
  ``storage_namespace``, ``file_name``, ``image_title`` and the list of
  ``source_original_names`` so the API layer can rebuild a playable
  ``/api/storage/<ns>/<file>`` URL without another DB round-trip.

* Because each row is a short description (≤ a few hundred tokens), a
  normal OpenAI embedding + Chroma L2 search is more than fast enough.

* The search is intentionally tolerant: callers can pass a list of
  ``preferred_source_files`` (e.g. the original_names of the currently
  uploaded files). Matches whose indexed ``source_original_names`` share
  at least one entry with that list get a small distance bonus so
  "same PDF in a different conversation" trumps unrelated images that
  happen to have slightly more overlapping words.
"""

from __future__ import annotations

import logging
from typing import Any

from .vector_store import _embed_single_cached, get_client

logger = logging.getLogger(__name__)

GENERATED_IMAGES_COLLECTION = "generated_images_v1"

# L2 distance on OpenAI embeddings usually sits in [0, 2]. Descriptions of
# truly related creative scenes (same story, same character, same mood)
# tend to score below ~0.55; we pick a conservative default so we only
# reuse when the match is genuinely close.
DEFAULT_MAX_DISTANCE = 0.55

# When the caller supplies ``preferred_source_files`` and a candidate's
# ``source_original_names`` shares at least one entry with them, we
# subtract this amount from the reported distance before comparing it
# against ``max_distance``. This tilts reuse toward images grounded in
# the same source document (e.g. the user re-uploaded the same PDF in a
# new conversation).
SOURCE_OVERLAP_BONUS = 0.1


def _collection():
    client = get_client()
    return client.get_or_create_collection(name=GENERATED_IMAGES_COLLECTION)


def register_image(
    *,
    image_id: str,
    conversation_id: str,
    storage_namespace: str,
    file_name: str,
    image_title: str | None = None,
    image_prompt: str | None = None,
    user_prompt: str | None = None,
    source_original_names: list[str] | None = None,
) -> None:
    """Index one generated image into the global reusable-images collection.

    ``image_id`` must match the primary key stored in Postgres'
    ``generated_images`` table so the two systems stay in lockstep.

    The embedded document concatenates the originating user prompt with
    the richer LLM-generated image prompt. This lets us hit the same image
    two ways: a future user typing the *exact same* prompt in another
    conversation (surface-level match), or a semantically similar
    creative-writing answer whose text overlaps with the scene the
    prompt paints (deeper match).
    """
    if not (image_prompt or "").strip() and not (user_prompt or "").strip():
        logger.warning(
            "⚠️ refusing to register image %s without an image_prompt or user prompt",
            image_id,
        )
        return

    collection = _collection()
    embed_text = _build_embed_text(user_prompt=user_prompt, image_prompt=image_prompt or "")
    vector = list(_embed_single_cached(embed_text))
    metadata: dict[str, Any] = {
        "conversation_id": conversation_id,
        "storage_namespace": storage_namespace,
        "file_name": file_name,
        "image_title": image_title or "",
        "image_prompt": image_prompt or "",
        "user_prompt": user_prompt or "",
        # Chroma metadata values must be primitive; encode as a delimited
        # string and split on read.
        "source_original_names": "||".join(source_original_names or []),
    }
    # Upsert so re-generations (same id) don't create duplicate rows.
    collection.upsert(
        ids=[image_id],
        documents=[embed_text],
        embeddings=[vector],
        metadatas=[metadata],
    )


def _build_embed_text(*, user_prompt: str | None, image_prompt: str) -> str:
    """Compose the text we embed for a stored image.

    Keeping both fields in one document means a single vector covers both
    "same prompt" and "same described scene" lookups — avoiding the
    maintenance cost of a second collection or a two-stage query.
    """
    parts: list[str] = []
    if user_prompt and user_prompt.strip():
        parts.append(f"PROMPT: {user_prompt.strip()}")
    if image_prompt and image_prompt.strip():
        parts.append(f"DESCRIPTION: {image_prompt.strip()}")
    return "\n\n".join(parts)


def _decode_source_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s for s in raw.split("||") if s]


def find_reusable_image(
    *,
    query_text: str,
    exclude_conversation_id: str | None = None,
    preferred_source_files: list[str] | None = None,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    top_k: int = 10,
) -> dict | None:
    """Return the best-matching indexed image, or None if nothing qualifies.

    The return shape mirrors what the backend needs to paint the reused
    image into an assistant message::

        {
          "image_id": "...",
          "distance": 0.32,
          "conversation_id": "...",
          "storage_namespace": "...",
          "file_name": "...",
          "image_title": "...",
          "image_prompt": "...",
          "source_original_names": [...],
        }
    """
    if not query_text.strip():
        return None

    collection = _collection()
    if collection.count() == 0:
        return None

    vector = list(_embed_single_cached(query_text))
    result = collection.query(
        query_embeddings=[vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    ids = result.get("ids", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    preferred = set(preferred_source_files or [])
    best: dict | None = None

    for image_id, metadata, distance in zip(ids, metadatas, distances, strict=False):
        if exclude_conversation_id and metadata.get("conversation_id") == exclude_conversation_id:
            continue

        source_names = _decode_source_names(metadata.get("source_original_names"))
        effective = distance
        if preferred and any(name in preferred for name in source_names):
            effective = max(0.0, effective - SOURCE_OVERLAP_BONUS)

        if effective > max_distance:
            continue

        if best is None or effective < best["effective_distance"]:
            best = {
                "image_id": image_id,
                "distance": float(distance),
                "effective_distance": float(effective),
                "conversation_id": metadata.get("conversation_id", ""),
                "storage_namespace": metadata.get("storage_namespace", ""),
                "file_name": metadata.get("file_name", ""),
                "image_title": metadata.get("image_title") or "",
                "image_prompt": metadata.get("image_prompt") or "",
                "user_prompt": metadata.get("user_prompt") or "",
                "source_original_names": source_names,
            }

    if best is None:
        return None

    # Drop the helper field before returning so the API surface stays tidy.
    best.pop("effective_distance", None)
    return best
