"""Internal-wiki builder — Karpathy-style "idea file" per conversation.

Pattern source: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

After the user-facing welcome message has been emitted, we build a compact,
*structured* internal wiki that is stored as a hidden message and injected
into the answering prompt for every subsequent question. This compounds
knowledge instead of re-deriving the document's shape on every turn.

Retrieval strategy
------------------
The welcome message is itself a high-quality query: it already names the
dominant entities and stakes of the upload. We therefore embed it and run a
top-K Chroma search against the just-indexed conversation collection. For
each match we expand to its full page (so structure and relationships
survive) and to the dominant chapter, all packed into a generous token
budget (default ~300k tokens). The wiki LLM then has both the high-level
framing (welcome) and the concrete material (matched pages + chapter) when
it constructs the entity/relationship graph.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser

from .lang_detect import detect_language
from .llm_instrument import traced_llm_call
from .prompts.wiki import WIKI_PROMPT

logger = logging.getLogger(__name__)

# 4 chars/token is the conservative English approximation; Polish/Arabic etc
# trend toward 3.5, so we add a small safety factor by reserving ~10% of the
# budget for prompt scaffolding (system prompt + examples + welcome + headers).
_CHARS_PER_TOKEN = 4
_DEFAULT_TOKEN_BUDGET = 300_000
_MAX_WELCOME_CHARS = 6_000  # welcome is concentrated framing — full clip rarely needed
_MAX_OUTPUT_CHARS = 7_000  # ~1750 tokens; soft trim if model overshoots
_TOP_K_CHUNKS = 10  # vector neighbours retrieved against the welcome message


def _budget_chars(token_budget: int) -> int:
    """Convert a token budget to a raw-material char budget.

    Reserves ~10% headroom for prompt scaffolding so the raw-material section
    never single-handedly exhausts the context window.
    """
    if token_budget <= 0:
        return 0
    return int(token_budget * _CHARS_PER_TOKEN * 0.9)


def _build_raw_material(
    *,
    collection_name: str,
    conversation_id: str,
    welcome_message: str,
    storage_dir: str | None,
    char_budget: int,
) -> tuple[str, int]:
    """Retrieve material relevant to the welcome message.

    Pipeline:
      1. ``query_chunks`` with the welcome message as the query — Chroma
         surfaces chunks closest to the document's high-level framing.
      2. Expand to full pages via ``_extract_matched_pages`` (preserves
         structure that 1600-char chunking destroys).
      3. Add the dominant chapter via ``_extract_chapter_context`` for
         long-range narrative / structural context.
      4. Hard-cap combined material at ``char_budget``.

    Returns ``(material, chunk_count)`` where ``chunk_count`` is the number
    of Chroma matches that contributed (used for logging + skip decisions).
    """
    # Local imports avoid pulling rag.py / vector_store at module import time,
    # keeping wiki.py importable in lightweight contexts (tests, tooling).
    from .rag import _extract_chapter_context, _extract_matched_pages
    from .vector_store import query_chunks

    try:
        rows = query_chunks(
            collection_name=collection_name,
            conversation_id=conversation_id,
            question=welcome_message[:_MAX_WELCOME_CHARS],
            top_k=_TOP_K_CHUNKS,
            # Wide distance gate — wiki construction wants loosely related
            # context, not the tight retrieval used for a Q&A turn.
            max_distance=1.5,
        )
    except Exception as exc:
        logger.warning("📚 wiki: chunk query failed (conv=%s): %s", conversation_id, exc)
        rows = []

    if not rows:
        return "(no matched material)", 0

    matched_pages = _extract_matched_pages(storage_dir, rows) if storage_dir else ""
    chapter_ctx = _extract_chapter_context(storage_dir, rows) if storage_dir else ""

    sections: list[str] = []

    # 1. Top-K matched chunks — terse, exact text the embedder selected.
    chunk_block_parts: list[str] = []
    for i, row in enumerate(rows, 1):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        fname = row.get("file_name", "unknown")
        page = row.get("page")
        label = f"[Match {i} — {fname}"
        if page is not None:
            label += f", p.{page}"
        label += "]"
        chunk_block_parts.append(f"{label}\n{text}")
    if chunk_block_parts:
        sections.append(
            "== TOP MATCHES (embedding similarity to welcome message) ==\n"
            + "\n\n".join(chunk_block_parts)
        )

    # 2. Full pages of those matches — preserves formulas, lists, dialogue
    #    boundaries, etc. that chunking splits across boundaries.
    if matched_pages and not matched_pages.startswith("("):
        sections.append("== FULL PAGES OF TOP MATCHES ==\n" + matched_pages)

    # 3. Dominant chapter — long-range narrative / structural context.
    if chapter_ctx:
        sections.append("== DOMINANT CHAPTER CONTEXT ==\n" + chapter_ctx)

    combined = "\n\n--\n\n".join(sections)
    if len(combined) > char_budget:
        combined = (
            combined[:char_budget].rstrip()
            + "\n\n[... raw material trimmed to fit token budget]"
        )

    return combined, len(rows)


def build_conversation_wiki(
    *,
    conversation_id: str,
    collection_name: str,
    conversation_title: str,
    welcome_message: str,
    storage_dir: str | None,
    language: str | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
) -> str | None:
    """Build the internal wiki for a conversation.

    Returns the markdown wiki, or ``None`` if generation was skipped (empty
    welcome / no matched chunks) or failed. Failures are logged but never
    raised — the wiki is best-effort and never on the critical path.

    Parameters
    ----------
    conversation_id, collection_name
        Used for Chroma retrieval and telemetry.
    conversation_title
        Used in the H1 heading.
    welcome_message
        The user-facing welcome. Used both as the embedding query and as
        high-level framing in the LLM prompt.
    storage_dir
        Conversation storage directory (contains ``_raw_text.json`` and
        ``_chapters.json``). Required to expand matches to full pages.
    language
        Language hint (``"pl"``, ``"en"``, ...). Detected from the welcome
        when omitted.
    token_budget
        Soft cap on prompt input tokens for the raw-material section.
        Defaults to 300k.
    """
    welcome_message = (welcome_message or "").strip()
    if not welcome_message:
        logger.info(
            "📚 Skipping wiki generation: empty welcome message (conv=%s)",
            conversation_id,
        )
        return None

    if language is None:
        language = detect_language(welcome_message[:2000]) or "en"

    title = (conversation_title or "").strip() or "Conversation"
    welcome_clipped = welcome_message[:_MAX_WELCOME_CHARS]

    char_budget = _budget_chars(token_budget)
    raw_material, chunk_count = _build_raw_material(
        collection_name=collection_name,
        conversation_id=conversation_id,
        welcome_message=welcome_message,
        storage_dir=storage_dir,
        char_budget=char_budget,
    )
    if chunk_count == 0:
        logger.info(
            "📚 Skipping wiki generation: no matched chunks (conv=%s)",
            conversation_id,
        )
        return None

    from .rag import get_llm  # local import — avoids circular at module load

    llm = get_llm()
    chain = WIKI_PROMPT | llm | StrOutputParser()
    model = (
        getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    )

    logger.info(
        "📚 Wiki: building (conv=%s, lang=%s, matches=%d, raw=%d chars, budget=%dk tokens)",
        conversation_id,
        language,
        chunk_count,
        len(raw_material),
        token_budget // 1000,
    )

    try:
        wiki_text, _usage = traced_llm_call(
            chain=chain,
            params={
                "conversation_title": title,
                "language": language,
                "welcome_message": welcome_clipped,
                "raw_material": raw_material,
            },
            operation="build_conversation_wiki",
            model=model,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning(
            "📚 Wiki generation failed (conv=%s): %s", conversation_id, exc
        )
        return None

    wiki_text = (wiki_text or "").strip()
    if not wiki_text:
        logger.info(
            "📚 Wiki generation produced empty output (conv=%s)", conversation_id
        )
        return None

    # Strip surrounding code fences if the model added them despite the
    # explicit instruction not to.
    if wiki_text.startswith("```"):
        first_nl = wiki_text.find("\n")
        if first_nl != -1:
            wiki_text = wiki_text[first_nl + 1 :]
        if wiki_text.endswith("```"):
            wiki_text = wiki_text[:-3].rstrip()

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
