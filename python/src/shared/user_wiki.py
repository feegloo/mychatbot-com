"""Per-user master knowledge wiki builder.

Aggregates per-conversation "idea files" (Section 3a wikis) into a single
cross-topic master wiki that captures what this user has studied across all
their conversations.

Triggered lazily from ask.ts after a successful answer when:
  • USER_WIKI_ENABLED=true
  • user_id > 0
  • The conversation has an internal wiki
  • The user's existing master wiki is stale (> 30 min old) or absent

The result is stored in ``user_wikis`` and injected into the ANSWER_PROMPT
as Section 3b for all subsequent questions by this user.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser

from .llm_instrument import traced_llm_call
from .prompts.user_wiki import USER_WIKI_PROMPT

logger = logging.getLogger(__name__)

_MAX_OUTPUT_CHARS = 12_000  # ~3000 tokens — same budget as per-conversation wiki
_MAX_WIKI_INPUT_CHARS = 4_000  # clip each conversation wiki to keep total prompt sane


def _format_conversation_wikis(wikis: list[dict]) -> str:
    """Format a list of per-conversation wikis into a single block for the prompt.

    Each item in *wikis* is expected to have:
        conversation_id : str
        content         : str   (the per-conversation wiki text)
    """
    if not wikis:
        return "(no conversation wikis available)"

    parts: list[str] = []
    for i, item in enumerate(wikis, 1):
        conv_id = item.get("conversation_id", f"conv-{i}")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        # Clip long wikis — the master wiki can't process >40k chars anyway
        if len(content) > _MAX_WIKI_INPUT_CHARS:
            content = content[:_MAX_WIKI_INPUT_CHARS].rstrip() + "\n_(trimmed)_"
        parts.append(f"=== Conversation {i} (id: {conv_id}) ===\n{content}")

    return "\n\n--\n\n".join(parts) if parts else "(no conversation wikis available)"


def build_user_wiki(
    *,
    user_id: int,
    conversation_wikis: list[dict],
) -> str | None:
    """Synthesise a cross-conversation master wiki for *user_id*.

    Parameters
    ----------
    user_id
        Stable integer user identifier (from ``user_fingerprints``).
    conversation_wikis
        List of ``{conversation_id: str, content: str}`` dicts — the
        per-conversation Section-3a wikis that have been built so far.

    Returns the wiki text, or ``None`` if generation failed or was skipped.
    Failures are logged but never raised — this is best-effort enrichment.
    """
    wikis = [w for w in (conversation_wikis or []) if (w.get("content") or "").strip()]
    if not wikis:
        logger.info(
            "📚 [user-wiki] Skipping: no non-empty conversation wikis (user=%d)", user_id
        )
        return None

    from .rag import get_llm  # local import to avoid circular at module load

    llm = get_llm()
    chain = USER_WIKI_PROMPT | llm | StrOutputParser()
    model = (
        getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    )

    formatted = _format_conversation_wikis(wikis)

    logger.info(
        "📚 [user-wiki] Building master wiki (user=%d, sources=%d, input=%d chars)",
        user_id,
        len(wikis),
        len(formatted),
    )

    try:
        wiki_text, _usage = traced_llm_call(
            chain=chain,
            params={"conversation_wikis": formatted},
            operation="build_user_wiki",
            model=model,
            conversation_id=f"user_{user_id}",
        )
    except Exception as exc:
        logger.warning(
            "📚 [user-wiki] Generation failed (user=%d): %s", user_id, exc
        )
        return None

    wiki_text = (wiki_text or "").strip()
    if not wiki_text:
        logger.info(
            "📚 [user-wiki] Empty output (user=%d)", user_id
        )
        return None

    # Strip surrounding code fences if the model added them
    if wiki_text.startswith("```"):
        first_nl = wiki_text.find("\n")
        if first_nl != -1:
            wiki_text = wiki_text[first_nl + 1 :]
        if wiki_text.endswith("```"):
            wiki_text = wiki_text[:-3].rstrip()

    if len(wiki_text) > _MAX_OUTPUT_CHARS:
        logger.info(
            "📚 [user-wiki] Output exceeded %d chars (%d) — trimming (user=%d)",
            _MAX_OUTPUT_CHARS,
            len(wiki_text),
            user_id,
        )
        wiki_text = wiki_text[:_MAX_OUTPUT_CHARS].rstrip() + "\n\n_(trimmed)_"

    logger.info(
        "📚 [user-wiki] Generated (user=%d, %d sources, %d chars)",
        user_id,
        len(wikis),
        len(wiki_text),
    )
    return wiki_text
