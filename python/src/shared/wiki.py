"""Internal-wiki builder — Karpathy-style "idea file" per conversation.

Given the welcome message + a sample of indexed chunks, produces a compact
structured markdown wiki that is stored as an internal (hidden) message and
injected into the answering prompt for every subsequent question.

The wiki is generated AFTER the user-facing welcome message has been emitted,
on a background thread, so it never blocks the upload UX.

See [python/src/shared/prompts/wiki.py](python/src/shared/prompts/wiki.py) for
the system prompt + format contract + few-shot examples.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser

from .lang_detect import detect_language
from .llm_instrument import traced_llm_call
from .prompts.wiki import WIKI_PROMPT

logger = logging.getLogger(__name__)

# Hard caps — wiki is meant to be terse. We enforce length on input AND output.
_MAX_CHUNK_SAMPLE_CHARS = 12000
_MAX_WELCOME_CHARS = 4000
_MAX_OUTPUT_CHARS = 7000  # ~1750 tokens; soft trim if model overshoots
_TARGET_SAMPLE_CHUNKS = 10


def _sample_chunks(chunks: list[str], max_chunks: int = _TARGET_SAMPLE_CHUNKS) -> list[str]:
    """Stratified sample: head + middle + tail to capture topical diversity.

    Mirrors `suggested_questions._sample_chunks` so the wiki and the suggested
    questions see a comparable cross-section of the document.
    """
    if not chunks:
        return []
    if len(chunks) <= max_chunks:
        return chunks
    indices: set[int] = set()
    head = min(3, len(chunks))
    indices.update(range(head))
    mid_start = len(chunks) // 3
    mid_end = 2 * len(chunks) // 3
    step = max(1, (mid_end - mid_start) // max(1, max_chunks - 6))
    indices.update(range(mid_start, mid_end, step))
    indices.update(range(max(0, len(chunks) - 3), len(chunks)))
    return [chunks[i] for i in sorted(indices)[:max_chunks]]


def _format_chunk_sample(chunk_records: list[dict]) -> str:
    """Format chunk records as labeled excerpts (file + page).

    Each record is expected to expose ``file_name``, ``page`` (optional), and
    ``text``. Anything missing is rendered with safe fallbacks. Total output
    is hard-capped to keep the prompt within budget.
    """
    parts: list[str] = []
    used = 0
    for i, rec in enumerate(chunk_records, 1):
        file_name = rec.get("file_name") or "unknown"
        page = rec.get("page")
        text = (rec.get("text") or "").strip()
        if not text:
            continue
        label = f"[Chunk {i} — {file_name}"
        if page is not None:
            label += f", p.{page}"
        label += "]"
        block = f"{label}\n{text}"
        if used + len(block) > _MAX_CHUNK_SAMPLE_CHARS:
            block = block[: max(0, _MAX_CHUNK_SAMPLE_CHARS - used)]
            if block:
                parts.append(block)
            break
        parts.append(block)
        used += len(block) + 2  # +2 for separator
    return "\n\n".join(parts) if parts else "(no chunk excerpts available)"


def build_conversation_wiki(
    *,
    conversation_id: str,
    conversation_title: str,
    welcome_message: str,
    chunk_records: list[dict],
    language: str | None = None,
) -> str | None:
    """Build the internal wiki for a conversation.

    Returns the markdown wiki string, or ``None`` if generation was skipped
    (e.g., empty inputs) or failed. Failure is logged but never raised — the
    wiki is a best-effort enhancement, never on the critical path.

    Parameters
    ----------
    conversation_id
        For logging / telemetry only.
    conversation_title
        Used in the H1 heading. Falls back to ``"Conversation"`` if blank.
    welcome_message
        The user-facing welcome message already shown. Provides the high-level
        framing the wiki should compress further.
    chunk_records
        List of dicts with at least ``file_name`` and ``text`` keys. ``page``
        is optional. A stratified sample is taken automatically.
    language
        Optional ISO-style language hint (e.g., ``"pl"``, ``"en"``). When
        absent, detected from the welcome message.
    """
    welcome_message = (welcome_message or "").strip()
    if not welcome_message:
        logger.info("📚 Skipping wiki generation: empty welcome message (conv=%s)", conversation_id)
        return None
    if not chunk_records:
        logger.info("📚 Skipping wiki generation: no chunks (conv=%s)", conversation_id)
        return None

    if language is None:
        language = detect_language(welcome_message[:2000]) or "en"

    title = (conversation_title or "").strip() or "Conversation"
    welcome_clipped = welcome_message[:_MAX_WELCOME_CHARS]

    sampled_records = _sample_chunks(chunk_records)  # type: ignore[arg-type]
    chunk_sample = _format_chunk_sample(sampled_records)

    from .rag import get_llm  # local import to avoid circular at module load

    llm = get_llm()
    chain = WIKI_PROMPT | llm | StrOutputParser()
    model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"

    try:
        wiki_text, _usage = traced_llm_call(
            chain=chain,
            params={
                "conversation_title": title,
                "language": language,
                "welcome_message": welcome_clipped,
                "chunk_sample": chunk_sample,
            },
            operation="build_conversation_wiki",
            model=model,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("📚 Wiki generation failed (conv=%s): %s", conversation_id, exc)
        return None

    wiki_text = (wiki_text or "").strip()
    if not wiki_text:
        logger.info("📚 Wiki generation produced empty output (conv=%s)", conversation_id)
        return None

    # Strip stray surrounding code fences if the model added them despite the
    # explicit instruction not to.
    if wiki_text.startswith("```"):
        first_nl = wiki_text.find("\n")
        if first_nl != -1:
            wiki_text = wiki_text[first_nl + 1 :]
        if wiki_text.endswith("```"):
            wiki_text = wiki_text[: -3].rstrip()

    if len(wiki_text) > _MAX_OUTPUT_CHARS:
        logger.info(
            "📚 Wiki output exceeded %d chars (%d) — trimming (conv=%s)",
            _MAX_OUTPUT_CHARS,
            len(wiki_text),
            conversation_id,
        )
        wiki_text = wiki_text[:_MAX_OUTPUT_CHARS].rstrip() + "\n\n_(trimmed)_"

    logger.info(
        "📚 Wiki generated (conv=%s, lang=%s, %d chars)",
        conversation_id,
        language,
        len(wiki_text),
    )
    return wiki_text


__all__ = ["build_conversation_wiki"]
