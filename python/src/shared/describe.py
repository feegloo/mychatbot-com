from __future__ import annotations

import contextlib
import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .extractors import clean_file_name
from .lang_detect import detect_language
from .llm_instrument import traced_llm_call
from .prompts.welcome import (
    MINDMAP_RULES_EN,
    MINDMAP_RULES_PL,
    WELCOME_QUESTIONS_RULES_EN,
    WELCOME_QUESTIONS_RULES_PL,
    WELCOME_SYSTEM_EN,
    WELCOME_SYSTEM_PL,
)
from .rag import get_llm

logger = logging.getLogger(__name__)

_PAGE_HEADER_RE = re.compile(r"^#\s*Page\s+(\d+)\s*$", re.MULTILINE)
_IDENTITY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_FILENAME_NAME_PART_RE = re.compile(r"^[A-Z][A-Za-zÀ-ÿ'’.-]+$")
_DOMAIN_LIKE_RE = re.compile(r"(?i)^(?:https?://|www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,24}$")
_FILENAME_AUTHOR_STOPWORDS = {
    "the",
    "a",
    "an",
    "guide",
    "ultimate",
    "manual",
    "report",
    "book",
    "notes",
    "lesson",
    "chapter",
    "part",
    "scar",
    "scars",
    "treatment",
    "treatments",
}


class DescribeResult(TypedDict):
    welcome_message: str
    suggested_questions: list[str]


def _tokenize_identity_text(text: str) -> set[str]:
    return {token for token in _IDENTITY_TOKEN_RE.findall(text.lower()) if len(token) >= 2}


def _looks_like_filename_name_part(part: str) -> bool:
    return bool(_FILENAME_NAME_PART_RE.match(part))


def _looks_like_domain_or_url(text: str) -> bool:
    value = text.strip().lower().rstrip(".,;:!?")
    if not value:
        return False
    if "://" in value or value.startswith("www."):
        return True
    compact = re.sub(r"\s+", "", value)
    return bool(_DOMAIN_LIKE_RE.match(compact))


def _is_usable_filename_author_part(part: str) -> bool:
    normalized = re.sub(r"[^A-Za-z0-9.]+", "", part)
    if not normalized:
        return False
    if normalized.lower() in _FILENAME_AUTHOR_STOPWORDS:
        return False
    if _looks_like_domain_or_url(normalized):
        return False
    return _looks_like_filename_name_part(part)


def _extract_filename_author_hint(cleaned_name: str, reference_texts: list[str]) -> str | None:
    stem = Path(cleaned_name).stem
    parts = [part for part in re.split(r"[-_]+", stem) if part]
    if len(parts) < 3:
        return None

    reference_tokens: set[str] = set()
    for text in reference_texts:
        if text:
            reference_tokens.update(_tokenize_identity_text(text))
    if not reference_tokens:
        return None

    for index, part in enumerate(parts):
        normalized = re.sub(r"[^A-Za-z0-9]+", "", part).lower()
        if not normalized:
            continue
        # Both stopwords and content-matching tokens signal the end of the name prefix.
        # Skipping stopwords (as `continue`) used to make them invisible to prefix length
        # checks, causing the prefix to exceed the 1-3 cap. Treating them as boundary
        # markers here gives a clean name like "Nikki-Butler" instead of nothing.
        if normalized in _FILENAME_AUTHOR_STOPWORDS or normalized in reference_tokens:
            prefix = parts[:index]
            if 1 <= len(prefix) <= 3 and all(_is_usable_filename_author_part(chunk) for chunk in prefix):
                return "-".join(prefix)
            break
    return None


def _build_filename_identity_section(
    extracted: list[dict],
    images: list[dict],
    file_metadata: dict[str, dict] | None,
) -> str:
    reference_samples = {
        item.get("file_name", ""): (item.get("text") or "")[:1500]
        for item in [*extracted, *images]
        if item.get("file_name")
    }

    ordered_names = list(dict.fromkeys([*reference_samples.keys(), *((file_metadata or {}).keys())]))
    identity_parts: list[str] = []

    for original_name in ordered_names:
        cleaned_name = clean_file_name(original_name)
        meta = file_metadata.get(original_name, {}) if file_metadata else {}
        reference_texts = [
            str(meta.get("title") or ""),
            str(meta.get("subject") or ""),
            reference_samples.get(original_name, ""),
        ]
        filename_author = _extract_filename_author_hint(cleaned_name, reference_texts)
        metadata_author = ""
        if isinstance(meta, dict):
            metadata_author = str(meta.get("author") or meta.get("artist") or "").strip()

        identity_payload: dict[str, object] = {
            "uploaded_filename": original_name,
            "cleaned_filename": cleaned_name,
        }
        if filename_author:
            identity_payload["preferred_author_from_filename"] = filename_author
        if metadata_author:
            identity_payload["embedded_metadata_author"] = metadata_author
        if filename_author and metadata_author and filename_author != metadata_author:
            identity_payload["author_conflict"] = True
            identity_payload["resolution"] = (
                "Prefer filename-derived author only if it looks like a real person/creator name; if it looks like a URL/site watermark, keep embedded metadata author. Mention the mismatch naturally."
            )

        if len(identity_payload) > 2:
            identity_parts.append(
                f"[{original_name}]\n{json.dumps(identity_payload, ensure_ascii=False)}"
            )

    if not identity_parts:
        return ""

    return (
        "\n\n=====\n"
        "Filename identity hints (use filename-derived author only when it looks like a real person/creator name, not a URL/domain watermark):\n"
        + "\n\n".join(identity_parts)
        + "\n====="
    )


def _fallback_from_metadata(
    extracted: list[dict],
    images: list[dict],
    file_metadata: dict[str, dict] | None,
    language: str | None,
) -> str:
    """Generate a welcome message from metadata when no text could be extracted.

    Builds a human-friendly message that surfaces whatever identifying information
    is available (title, author, page count, file dates) so the user can at least
    understand what document they uploaded.
    """
    file_names = [clean_file_name(doc.get("file_name", "")) for doc in extracted]
    file_names += [clean_file_name(img.get("file_name", "")) for img in images]
    name_list = ", ".join(dict.fromkeys(fn for fn in file_names if fn)) or "document"

    # Collect useful identifying fields from metadata
    title_from_meta = ""
    author_from_meta = ""
    page_count = None
    file_size_bytes = None
    file_created = ""

    if file_metadata:
        for meta in file_metadata.values():
            if not isinstance(meta, dict):
                continue
            if not title_from_meta and meta.get("title"):
                title_from_meta = meta["title"]
            if not author_from_meta and meta.get("author"):
                author_from_meta = meta["author"]
            if page_count is None and meta.get("page_count"):
                with contextlib.suppress(TypeError, ValueError):
                    page_count = int(meta["page_count"])
            if file_size_bytes is None and meta.get("file_size_bytes"):
                with contextlib.suppress(TypeError, ValueError):
                    file_size_bytes = int(meta["file_size_bytes"])
            if not file_created and meta.get("file_created"):
                file_created = str(meta["file_created"])[:10]  # date only

    display_title = title_from_meta or name_list
    msg = f"# {display_title}\n\n"

    # Build context lines for what we know about the document
    known_facts: list[str] = []
    if author_from_meta:
        known_facts.append(f"**Author / Creator:** {author_from_meta}")
    if page_count:
        known_facts.append(f"**Pages:** {page_count}")
    if file_size_bytes:
        size_mb = file_size_bytes / (1024 * 1024)
        if size_mb >= 1:
            known_facts.append(f"**File size:** {size_mb:.1f} MB")
        else:
            known_facts.append(f"**File size:** {file_size_bytes // 1024} KB")
    if file_created:
        known_facts.append(f"**Created:** {file_created}")

    if language == "pl":
        msg += f"Plik **{name_list}** został przesłany, ale nie udało się wyodrębnić treści tekstowej — dokument prawdopodobnie składa się ze skanów lub obrazów."
        if known_facts:
            msg += "\n\nCo udało się odczytać z metadanych pliku:\n" + "\n".join(f"- {f}" for f in known_facts)
            msg += "\n\nNa podstawie nazwy pliku i metadanych można spróbować określić, co to za dokument — zadaj pytanie lub poczekaj, aż OCR przetworzy strony."
        else:
            msg += " Możesz zadać pytanie, a postaram się pomóc."
    else:
        msg += f"**{name_list}** was uploaded, but no text could be extracted — this document likely consists of scanned pages or images."
        if known_facts:
            msg += "\n\nHere's what the file metadata tells us:\n" + "\n".join(f"- {f}" for f in known_facts)
            msg += "\n\nBased on the filename and metadata, we may be able to identify this document — feel free to ask, or wait for OCR to process the pages."
        else:
            msg += " Feel free to ask a question and I'll do my best to help."
    return msg


# Keys to always exclude from the metadata block shown to the model
_META_EXCLUDE_KEYS = {
    "file_name",
    "file_created",
    "file_modified",
    "file_size_bytes",
    "exif",
    "web_detection",
    "identification",
    "producer",
    "creator",
}

# ── Token budget for the describe prompt ─────────────────────────────
# gpt-5.4-nano has a ~400K context window. Keep the char-budget conservative
# so the large-document path engages earlier before token budgets get tight.
_DESCRIBE_MAX_CONTENT_CHARS = 600_000

# Placeholder used when no readable text was extracted but metadata is available.
# The LLM is instructed to use the metadata block to describe the document.
_NO_TEXT_PLACEHOLDER = (
    "[NO READABLE TEXT WAS EXTRACTED — the document likely consists of scanned "
    "images or photographed pages. Use the file metadata section below to identify "
    "the document and describe what it is, who created it, and what it is likely about. "
    "Be warm and helpful. If the filename or metadata hints at a well-known work, "
    "mention it and give useful cultural/historical context.]"
)
# When a document is large, we split the budget: 50% for raw text from start,
# 20% for 2-pass summaries of remaining content, 30% for page summaries.
_TEXT_BUDGET_RATIO = 0.50
_SUMMARY_PASS_BUDGET_RATIO = 0.20
# Threshold for triggering 2-pass summarization (chars of total extracted text)
_TWO_PASS_THRESHOLD = 200_000
# Threshold for triggering multi-part split+synthesize strategy.
# Documents above this size get split into N parts, each generating a
# detailed condensed summary, then synthesized into one welcome message.
# ~600K chars can approach token limits on non-Latin text; split earlier.
_SPLIT_THRESHOLD = 600_000
# Max chars of text to send per partial welcome message call.
# ~150K chars ≈ 37K tokens. Each part produces a detailed "condensed summary"
# of its section (~10 pages worth of detail).
_SPLIT_PART_MAX_CHARS = 150_000
# Delay between sequential LLM calls (seconds) to spread out TPM usage.
# Each call uses ~40K tokens; serial execution avoids bursting past 200K TPM.
_SPLIT_INTER_CALL_DELAY = 2.0
# How many chars of raw book text to include in the synthesis prompt.
# ~200 pages ≈ 400K chars. This gives the synthesis LLM direct access to the
# beginning of the book alongside the condensed summaries.
_SYNTHESIS_RAW_TEXT_CHARS = 400_000
# Whole-book path: if the book fits inside this estimated token budget,
# send the full raw text to the welcome-message prompt instead of truncating.
# For a 400K-context model, keep whole-book mode below the hard request cap
# to leave room for system/developer instructions.
_WHOLE_BOOK_MAX_ESTIMATED_TOKENS = 300_000
# Keep the extracted raw text in memory up to 500 MB as requested.
_WHOLE_BOOK_MEMORY_LIMIT_BYTES = 500 * 1024 * 1024
# Large-book compaction path packs adjacent chapters/page ranges into 4-8 LLM calls.
_BOOK_COMPACTION_MIN_GROUPS = 4
_BOOK_COMPACTION_MAX_GROUPS = 8
_BOOK_COMPACTION_TOKENS_PER_GROUP = 60_000
_RAW_ENDING_CHARS = 120_000
# Max retries for 429 rate-limit errors
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0

# ── Suggested questions rules (appended to describe prompts) ─────────
#
# Output contract: the model appends up to 10 [action:...] markers on a
# SINGLE line at the very end of the welcome message — identical format
# used by the normal RAG answer prompt in rag.py. The frontend parses
# these markers into clickable action buttons (first 3 visible, rest

_ACTION_MARKER_RE = re.compile(r"\[(?:action|akcja):\s*([^\]]+)\]", re.IGNORECASE)

# Emoji / pictograph ranges used to detect a fragment's trailing emoji when
# the model forgets to wrap action prompts in [action:...] markers. Covers
# the common miscellaneous-symbols/pictographs/transport/dingbats blocks
# plus the supplementary planes where most modern emoji live.
_EMOJI_CHAR_RE = re.compile(
    r"[\u2600-\u27BF\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF]"
    r"[\uFE0E\uFE0F\U0001F3FB-\U0001F3FF]?"
)
# Matches a fragment that looks like an orphan action/question: up to ~100
# chars of text ending either with `?` or an emoji (optional variation
# selector / skin tone modifier). Non-greedy so adjacent fragments split
# cleanly when jammed together on a single line.
_BARE_FRAGMENT_RE = re.compile(
    r"[A-Za-z\u00C0-\u024F\u0400-\u04FF][^?\n\[\]]{0,120}?"
    r"(?:\?|"
    r"[\u2600-\u27BF\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF]"
    r"[\uFE0E\uFE0F\U0001F3FB-\U0001F3FF]?"
    r")"
)


def _recover_bare_action_list(text: str) -> tuple[str, list[str]]:
    """Recover action prompts the model emitted as plain prose instead of
    wrapped in ``[action:...]`` markers.

    Some models (especially at high temperature or under long contexts)
    occasionally emit the final action row as a run of bare fragments
    like ``What happens to Bran? Who is George R. R. Martin? Generate
    an image inspired by Westeros 🎨 Write a chapter inspired by ✏️`` instead of
    ``[action:What happens to Bran?] [action:Who is George R. R. Martin?]
    [action:Generate an image inspired by Westeros 🎨] [action:Write a chapter inspired
    by ✏️]``. This heuristic inspects the final paragraph, splits it
    on ``?`` / trailing-emoji boundaries, and if it finds at least three
    fragments that all look like action prompts, it strips them from the
    prose and returns them as a recovered action list.

    Returns ``(cleaned_text, recovered_actions)``. If nothing plausible
    is found, ``recovered_actions`` is an empty list and ``cleaned_text``
    equals the input.
    """
    stripped = text.rstrip()
    # Work on the last paragraph — the action row should always be at the
    # very end of the welcome message.
    split_idx = stripped.rfind("\n\n")
    head = stripped[: split_idx + 2] if split_idx != -1 else ""
    tail = stripped[split_idx + 2:] if split_idx != -1 else stripped

    candidates = [m.group(0).strip() for m in _BARE_FRAGMENT_RE.finditer(tail)]
    candidates = [c for c in candidates if c]
    if len(candidates) < 3:
        return text, []

    # Require that the run of candidates covers most of the tail (i.e. the
    # tail really *is* a bare action list, not a normal paragraph that
    # happens to contain a few questions / emoji). We accept recovery when
    # the joined candidates account for >= 70% of the non-whitespace chars
    # in the tail.
    joined_len = sum(len(c) for c in candidates)
    tail_nonspace = len(re.sub(r"\s+", "", tail))
    if tail_nonspace == 0 or joined_len / tail_nonspace < 0.7:
        return text, []

    recovered = candidates[:10]
    logger.warning(
        f"⚠️ Recovered {len(recovered)} bare action prompts missing [action:] wrappers; "
        f"re-embedding as markers"
    )
    return head.rstrip(), recovered


def _parse_describe_response(response: str) -> tuple[str, list[str]]:
    """Return the welcome message (with ``[action:...]`` markers intact) and
    the extracted action labels as a list.

    The LLM is instructed to emit up to 10 ``[action:...]`` markers on a
    single line at the end of the welcome message (identical format to the
    normal RAG answer). The frontend parses those markers into clickable
    buttons, so we deliberately LEAVE THEM IN the returned welcome text —
    the list is returned separately only so callers can log / forward it
    for "do not repeat these" heuristics on later turns.

    When the model forgets to wrap prompts in ``[action:...]`` we run a
    recovery pass that splits the final paragraph on ``?`` / emoji
    boundaries and re-embeds the fragments.
    """
    text = response.strip()
    actions = [m.group(1).strip() for m in _ACTION_MARKER_RE.finditer(text)]
    # Recovery: if the model produced fewer than 3 wrapped markers, try to
    # rescue a bare-prose action row from the tail of the welcome message.
    if len(actions) < 3:
        cleaned, recovered = _recover_bare_action_list(text)
        if recovered:
            # Merge any existing wrapped actions with the recovered ones,
            # deduplicated, preserving order (wrapped first).
            seen = set()
            merged: list[str] = []
            for a in actions + recovered:
                key = a.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(a.strip())
            text = _embed_actions_in_welcome(cleaned, merged[:10])
            actions = merged[:10]
    return text, actions[:10]


def _embed_actions_in_welcome(welcome: str, actions: list[str]) -> str:
    """Ensure the welcome content ends with a single ``[action:...]`` row
    reflecting ``actions``. Strips any existing markers first so the call
    is idempotent (callers can merge contextual prompts with the model's
    output and re-embed without duplicating buttons).
    """
    stripped = _ACTION_MARKER_RE.sub("", welcome).rstrip()
    stripped = re.sub(r"\n[ \t]*\n\s*$", "", stripped).rstrip()
    if not actions:
        return stripped
    action_line = " ".join(f"[action:{q}]" for q in actions if q and q.strip())
    if not action_line:
        return stripped
    return f"{stripped}\n\n{action_line}" if stripped else action_line


def _estimate_total_text_len(extracted: list[dict]) -> int:
    """Return the total character count across all extracted documents."""
    return sum(len(doc.get("text") or "") for doc in extracted)


def _estimate_word_count(text: str) -> int:
    """Count words quickly without a heavyweight tokenizer."""
    if not text.strip():
        return 0
    return len(re.findall(r"\S+", text))


# ── Token budgeting (tiktoken-backed for accurate non-Latin counts) ──
# gpt-5.4-nano has a ~400K context window. Hard-cap requests at 400K tokens.
_MAX_REQUEST_TOKENS = 400_000
# Safe budget for the *content* portion of a single LLM call.  The system
# prompts in this module are large (~5-15K tokens of rules), so we reserve
# extra headroom when packing raw text.
_MAX_CONTENT_TOKENS = 350_000

_tiktoken_enc = None


def _get_tiktoken_encoder():
    """Lazy-load the tiktoken cl100k_base encoder (None if unavailable)."""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            import tiktoken

            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception as e:  # pragma: no cover - tiktoken is a hard dep
            logger.warning(f"⚠️ tiktoken unavailable ({e}); falling back to char estimate")
            _tiktoken_enc = False
    return _tiktoken_enc or None


def _count_tokens_accurate(text: str) -> int:
    """Accurate tiktoken-based count.  Critical for Arabic / CJK scripts
    where each character often maps to a full token, making char/4 estimates
    drastically too low and causing 300K-token per-request limits to hit."""
    if not text:
        return 0
    enc = _get_tiktoken_encoder()
    if enc is None:
        # Conservative fallback: treat each char as ~1 token for non-Latin.
        if any(ord(c) > 0x7F for c in text[:2000]):
            return len(text)
        return max(len(text) // 4, 1)
    return len(enc.encode(text, disallowed_special=()))


def _estimate_token_count(text: str, word_count: int | None = None) -> int:
    """Accurate token count (uses tiktoken when available).

    Kept for back-compat with earlier call sites that passed ``word_count``;
    the word_count argument is ignored when the tokenizer is available.
    """
    try:
        return _count_tokens_accurate(text)
    except Exception:
        words = word_count if word_count is not None else _estimate_word_count(text)
        return max(len(text) // 4, int(words * 1.35))


def _truncate_text_to_token_budget(text: str, max_tokens: int) -> str:
    """Truncate text so its tiktoken count is ≤ max_tokens.

    Used to enforce a hard safety cap on per-call content.  Uses binary
    search on character length since encoding is roughly monotonic in
    prefix length.
    """
    if max_tokens <= 0 or not text:
        return ""
    tokens = _count_tokens_accurate(text)
    if tokens <= max_tokens:
        return text

    low, high = 0, len(text)
    # Start from a char-ratio estimate to avoid many iterations for huge docs
    ratio = max_tokens / max(tokens, 1)
    best = int(len(text) * ratio * 0.95)
    while low < high:
        if _count_tokens_accurate(text[:best]) <= max_tokens:
            low = best + 1
            best = min(high, best + max(1, (high - best) // 2))
        else:
            high = best
            best = max(low, best - max(1, (best - low) // 2))
        if best in (low, high):
            break
    # Final safety: linear shrink if still over budget
    while best > 0 and _count_tokens_accurate(text[:best]) > max_tokens:
        best = int(best * 0.9)
    logger.info(
        f"✂️  Truncated text from {len(text):,} chars → {best:,} chars "
        f"to fit {max_tokens:,} token budget (was ~{tokens:,} tokens)"
    )
    return text[:best]


def _extract_pages(text: str) -> list[tuple[int, str]]:
    """Split extracted PDF text into page-numbered sections."""
    if not text.strip():
        return []

    matches = list(_PAGE_HEADER_RE.finditer(text))
    if not matches:
        return [(1, text.strip())]

    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages.append((page_number, text[start:end].strip()))
    return pages


def _resolve_page_count(
    extracted: list[dict],
    file_metadata: dict[str, dict] | None,
    page_summaries: list[dict] | None,
) -> int:
    """Resolve page count from metadata first, then from extracted page markers."""
    if file_metadata:
        for meta in file_metadata.values():
            page_count = meta.get("page_count") if isinstance(meta, dict) else None
            if isinstance(page_count, int) and page_count > 0:
                return page_count

    if page_summaries:
        pages = [ps.get("page") for ps in page_summaries if isinstance(ps.get("page"), int)]
        if pages:
            return max(pages)

    detected_pages: list[int] = []
    for doc in extracted:
        detected_pages.extend(page_number for page_number, _text in _extract_pages(doc.get("text") or ""))
    return max(detected_pages) if detected_pages else 0


def _build_page_summary_block(page_summaries: list[dict]) -> str:
    """Build a compact summary-per-page block from page summaries."""
    lines: list[str] = []
    for ps in page_summaries:
        page = ps.get("page", "?")
        fname = clean_file_name(ps.get("file_name", ""))
        summary = ps.get("summary", "").strip()
        if summary:
            prefix = f"[{fname} p.{page}]" if fname else f"[p.{page}]"
            lines.append(f"{prefix} {summary}")
    return "\n".join(lines)


def _invoke_with_retry(
    chain, params: dict, label: str = "LLM call", *, conversation_id: str | None = None,
) -> str:
    """Invoke a LangChain chain with retry on 429 rate-limit errors.

    Wraps each attempt with OTel tracing, metrics, and prompt history logging.
    """
    model = "unknown"
    try:
        llm = get_llm()
        model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    except Exception:
        pass

    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            response_text, _usage = traced_llm_call(
                chain=chain,
                params=params,
                operation=f"describe.{label}",
                model=model,
                conversation_id=conversation_id,
                rendered_prompt=str(params)[:500_000],
            )
            return response_text
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
            if is_rate_limit and attempt < _LLM_MAX_RETRIES:
                delay = _LLM_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"⚠️ Rate limit hit for {label} (attempt {attempt + 1}), "
                    f"retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            raise


def _summarize_text_chunk(text: str, chunk_label: str, language: str) -> str:
    """Summarize a large chunk of text into a dense condensed summary.

    Used in the 2-pass strategy for very large documents: each half of the
    document is summarized separately, then combined with raw text from the
    beginning for the final welcome message prompt.
    """
    if not text.strip():
        return ""

    if language == "pl":
        system_msg = (
            "Jesteś ekspertem od streszczania dokumentów. Otrzymasz fragment dużego dokumentu. "
            "Stwórz gęste, szczegółowe streszczenie zachowując WSZYSTKIE kluczowe fakty, nazwiska, daty, kwoty, "
            "wnioski i argumenty. Dla każdej strony/sekcji napisz 2-3 zdania wyciągając najważniejsze informacje. "
            "Zachowaj oryginalną strukturę i kolejność. NIE pomijaj ważnych szczegółów. "
            "Pisz zwięźle ale kompletnie — to streszczenie będzie jedynym źródłem informacji o tej części dokumentu."
        )
    else:
        system_msg = (
            "You are an expert document summarizer. You will receive a section of a large document. "
            "Create a dense, detailed summary preserving ALL key facts, names, dates, amounts, "
            "conclusions, and arguments. For each page/section, write 2-3 sentences extracting the crucial information. "
            "Maintain the original structure and order. Do NOT skip important details. "
            "Write concisely but completely — this summary will be the only source of information about this part of the document."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            ("human", f"Document section ({chunk_label}):\n\n{{text}}"),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    safe_text = _truncate_text_to_token_budget(text, _MAX_CONTENT_TOKENS)
    result = _invoke_with_retry(chain, {"text": safe_text}, label=f"2-pass summary ({chunk_label})")
    logger.info(f"📝 2-pass summary for {chunk_label}: {len(safe_text)} chars → {len(result)} chars")
    return result.strip()


def _split_text_into_parts(full_text: str, max_chars_per_part: int) -> list[str]:
    """Split text into roughly equal parts, each ≤ max_chars_per_part.

    Tries to split at page boundaries (# Page N headers) for cleaner breaks.
    """
    if len(full_text) <= max_chars_per_part:
        return [full_text]

    n_parts = math.ceil(len(full_text) / max_chars_per_part)
    target_size = len(full_text) // n_parts
    parts: list[str] = []
    start = 0

    for i in range(n_parts):
        if i == n_parts - 1:
            parts.append(full_text[start:])
            break

        end = start + target_size
        # Try to find a page boundary near the target split point
        search_start = max(start, end - 2000)
        search_end = min(len(full_text), end + 2000)
        search_region = full_text[search_start:search_end]

        # Look for "# Page N" markers to split cleanly
        best_split = -1
        import re

        for m in re.finditer(r"\n# Page \d+", search_region):
            candidate = search_start + m.start()
            if candidate > start:
                best_split = candidate

        if best_split > start:
            parts.append(full_text[start:best_split])
            start = best_split
        else:
            # Fall back to splitting at a paragraph boundary
            newline_pos = full_text.rfind("\n\n", start + target_size - 1000, end + 1000)
            if newline_pos > start:
                parts.append(full_text[start:newline_pos])
                start = newline_pos
            else:
                parts.append(full_text[start:end])
                start = end

    return [p for p in parts if p.strip()]


def _build_book_sections(
    *,
    pages: list[tuple[int, str]],
    chapters: list[dict] | None,
    total_pages: int,
    estimated_tokens: int,
) -> list[dict]:
    """Build chapter-based or fallback page-range sections for large books."""
    if not pages:
        return []

    last_page = max(page_number for page_number, _text in pages)
    normalized_chapters: list[dict] = []

    if chapters:
        for index, chapter in enumerate(chapters, start=1):
            start_page = int(chapter.get("start_page") or chapter.get("pageFrom") or 0)
            end_page = int(chapter.get("end_page") or chapter.get("pageTo") or 0)
            if start_page <= 0 or end_page < start_page:
                continue
            name = (
                chapter.get("chapter_name")
                or chapter.get("name")
                or chapter.get("title")
                or f"Chapter {index}"
            )
            normalized_chapters.append(
                {
                    "name": str(name),
                    "start_page": start_page,
                    "end_page": min(end_page, last_page),
                }
            )

    if normalized_chapters:
        return normalized_chapters

    target_groups = max(
        _BOOK_COMPACTION_MIN_GROUPS,
        min(_BOOK_COMPACTION_MAX_GROUPS, math.ceil(estimated_tokens / _BOOK_COMPACTION_TOKENS_PER_GROUP)),
    )
    target_groups = max(1, min(target_groups, len(pages)))
    pages_per_group = max(1, math.ceil(max(total_pages, last_page) / target_groups))

    sections: list[dict] = []
    current_start = 1
    while current_start <= last_page:
        current_end = min(last_page, current_start + pages_per_group - 1)
        sections.append(
            {
                "name": f"Pages {current_start}-{current_end}",
                "start_page": current_start,
                "end_page": current_end,
            }
        )
        current_start = current_end + 1

    return sections


def _pack_book_sections(section_ranges: list[dict], total_pages: int, estimated_tokens: int) -> list[dict]:
    """Pack adjacent sections into 4-8 larger LLM requests."""
    if not section_ranges:
        return []

    target_groups = max(
        _BOOK_COMPACTION_MIN_GROUPS,
        min(_BOOK_COMPACTION_MAX_GROUPS, math.ceil(estimated_tokens / _BOOK_COMPACTION_TOKENS_PER_GROUP)),
    )
    target_groups = max(1, min(target_groups, len(section_ranges)))
    target_pages = max(1, math.ceil(max(total_pages, 1) / target_groups))

    packed: list[dict] = []
    current_sections: list[dict] = []
    current_pages = 0

    for section in section_ranges:
        section_pages = max(1, section["end_page"] - section["start_page"] + 1)
        should_flush = (
            current_sections
            and current_pages + section_pages > target_pages
            and len(packed) < target_groups - 1
        )
        if should_flush:
            packed.append(
                {
                    "sections": current_sections,
                    "start_page": current_sections[0]["start_page"],
                    "end_page": current_sections[-1]["end_page"],
                }
            )
            current_sections = []
            current_pages = 0

        current_sections.append(section)
        current_pages += section_pages

    if current_sections:
        packed.append(
            {
                "sections": current_sections,
                "start_page": current_sections[0]["start_page"],
                "end_page": current_sections[-1]["end_page"],
            }
        )

    return packed


def _build_group_text(pages: list[tuple[int, str]], group: dict) -> str:
    """Build text for one packed chapter/page-range group."""
    page_map = {page_number: text for page_number, text in pages}
    blocks: list[str] = []

    for section in group["sections"]:
        section_pages: list[str] = []
        for page_number in range(section["start_page"], section["end_page"] + 1):
            page_text = page_map.get(page_number, "")
            if page_text.strip():
                section_pages.append(f"# Page {page_number}\n\n{page_text}")
        if section_pages:
            blocks.append(
                f"===SECTION===\n"
                f"name: {section['name']}\n"
                f"pages: {section['start_page']}-{section['end_page']}\n\n"
                + "\n\n".join(section_pages)
            )

    return "\n\n-----\n\n".join(blocks)


def _generate_partial_welcome(
    part_text: str,
    part_index: int,
    total_parts: int,
    file_list: str,
    language: str,
    metadata_section: str,
) -> str:
    """Generate a detailed condensed summary for one part of a large document.

    Unlike a short welcome message, this produces a rich, dense summary
    (equivalent to ~10 pages of detail) that captures all key facts, characters,
    events, and concepts. These detailed summaries are later synthesized into
    the final welcome message.
    """
    if language == "pl":
        system_msg = (
            "Tworzysz SZCZEGÓŁOWE STRESZCZENIE CZĘŚCI dużego dokumentu. "
            f"To jest część {part_index + 1} z {total_parts}.\n\n"
            "Twoim zadaniem jest wyciągnąć WSZYSTKIE istotne informacje z tego fragmentu "
            "i stworzyć gęste, szczegółowe streszczenie — jakby skrócić 500 stron do 10.\n\n"
            "Twoja odpowiedź MUSI zawierać:\n"
            "- **Tytuł i autor** (tylko jeśli to część 1 i możesz je rozpoznać)\n"
            "- **WSZYSTKIE imiona postaci/osób** z pogrubionymi nazwami\n"
            "- **Kluczowe wydarzenia** w kolejności chronologicznej\n"
            "- **Miejsca, daty, kwoty, statystyki** — każda konkretna liczba\n"
            "- **Główne tematy i argumenty** z tej części\n"
            "- **Relacje między postaciami/elementami**\n"
            "- **Zwroty akcji, kluczowe cytaty, wnioski**\n\n"
            "Pisz gęsto i szczegółowo — to streszczenie będzie jedynym źródłem "
            "informacji o tej części dokumentu. Każde zdanie musi nieść konkretne fakty.\n"
            "NIE pisz ogólników. NIE pytaj użytkownika. NIE używaj [source:N].\n"
            "Odpowiadaj po polsku."
        )
    else:
        system_msg = (
            "You are creating a DETAILED CONDENSED SUMMARY of ONE PART of a large document. "
            f"This is part {part_index + 1} of {total_parts}.\n\n"
            "Your job is to extract ALL important information from this section and create "
            "a dense, detailed summary — as if condensing 500 pages into 10.\n\n"
            "Your response MUST include:\n"
            "- **Title and author** (only if this is part 1 and you can identify them)\n"
            "- **ALL character/person names** with bold formatting\n"
            "- **Key events** in chronological order\n"
            "- **Places, dates, amounts, statistics** — every specific number\n"
            "- **Main themes and arguments** from this section\n"
            "- **Relationships between characters/elements**\n"
            "- **Plot twists, key quotes, conclusions**\n\n"
            "Write densely and in detail — this summary will be the ONLY source of information "
            "about this part of the document. Every sentence must carry concrete facts.\n"
            "Do NOT write generalities. Do NOT ask the user anything. Do NOT use [source:N].\n"
            "Reply in the same language as the content."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            (
                "human",
                "Files: {file_list}\n\nContent (part {part_num}/{total}):\n{content}{metadata_section}",
            ),
        ]
    )

    # Hard-cap the part text so this single request cannot exceed the per-call
    # token limit (critical for non-Latin scripts like Arabic where
    # char/4 estimates drastically undercount).
    safe_part_text = _truncate_text_to_token_budget(part_text, _MAX_CONTENT_TOKENS)

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(
        chain,
        {
            "file_list": file_list,
            "part_num": str(part_index + 1),
            "total": str(total_parts),
            "content": safe_part_text,
            "metadata_section": metadata_section,
        },
        label=f"partial summary {part_index + 1}/{total_parts}",
    )
    logger.info(
        f"📝 Detailed summary {part_index + 1}/{total_parts}: "
        f"{len(safe_part_text)} chars text → {len(result)} chars summary"
    )
    return result.strip()


def _generate_compacted_book_group(
    group_text: str,
    group_index: int,
    total_groups: int,
    file_list: str,
    language: str,
    metadata_section: str,
) -> str:
    """Compact one packed set of chapters/page-ranges into structured summaries."""
    if language == "pl":
        system_msg = (
            "Otrzymasz kilka kolejnych rozdziałów lub zakresów stron tej samej książki. "
            f"To pakiet {group_index + 1} z {total_groups}.\n\n"
            "Dla KAŻDEJ sekcji zachowaj osobny blok w dokładnie takim formacie:\n"
            "===SECTION===\n"
            "name: <nazwa sekcji>\n"
            "pages: <zakres stron>\n"
            "summary:\n"
            "- ...\n"
            "- ...\n\n"
            "Skróć każdą sekcję do około 10-15% objętości, ale zachowaj fabułę, bohaterów, "
            "fakty, liczby, miejsca, relacje, zwroty akcji i ważne szczegóły. "
            "Nie mieszaj sekcji ze sobą. Nie pomijaj zakończeń scen i ważnych przejść. "
            "Pisz po polsku."
        )
    else:
        system_msg = (
            "You will receive several consecutive chapters or page ranges from the same book. "
            f"This is pack {group_index + 1} of {total_groups}.\n\n"
            "For EACH section, keep a separate block in exactly this format:\n"
            "===SECTION===\n"
            "name: <section name>\n"
            "pages: <page range>\n"
            "summary:\n"
            "- ...\n"
            "- ...\n\n"
            "Compress each section to about 10-15% of its volume while preserving plot, people, "
            "facts, numbers, places, relationships, twists, and key details. "
            "Do not merge sections together. Do not skip endings of scenes or important transitions. "
            "Reply in the same language as the content."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            (
                "human",
                "Files: {file_list}\n\nSections to compact:\n{content}{metadata_section}",
            ),
        ]
    )

    # Hard-cap the group text so this single request cannot exceed the per-call
    # token limit (critical for non-Latin scripts like Arabic).
    safe_group_text = _truncate_text_to_token_budget(group_text, _MAX_CONTENT_TOKENS)

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(
        chain,
        {
            "file_list": file_list,
            "content": safe_group_text,
            "metadata_section": metadata_section if group_index == 0 else "",
        },
        label=f"book compact {group_index + 1}/{total_groups}",
    )
    logger.info(
        f"📝 Book compact {group_index + 1}/{total_groups}: "
        f"{len(safe_group_text)} chars → {len(result)} chars"
    )
    return result.strip()


def _synthesize_welcome_messages(
    partial_messages: list[str],
    file_list: str,
    language: str,
    metadata_section: str,
    raw_beginning: str = "",
    raw_ending: str = "",
) -> tuple[str, list[str]]:
    """Synthesize N detailed condensed summaries into one final welcome message.

    Returns (welcome_message, suggested_questions).

    When raw_beginning is provided, the LLM also receives the first ~200 pages
    of raw book text alongside the condensed summaries — giving it direct access
    to the author's voice, style, and opening content for a smarter result.
    """
    if len(partial_messages) == 1 and not raw_beginning:
        return partial_messages[0], []

    combined_partials = "\n\n---\n\n".join(
        f"[Detailed summary of section {i + 1} of {len(partial_messages)}]\n{msg}"
        for i, msg in enumerate(partial_messages)
    )

    # ── Budget raw_beginning / raw_ending to fit the per-call token limit ──
    # Partials and metadata are always included in full.  Raw text is a
    # best-effort addition — trimmed (or dropped) to fit _MAX_CONTENT_TOKENS.
    partials_tokens = _count_tokens_accurate(combined_partials)
    metadata_tokens = _count_tokens_accurate(metadata_section)
    remaining_budget = _MAX_CONTENT_TOKENS - partials_tokens - metadata_tokens
    if remaining_budget < 0:
        # Partials alone exceed the budget — recursively compress them by
        # halving into two shorter summaries, then continue.
        logger.warning(
            f"⚠️ Partials exceed budget ({partials_tokens} > {_MAX_CONTENT_TOKENS} tokens); "
            f"recursively compressing before synthesis"
        )
        midpoint = len(partial_messages) // 2 or 1
        left = _summarize_text_chunk(
            "\n\n---\n\n".join(partial_messages[:midpoint]),
            "first half of summaries",
            language,
        )
        right = _summarize_text_chunk(
            "\n\n---\n\n".join(partial_messages[midpoint:]),
            "second half of summaries",
            language,
        )
        partial_messages = [m for m in (left, right) if m.strip()]
        combined_partials = "\n\n---\n\n".join(
            f"[Detailed summary of section {i + 1} of {len(partial_messages)}]\n{msg}"
            for i, msg in enumerate(partial_messages)
        )
        partials_tokens = _count_tokens_accurate(combined_partials)
        remaining_budget = _MAX_CONTENT_TOKENS - partials_tokens - metadata_tokens

    # Split remaining budget between beginning (70%) and ending (30%) — keeping
    # context about how the document opens is usually more valuable than how it
    # ends, but both help the synthesizer.
    begin_budget = max(0, int(remaining_budget * 0.7))
    end_budget = max(0, remaining_budget - begin_budget)
    safe_beginning = _truncate_text_to_token_budget(raw_beginning, begin_budget) if raw_beginning else ""
    safe_ending = _truncate_text_to_token_budget(raw_ending, end_budget) if raw_ending else ""

    raw_parts: list[str] = []
    if safe_beginning:
        raw_parts.append(
            f"Raw text from the beginning of the document "
            f"(first ~{len(safe_beginning) // 1000}K chars):\n{safe_beginning}"
        )
    if safe_ending:
        raw_parts.append(
            f"Raw text from the ending of the document "
            f"(last ~{len(safe_ending) // 1000}K chars):\n{safe_ending}"
        )

    raw_block = ""
    if raw_parts:
        raw_block = "\n\n=====\n" + "\n\n-----\n\n".join(raw_parts) + "\n====="

    if language == "pl":
        system_msg = (
            "Otrzymujesz SZCZEGÓŁOWE STRESZCZENIA różnych CZĘŚCI tego samego dużego dokumentu "
            "(książki/PDF). Każde streszczenie obejmuje inną sekcję i zawiera gęste, "
            "szczegółowe informacje o treści.\n\n"
            "Dodatkowo możesz otrzymać surowy tekst z początku dokumentu — wykorzystaj go "
            "aby uchwycić styl autora, ton i kontekst otwierający.\n\n"
            "Twoim zadaniem jest POŁĄCZYĆ te streszczenia w jedną, spójną wiadomość powitalną.\n\n"
        ) + MINDMAP_RULES_PL + (
            "\nTwoja odpowiedź MUSI składać się z trzech części:\n"
            "1. **Tytuł**: # Tytuł dokumentu - Autor\n"
            "2. **Opis**: 3-5 zdań podsumowujących CAŁY dokument. Zachowaj najważniejsze "
            "fakty, nazwiska, miejsca z WSZYSTKICH części. Używaj **pogrubienia** selektywnie — tylko liczby, nazwy własne i najważniejszy 1-2 termin na akapit.\n"
            "3. **Ekspercki wgląd**: 2-3 zdania wartościowej analizy.\n\n"
            "WAŻNE: Musisz zsyntetyzować informacje z WSZYSTKICH streszczeń, nie tylko pierwszego. "
            "Celuj w 250-350 słów łącznie (2-5 akapitów, najczęściej 4, czasem 3, rzadko 5). NIE pytaj użytkownika. NIE używaj [source:N]. "
            "Używaj emoji profesjonalnie (📖, ⚔️, 🗺️ itp.).\n"
            "Odpowiadaj po polsku."
        ) + WELCOME_QUESTIONS_RULES_PL
    else:
        system_msg = (
            "You are receiving DETAILED CONDENSED SUMMARIES of different PARTS of the same "
            "large document (book/PDF). Each summary covers a different section and contains "
            "dense, detailed information about the content.\n\n"
            "You may also receive raw text from the beginning of the document — use it "
            "to capture the author's voice, tone, and opening context.\n\n"
            "Your job is to MERGE these summaries into one cohesive welcome message.\n\n"
        ) + MINDMAP_RULES_EN + (
            "\nYour response MUST have three parts:\n"
            "1. **Title**: # Document Title 🔖 — after the title (and optional \" - Author Name\"), append ONE contextually appropriate emoji that fits the document topic (e.g. 🚗 driving, 🔬 science/lab, ⚖️ legal, 📈 finance, 🍳 cooking, 💻 code, 🎭 fiction). Only known author gets appended; do NOT write \"Unknown author\".\n"
            "2. **Description**: 3-5 sentences summarizing the ENTIRE document. Preserve the key "
            "facts, names, places from ALL parts. Use **bold** selectively — only for exact numbers, proper names, and the most critical 1-2 terms per paragraph.\n"
            "3. **Expert insight**: 1-2 sentences of valuable analysis.\n\n"
            "IMPORTANT: Synthesize information from ALL summaries, not just the first. "
            "Aim for 250-300 words total (2-5 paragraphs, usually 3, sometimes 4, rarely 5). Do NOT ask the user anything. Do NOT use [source:N]. "
            "Use emoji professionally (📖, ⚔️, 🗺️ etc.).\n"
            "Reply in the same language as the content."
        ) + WELCOME_QUESTIONS_RULES_EN

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            (
                "human",
                "Files: {file_list}\n\nDetailed summaries to synthesize:\n\n{partials}{raw_block}{metadata_section}",
            ),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(
        chain,
        {
            "file_list": file_list,
            "partials": combined_partials,
            "raw_block": raw_block,
            "metadata_section": metadata_section,
        },
        label="synthesis",
    )
    logger.info(
        f"📝 Synthesized {len(partial_messages)} summaries "
        f"(+ {len(safe_beginning)} chars raw start, {len(safe_ending)} chars raw end) → {len(result)} chars final"
    )
    return _parse_describe_response(result)


def _detect_empty_file_names(
    file_metadata: dict[str, dict] | None,
    extracted: list[dict],
    images: list[dict],
) -> list[str]:
    """Return display names of files that are confirmed empty (0 bytes, no content).

    Only flags a file as empty when BOTH conditions hold:
    - its ``file_size_bytes`` metadata field is explicitly 0
    - no text was extracted and no images were produced for that upload
    (avoids false positives when metadata extraction itself fails)
    """
    if not file_metadata:
        return []
    has_any_content = any((doc.get("text") or "").strip() for doc in extracted) or images
    if has_any_content:
        return []
    return [
        clean_file_name(fname)
        for fname, meta in file_metadata.items()
        if isinstance(meta, dict) and meta.get("file_size_bytes") == 0
    ]


def _make_empty_file_welcome(empty_names: list[str], language: str) -> str:
    """Return a direct, helpful welcome message for an empty (0-byte) file upload."""
    display = ", ".join(empty_names) if empty_names else "uploaded file"
    if language == "pl":
        body = (
            f"# {display}\n\n"
            f"⚠️ Przesłany plik **{display}** jest pusty (0 bajtów) — nie znaleziono żadnej treści. "
            f"Sprawdź, czy wybrałeś właściwy plik i spróbuj ponownie z plikiem zawierającym treść."
        )
        actions = ["Prześlij inny plik", "Jakie formaty są obsługiwane?"]
    else:
        body = (
            f"# {display}\n\n"
            f"⚠️ The uploaded file **{display}** is empty (0 bytes) — no content was found inside. "
            f"Please check whether you meant to upload a different file and try again."
        )
        actions = ["Upload a different file", "What file formats are supported?"]
    action_line = " ".join(f"[action:{q}]" for q in actions)
    return f"{body}\n\n{action_line}"


def _describes_woman_nonprofessional(text: str) -> bool:
    """Return True when the image description indicates a woman is the primary
    subject and the context is NOT professional/formal.

    Used to gate the 'Enhance image for social media' action so it only appears
    for casual portraits/selfies of women, not abstract art, landscapes, products,
    documents, or professional headshots.
    """
    text_lower = text.lower()

    # Strip embedded action markers so they don't pollute the analysis
    clean = _ACTION_MARKER_RE.sub("", text_lower)

    # ── Woman / female primary-subject signals (English + Polish) ──
    woman_terms = [
        "woman", "women", "female", "girl", "lady",
        "kobieta", "kobiet", "kobiety", "kobietą", "kobiecą",
        "dziewczyn", "pani ", "pani,", "pani.",
    ]
    if not any(term in clean for term in woman_terms):
        return False

    # ── Professional / formal-context exclusions (English + Polish) ──
    professional_terms = [
        "professional", "business", "corporate", "office", "headshot",
        "resume", "cv ", "linkedin", "executive", "ceo", "employee",
        "formal portrait", "id photo", "id card", "badge", "conference",
        "blazer", "suit ", " suit,", " suit.",
        "biznes", "zawodow", "biuro", "korporac",
        "garnitur", "marynark", "legitymacja", "identyfikator",
        "profil zawodowy", "zdjęcie profilowe",
    ]
    if any(term in clean for term in professional_terms):
        return False

    return True


def _inject_social_media_action(welcome: str, images: list[dict]) -> str:
    """Inject an 'Enhance image for social media' action button into the welcome
    message when the user uploaded a standalone image file (not a PDF page image)
    showing a woman as the primary subject in a non-professional context.

    The action uses ``|ref:FILENAME`` so the frontend can pass the original file
    to the image-generation pipeline as a reference image.
    """
    if not images:
        return welcome

    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".heic", ".avif"}
    # Only inject for actual uploaded image files — not PDF-extracted page images.
    # PDF page images have a numeric ``page`` field; standalone uploads have page=None.
    first_image_file: str | None = None
    for img in images:
        if img.get("page") is not None:
            continue
        fname = img.get("file_name", "")
        if Path(fname).suffix.lower() in image_extensions:
            first_image_file = fname
            break

    if not first_image_file:
        return welcome

    # Only offer the social-media enhancement for casual portraits/selfies of
    # women — not for abstract art, landscapes, products, documents, or
    # professional headshots.
    if not _describes_woman_nonprofessional(welcome):
        return welcome

    action_label = f"Enhance image for social media ❤️|ref:{first_image_file}"

    # Parse existing actions out, insert ours at position 1 (after the first
    # action so the most relevant document question stays first), then re-embed.
    existing = [m.group(1).strip() for m in _ACTION_MARKER_RE.finditer(welcome)]
    # Avoid duplicating the action if it was somehow already present.
    if any("enhance image for social media" in a.lower() for a in existing):
        return welcome

    insert_at = min(1, len(existing))
    merged = existing[:insert_at] + [action_label] + existing[insert_at:]
    return _embed_actions_in_welcome(welcome, merged)


def describe_documents(
    extracted: list[dict],
    images: list[dict],
    language: str | None = None,
    file_metadata: dict[str, dict] | None = None,
    page_summaries: list[dict] | None = None,
    file_names: list[str] | None = None,
    file_types: dict[str, str] | None = None,
    chapters: list[dict] | None = None,
    ocr_in_progress: bool = False,
    total_pages_hint: int | None = None,
    ocr_pages_done: int | None = None,
) -> DescribeResult:
    """Generate a welcome message with a # Title, description, and expert insight,
    plus up to 10 suggested questions — all from a single LLM call.

    Returns a DescribeResult dict with 'welcome_message' and 'suggested_questions'.

    Uses the beginning of extracted text (no embeddings/RAG) so the response
    is as quick as possible. When a whole book fits inside the budget, the full
    raw text is sent in one call. Larger books are compacted chapter-by-chapter
    or page-range-by-page-range, then synthesized with raw beginning/end text.
    """
    total_chars = _estimate_total_text_len(extracted)

    # ── Pre-compute metadata block and language (needed by all strategies) ──
    metadata_block = ""
    if file_metadata:
        meta_parts: list[str] = []
        for fname, meta in file_metadata.items():
            try:
                useful = {k: v for k, v in meta.items() if k not in _META_EXCLUDE_KEYS and v}
                if useful:
                    meta_parts.append(
                        f"[{fname}]\n{json.dumps(useful, ensure_ascii=False, default=str)}"
                    )
            except Exception as e:
                logger.warning(f"⚠️ Failed to format metadata for {fname}: {e}")
        if meta_parts:
            metadata_block = "\n\n".join(meta_parts)

    metadata_section = ""
    if metadata_block:
        metadata_section = (
            f"\n\n=====\nFile metadata (from EXIF / PDF info):\n{metadata_block}\n====="
        )

    filename_identity_section = _build_filename_identity_section(extracted, images, file_metadata)
    if filename_identity_section:
        metadata_section += filename_identity_section

    # Build a supplemental identification block with normally-excluded fields
    # (file size, creation date).  Appended only when there is no text to read,
    # so the LLM has maximum identifying information for "mystery document" cases.
    _META_IDENTIFY_KEYS = {"file_size_bytes", "file_created", "file_modified"}
    identification_parts: list[str] = []
    if file_metadata:
        for fname, meta in file_metadata.items():
            if not isinstance(meta, dict):
                continue
            ident = {k: v for k, v in meta.items() if k in _META_IDENTIFY_KEYS and v}
            if ident:
                identification_parts.append(
                    f"[{fname}]\n{json.dumps(ident, ensure_ascii=False, default=str)}"
                )
    _identification_section = (
        "\n\n=====\nFile identification hints (size / dates):\n"
        + "\n\n".join(identification_parts)
        + "\n====="
        if identification_parts
        else ""
    )

    file_names = [clean_file_name(doc.get("file_name", "")) for doc in extracted]
    file_names += [clean_file_name(img.get("file_name", "")) for img in images]
    file_list = ", ".join(dict.fromkeys(fn for fn in file_names if fn))
    all_text = "\n\n---\n\n".join(
        (doc.get("text") or "") for doc in extracted if (doc.get("text") or "").strip()
    )
    word_count = _estimate_word_count(all_text)
    estimated_tokens = _estimate_token_count(all_text, word_count)
    total_pages = _resolve_page_count(extracted, file_metadata, page_summaries)

    if language is None:
        sample_text = ""
        for doc in extracted:
            sample_text = (doc.get("text") or "")[:2000]
            if sample_text:
                break
        language = detect_language(sample_text) if sample_text else "en"

    # ── Empty file: return immediate feedback, no LLM call needed ────
    empty_names = _detect_empty_file_names(file_metadata, extracted, images)
    if empty_names:
        logger.info(f"📭 Empty file upload detected: {empty_names}")
        msg = _make_empty_file_welcome(empty_names, language)
        suggested = (
            ["Prześlij inny plik", "Jakie formaty są obsługiwane?"]
            if language == "pl"
            else ["Upload a different file", "What file formats are supported?"]
        )
        return DescribeResult(welcome_message=msg, suggested_questions=suggested)

    if all_text and len(all_text.encode("utf-8")) <= _WHOLE_BOOK_MEMORY_LIMIT_BYTES:
        logger.info(
            f"📚 Welcome input stats: pages={total_pages or '?'} words={word_count} "
            f"estimated_tokens={estimated_tokens} chars={len(all_text)}"
        )

    # ── Strategy 1: Whole-book prompt when it fits ──────────────────
    if all_text and estimated_tokens <= _WHOLE_BOOK_MAX_ESTIMATED_TOKENS:
        logger.info(
            f"📚 Whole-book welcome strategy: {total_pages or '?'} pages, {word_count} words, "
            f"~{estimated_tokens} tokens"
        )

    # ── Strategy 2: Chapter/page-range compaction for large books ───
    elif all_text and len(extracted) == 1 and total_pages >= 1:
        logger.info(
            f"📚 Large-book welcome strategy: {total_pages} pages, {word_count} words, "
            f"~{estimated_tokens} tokens"
        )
        pages = _extract_pages(all_text)
        section_ranges = _build_book_sections(
            pages=pages,
            chapters=chapters,
            total_pages=total_pages,
            estimated_tokens=estimated_tokens,
        )
        groups = _pack_book_sections(section_ranges, total_pages, estimated_tokens)

        compacted: list[tuple[int, str]] = []
        with ThreadPoolExecutor(max_workers=min(len(groups), _BOOK_COMPACTION_MAX_GROUPS)) as pool:
            futures = {}
            for index, group in enumerate(groups):
                group_text = _build_group_text(pages, group)
                if not group_text.strip():
                    continue
                futures[pool.submit(
                    _generate_compacted_book_group,
                    group_text,
                    index,
                    len(groups),
                    file_list,
                    language,
                    metadata_section,
                )] = index

            for future in futures:
                index = futures[future]
                try:
                    compacted.append((index, future.result()))
                except Exception as e:
                    logger.warning(f"⚠️ Book compact group {index + 1} failed: {e}")

        compacted.sort(key=lambda item: item[0])
        compacted_messages = [message for _, message in compacted if message.strip()]
        if compacted_messages:
            synthesis_msg, synthesis_qs = _synthesize_welcome_messages(
                compacted_messages,
                file_list,
                language,
                metadata_section,
                raw_beginning=all_text[:_SYNTHESIS_RAW_TEXT_CHARS],
                raw_ending=all_text[-_RAW_ENDING_CHARS:] if len(all_text) > _RAW_ENDING_CHARS else "",
            )
            return DescribeResult(welcome_message=synthesis_msg, suggested_questions=synthesis_qs)

        logger.warning("⚠️ Book compaction produced no summaries, falling back to split/truncated strategy")

    # ── Strategy 3: Split+Synthesize for very large documents ────────
    # For documents > _SPLIT_THRESHOLD chars (~600K), split the full text
    # into N parts, generate a detailed condensed summary for each (sequentially
    # to respect TPM limits), then synthesize all summaries + raw beginning
    # into one final welcome message.
    if total_chars > _SPLIT_THRESHOLD:
        logger.info(
            f"📝 Very large document ({total_chars} chars) → using split+synthesize strategy"
        )
        parts = _split_text_into_parts(all_text, _SPLIT_PART_MAX_CHARS)
        logger.info(f"📝 Split into {len(parts)} parts ({[len(p) for p in parts[:5]]}...)")

        # Generate detailed condensed summaries sequentially to stay under TPM
        partial_messages: list[tuple[int, str]] = []
        for i, part in enumerate(parts):
            try:
                msg = _generate_partial_welcome(
                    part,
                    i,
                    len(parts),
                    file_list,
                    language,
                    metadata_section if i == 0 else "",
                )
                partial_messages.append((i, msg))
            except Exception as e:
                logger.warning(f"⚠️ Detailed summary {i + 1} failed: {e}")

            # Delay between calls to spread TPM usage
            if i < len(parts) - 1:
                time.sleep(_SPLIT_INTER_CALL_DELAY)

        # Sort by part index to maintain order
        partial_messages.sort(key=lambda x: x[0])
        messages = [msg for _, msg in partial_messages]

        if not messages:
            return DescribeResult(
                welcome_message=_fallback_from_metadata(extracted, images, file_metadata, language),
                suggested_questions=[],
            )

        if len(messages) == 1:
            return DescribeResult(welcome_message=messages[0], suggested_questions=[])

        # Extract raw beginning text for the synthesis prompt.
        # This gives the synthesis LLM direct access to the author's voice
        # and opening content alongside the condensed summaries.
        raw_beginning = all_text[:_SYNTHESIS_RAW_TEXT_CHARS]

        # Synthesize all detailed summaries + raw beginning into one message
        synthesis_msg, synthesis_qs = _synthesize_welcome_messages(
            messages, file_list, language, metadata_section, raw_beginning=raw_beginning
        )
        return DescribeResult(welcome_message=synthesis_msg, suggested_questions=synthesis_qs)

    whole_book_mode = bool(all_text and estimated_tokens <= _WHOLE_BOOK_MAX_ESTIMATED_TOKENS)
    is_large = total_chars > _DESCRIBE_MAX_CONTENT_CHARS and page_summaries and not whole_book_mode

    # ── Build image snippets (always included, capped) ───────────────
    image_snippets: list[str] = []
    for img in images:
        desc = img.get("description", "")
        name = clean_file_name(img.get("file_name", "image"))
        page = img.get("page", "?")
        if desc:
            image_snippets.append(f"[Image from {name}, page {page}]\n{desc[:500]}")
    image_block = "\n\n---\n\n".join(image_snippets)

    if whole_book_mode:
        combined_parts = [all_text]
        if image_block:
            combined_parts.append(image_block)
        combined = "\n\n---\n\n".join(part for part in combined_parts if part.strip())
    elif is_large:
        # ── Large-document strategy ──────────────────────────────────
        # For very large documents (>200K chars), use 2-pass summarization:
        # 1. Raw text from the start of the document (50% budget)
        # 2. Summarize remaining content in 2 passes (20% budget)
        # 3. Per-page summaries for breadth (30% budget)
        image_chars = len(image_block)
        remaining = _DESCRIBE_MAX_CONTENT_CHARS - image_chars

        is_very_large = total_chars > _TWO_PASS_THRESHOLD

        if is_very_large:
            text_budget = int(remaining * _TEXT_BUDGET_RATIO)
            summary_pass_budget = int(remaining * _SUMMARY_PASS_BUDGET_RATIO)
            summary_budget = remaining - text_budget - summary_pass_budget
        else:
            text_budget = int(remaining * 0.7)
            summary_pass_budget = 0
            summary_budget = remaining - text_budget

        # Raw text from each document start (distribute budget evenly)
        per_doc = max(text_budget // max(len(extracted), 1), 500)
        text_snippets: list[str] = []
        for doc in extracted:
            name = clean_file_name(doc.get("file_name", "unknown"))
            text = (doc.get("text") or "")[:per_doc]
            if text.strip():
                text_snippets.append(f"[File: {name}]\n{text}")

        # Page summaries block
        summary_text = _build_page_summary_block(page_summaries)[:summary_budget]

        # 2-pass summarization for very large documents
        two_pass_summary = ""
        if is_very_large and summary_pass_budget > 0:
            # Collect remaining text (after the raw text budget) from all docs
            remaining_texts: list[str] = []
            for doc in extracted:
                full_text = doc.get("text") or ""
                if len(full_text) > per_doc:
                    remaining_texts.append(full_text[per_doc:])

            if remaining_texts:
                all_remaining = "\n\n---\n\n".join(remaining_texts)
                midpoint = len(all_remaining) // 2

                # Cap each half to avoid sending too much to the summarizer
                max_half = 80_000
                first_half = all_remaining[:midpoint][-max_half:]
                second_half = all_remaining[midpoint:][:max_half]

                # Summarize each half
                summary_1 = _summarize_text_chunk(
                    first_half, "first half (middle pages)", language
                )
                summary_2 = _summarize_text_chunk(
                    second_half, "second half (final pages)", language
                )

                two_pass_summary = f"[Condensed summary of middle pages]\n{summary_1}\n\n[Condensed summary of final pages]\n{summary_2}"
                two_pass_summary = two_pass_summary[:summary_pass_budget]
                logger.info(f"📝 2-pass summaries combined: {len(two_pass_summary)} chars")

        parts: list[str] = []
        if text_snippets:
            parts.append("\n\n---\n\n".join(text_snippets))
        if two_pass_summary:
            parts.append(
                f"[Dense summaries of document content beyond the raw text above — "
                f"generated via 2-pass summarization of the remaining {total_chars - text_budget} chars]\n{two_pass_summary}"
            )
        if summary_text:
            parts.append(
                f"[Short summaries of all pages — the full text above was truncated "
                f"because the document is very large ({total_chars} chars)]\n{summary_text}"
            )
        if image_block:
            parts.append(image_block)

        combined = "\n\n---\n\n".join(parts)
        if not combined.strip():
            # If metadata is available, let the LLM generate a contextual message;
            # otherwise return the static fallback immediately.
            if not metadata_block:
                return DescribeResult(
                    welcome_message=_fallback_from_metadata(extracted, images, file_metadata, language),
                    suggested_questions=[],
                )
            combined = _NO_TEXT_PLACEHOLDER
        logger.info(
            f"📝 Large-doc describe: {total_chars} chars total → "
            f"{len(combined)} chars context (text {text_budget}, 2-pass {len(two_pass_summary)}, summaries {len(summary_text)})"
        )
    else:
        # ── Small-document strategy (original) ───────────────────────
        snippets: list[str] = []
        per_doc = max(_DESCRIBE_MAX_CONTENT_CHARS // max(len(extracted), 1), 3000)
        for doc in extracted:
            name = clean_file_name(doc.get("file_name", "unknown"))
            text = (doc.get("text") or "")[:per_doc]
            if text.strip():
                snippets.append(f"[File: {name}]\n{text}")
        snippets.extend(image_snippets)

        if not snippets:
            # If metadata is available, let the LLM generate a contextual message;
            # otherwise return the static fallback immediately.
            if not metadata_block:
                return DescribeResult(
                    welcome_message=_fallback_from_metadata(extracted, images, file_metadata, language),
                    suggested_questions=[],
                )
            combined = _NO_TEXT_PLACEHOLDER
        else:
            combined = "\n\n---\n\n".join(snippets)[:_DESCRIBE_MAX_CONTENT_CHARS]

    # For the no-text case, enrich metadata_section with file size and date hints
    # so the LLM has the best chance of identifying the document.
    effective_metadata_section = metadata_section
    if combined == _NO_TEXT_PLACEHOLDER and _identification_section:
        effective_metadata_section = metadata_section + _identification_section

    if language == "pl":
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", WELCOME_SYSTEM_PL),
                ("human", "Przesłane pliki: {file_list}\n\nTreść:\n{content}{metadata_section}"),
            ]
        )
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", WELCOME_SYSTEM_EN),
                ("human", "Uploaded files: {file_list}\n\nContent:\n{content}{metadata_section}"),
            ]
        )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()

    # Build an OCR-in-progress note to append to the human message when the
    # welcome is generated from a partial OCR pass (e.g. Mathnawi Rumi scan).
    ocr_context_note = ""
    if ocr_in_progress or (ocr_pages_done is not None and total_pages_hint and ocr_pages_done < total_pages_hint):
        pages_done_str = str(ocr_pages_done) if ocr_pages_done is not None else "some"
        pages_total_str = str(total_pages_hint) if total_pages_hint else "many"
        ocr_context_note = (
            f"\n\n=====\n[SYSTEM NOTE — OCR IN PROGRESS]\n"
            f"OCR has been run on {pages_done_str} of {pages_total_str} pages so far. "
            f"The text above is what was extracted. "
            f"If the text is sparse, incomplete, or only partial, still produce the best welcome message you can "
            f"based on what is available — and explicitly tell the user in your welcome message that:\n"
            f"1. The material contains photos/scans of handwritten or printed text (e.g. Arabic calligraphy, classical manuscripts).\n"
            f"2. OCR is still running on all {pages_total_str} pages in the background.\n"
            f"3. The welcome message will be extended as more text becomes available.\n"
            f"4. If almost no text was found yet, tell the user this honestly and describe the nature of the document from metadata/filename.\n"
            f"Use a warm, reassuring tone. Do NOT pretend you have full text when you don't.\n====="
        )

    # Final safety: cap the full content to the per-call token budget.  This
    # protects the whole-book path (Strategy 1) and the large/small paths from
    # ever exceeding the model's 300K-token per-request limit — essential for
    # Arabic/CJK scripts where char-based estimates under-count severely.
    combined = _truncate_text_to_token_budget(combined, _MAX_CONTENT_TOKENS)

    raw = _invoke_with_retry(
        chain,
        {"file_list": file_list, "content": combined, "metadata_section": effective_metadata_section + ocr_context_note},
        label="describe",
    )
    welcome_message, suggested_questions = _parse_describe_response(raw)

    # Apply contextual post-processing (EXIF, person recognition, image prompts)
    if suggested_questions:
        from .suggested_questions import _append_contextual_prompts

        suggested_questions = _append_contextual_prompts(
            suggested_questions,
            file_names,
            file_types,
            language,
            welcome_message=welcome_message,
            description="",
        )
    # Re-embed the (possibly enriched) action list back into the welcome
    # content so the frontend sees a single source of truth. The list is
    # still returned separately for back-compat with answering.ts's
    # "don't repeat these" heuristic.
    welcome_message = _embed_actions_in_welcome(welcome_message, suggested_questions)

    # Inject social media action for standalone image uploads (sets |ref: so
    # the frontend routes it through the image-gen pipeline with the photo).
    welcome_message = _inject_social_media_action(welcome_message, images)

    return DescribeResult(
        welcome_message=welcome_message,
        suggested_questions=suggested_questions,
    )
