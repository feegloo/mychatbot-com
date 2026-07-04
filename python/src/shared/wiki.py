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
_MAX_WELCOME_CHARS = 10_000  # welcome is concentrated framing — full clip rarely needed
_MAX_OUTPUT_CHARS = 80_000  # ~10_000 tokens; extra headroom for rich large-doc diagrams
_TOP_K_CHUNKS = 20  # vector neighbours retrieved against the welcome message (doubled for breadth)


def _budget_chars(token_budget: int) -> int:
    """Convert a token budget to a raw-material char budget.

    Reserves ~10% headroom for prompt scaffolding so the raw-material section
    never single-handedly exhausts the context window.
    """
    if token_budget <= 0:
        return 0
    return int(token_budget * _CHARS_PER_TOKEN * 0.9)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]: 1 = same direction, 0 = orthogonal, -1 = opposite."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_chunk_correlation_block(
    collection_name: str,
    chunk_ids: list[str],
    chunk_labels: list[str],
) -> str:
    """Fetch stored embeddings for *chunk_ids* and compute all pairwise cosine
    similarities.

    Returns a formatted text block (to embed in the wiki raw-material section)
    that maps every unique chunk pair to a correlation score in [-1, 1]:
      •  1.0 → identical / strongly related (same semantic space)
      •  0.0 → unrelated / orthogonal
      • -1.0 → opposing / contrasting concepts

    Only pairs whose |score| >= 0.10 are listed (below that threshold the
    similarity is too weak to drive meaningful diagram edges).
    """
    try:
        from .vector_store import get_client

        client = get_client()
        collection = client.get_or_create_collection(name=collection_name)
        result = collection.get(ids=chunk_ids, include=["embeddings"])
        raw_embeddings = result.get("embeddings") or []
        returned_ids: list[str] = result.get("ids") or []
    except Exception as exc:
        logger.warning("📚 wiki: embedding fetch for correlation failed: %s", exc)
        return ""

    # Build id → embedding map; returned order may differ from requested order.
    emb_by_id: dict[str, list[float]] = {
        cid: list(emb)
        for cid, emb in zip(returned_ids, raw_embeddings, strict=False)
        if emb is not None
    }

    # Align with the original chunk_ids / chunk_labels ordering.
    aligned: list[tuple[str, list[float]]] = []
    for cid, label in zip(chunk_ids, chunk_labels, strict=False):
        emb = emb_by_id.get(cid)
        if emb is not None:
            aligned.append((label, emb))

    if len(aligned) < 2:
        return ""

    # Compute all pairwise cosine similarities.
    pairs: list[tuple[float, str, str]] = []
    for i in range(len(aligned)):
        for j in range(i + 1, len(aligned)):
            label_a, emb_a = aligned[i]
            label_b, emb_b = aligned[j]
            score = round(_cosine_similarity(emb_a, emb_b), 2)
            if abs(score) >= 0.10:
                pairs.append((score, label_a, label_b))

    # Sort strongest first so the LLM sees the most relevant pairs early.
    pairs.sort(key=lambda t: abs(t[0]), reverse=True)

    if not pairs:
        return ""

    lines = [
        "== CHUNK PAIRWISE COSINE CORRELATION ==",
        "Score: 1.0 = closely related, 0.0 = unrelated, -1.0 = contrasting/opposing",
        "Use these scores as edge-weight labels in the Mermaid diagram.",
        "",
    ]
    for score, la, lb in pairs:
        lines.append(f"{la} <-> {lb}: {score:+.2f}")

    return "\n".join(lines)


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
      4. Compute pairwise cosine similarities between retrieved chunk
         embeddings and append a correlation matrix section — this lets
         the wiki LLM annotate Mermaid diagram edges with numeric scores.
      5. Hard-cap combined material at ``char_budget``.

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
    chunk_ids: list[str] = []
    chunk_labels: list[str] = []
    for i, row in enumerate(rows, 1):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        fname = row.get("file_name", "unknown")
        page = row.get("page")
        label = f"Match {i}"
        display_label = f"[{label} — {fname}"
        if page is not None:
            display_label += f", p.{page}"
        display_label += "]"
        chunk_block_parts.append(f"{display_label}\n{text}")
        chunk_ids.append(row.get("chunk_id", ""))
        chunk_labels.append(label)
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

    # 4. Pairwise cosine correlation between retrieved chunks.
    #    Fetches stored embeddings from Chroma; failures are silently skipped.
    valid_ids = [cid for cid, lbl in zip(chunk_ids, chunk_labels, strict=False) if cid]
    valid_labels = [lbl for cid, lbl in zip(chunk_ids, chunk_labels, strict=False) if cid]
    if len(valid_ids) >= 2:
        corr_block = _build_chunk_correlation_block(collection_name, valid_ids, valid_labels)
        if corr_block:
            sections.append(corr_block)

    combined = "\n\n--\n\n".join(sections)
    if len(combined) > char_budget:
        combined = (
            combined[:char_budget].rstrip()
            + "\n\n[... raw material trimmed to fit token budget]"
        )

    return combined, len(rows)


def _build_document_scale_hint(page_count: int | None, welcome_len: int) -> str:
    """Return an extraction-depth hint based on estimated document size.

    For large documents we want the model to be exhaustive — extract every
    named entity, secondary character, location, subplot, etc. — rather than
    producing a high-level representative sample.  We express this as a
    qualitative instruction ("what to extract more of") plus scaled numeric
    targets so the model understands both the WHAT and the HOW MUCH.

    Tiers (page_count takes precedence; falls back to welcome length):
      • tiny   : < 20 pages  (or welcome < 1 000 chars)
      • short  : 20–80 pages (or welcome 1 000–3 000 chars)
      • medium : 80–180 pages
      • large  : 180–400 pages
      • xl     : > 400 pages
    """
    # Estimate tier from page_count; fall back to welcome length as proxy.
    if page_count is not None:
        if page_count < 20:
            tier = "tiny"
        elif page_count < 80:
            tier = "short"
        elif page_count < 180:
            tier = "medium"
        elif page_count < 400:
            tier = "large"
        else:
            tier = "xl"
    else:
        # Welcome message length is a rough proxy for document richness.
        if welcome_len < 1_000:
            tier = "tiny"
        elif welcome_len < 3_000:
            tier = "short"
        elif welcome_len < 5_000:
            tier = "medium"
        else:
            tier = "large"

    if tier == "tiny":
        return (
            "DOCUMENT SCALE: short (tiny). "
            "Standard extraction: 24–42 nodes, 30–54 edges."
        )
    if tier == "short":
        return (
            "DOCUMENT SCALE: short. "
            "Standard extraction: 36–54 nodes, 42–66 edges."
        )
    if tier == "medium":
        return (
            "DOCUMENT SCALE: medium (~80-180 pages). "
            "Extended extraction: aim for 54–78 nodes and 66–90 edges. "
            "Include secondary characters/modules/clauses alongside the main entities. "
            "For fiction: capture subplots, locations, and factions in addition to the main cast. "
            "For technical docs: include specific APIs, configs, data structures, and constraints. "
            "For legal docs: capture every clause, party, obligation, amount, and deadline."
        )
    if tier == "large":
        return (
            "DOCUMENT SCALE: LARGE (~180-400 pages). "
            "EXHAUSTIVE EXTRACTION MODE — target 72–102 nodes and 84–114 edges. "
            "Extract EVERY significant named entity visible in the raw material: "
            "for fiction — every named character (including minor ones), every named location, "
            "every subplot, every faction/alliance, every legal/formal concept, every piece of "
            "evidence, every key scene mechanism; "
            "for technical docs — every module, component, algorithm, parameter, API endpoint, "
            "data structure, and config option; "
            "for legal/business docs — every party, clause number, obligation, right, penalty, "
            "date, amount, and condition. "
            "Do NOT group or generalize individual entities — individual specificity matters more "
            "than a tidy diagram. Cross-cutting edges (between subgraphs) are especially valuable."
        )
    # xl
    return (
        "DOCUMENT SCALE: VERY LARGE (400+ pages). "
        "MAXIMUM EXHAUSTIVE EXTRACTION MODE — target 96–132 nodes and 108–144 edges. "
        "The raw material covers only a sample of the full document; extract every entity "
        "you can see. Prioritise depth over neatness: include secondary characters, "
        "sub-sub-plots, minor locations, all named concepts, all evidence items, "
        "all formal/legal mechanisms. "
        "Use multiple subgraphs to organise the density (e.g. Characters, Locations, "
        "Events, Evidence, Legal/Formal, Themes). "
        "Cross-subgraph edges are especially valuable — show how disparate threads connect."
    )


def build_conversation_wiki(
    *,
    conversation_id: str,
    collection_name: str,
    conversation_title: str,
    welcome_message: str,
    storage_dir: str | None,
    language: str | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    page_count: int | None = None,
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
    page_count
        Total page count of the source document(s), used to scale extraction
        depth.  When provided, large documents automatically receive more
        aggressive node/edge targets.  Optional — inferred from welcome
        length when absent.
    """
    welcome_message = (welcome_message or "").strip()
    if not welcome_message:
        logger.info(
            "📚 Skipping wiki generation: empty welcome message (conv=%s)",
            conversation_id,
        )
        return None

    if language is None:
        # Strip embedded [mindmap]...[/mindmap] blocks before detection: they
        # are generated from the source document and often contain exotic-script
        # text (e.g. Arabic) that causes lang-detect to mis-identify an English
        # or Polish welcome message as the source document's language.
        import re as _re
        sample = _re.sub(r"\[mindmap\].*?\[/mindmap\]", "", welcome_message, flags=_re.DOTALL)
        language = detect_language(sample[:2000]) or "en"

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

    # Build a scale hint so the prompt adjusts extraction depth to document size.
    document_scale_hint = _build_document_scale_hint(
        page_count=page_count,
        welcome_len=len(welcome_message),
    )

    from .rag import get_llm  # local import — avoids circular at module load

    llm = get_llm()
    chain = WIKI_PROMPT | llm | StrOutputParser()
    model = (
        getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    )

    logger.info(
        "📚 Wiki: building (conv=%s, lang=%s, matches=%d, raw=%d chars, "
        "budget=%dk tokens, scale=%s)",
        conversation_id,
        language,
        chunk_count,
        len(raw_material),
        token_budget // 1000,
        document_scale_hint.split(".")[0],
    )

    try:
        wiki_text, _usage = traced_llm_call(
            chain=chain,
            params={
                "conversation_title": title,
                "language": language,
                "welcome_message": welcome_clipped,
                "raw_material": raw_material,
                "document_scale_hint": document_scale_hint,
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
        wiki_text = wiki_text[:_MAX_OUTPUT_CHARS].rstrip() + "\n\n[... trimmed]"

    logger.info(
        "📚 Wiki generated (conv=%s, lang=%s, %d chars)",
        conversation_id,
        language,
        len(wiki_text),
    )
    return wiki_text


__all__ = ["build_conversation_wiki"]
