from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .chapters import ChapterInfo, chapters_from_serializable
from .config import get_settings
from .llm_instrument import traced_llm_call
from .prompts.emoji_and_dash import EMOJI_AND_DASH_RULES
from .prompts.labels_actions import LABELS_ACTIONS_RULES
from .prompts.quiz import QUIZ_PROMPT
from .prompts.response_formats import RESPONSE_FORMATS_RULES
from .prompts.voice_tone import VOICE_TONE_RULES
from .vector_store import query_chunks

logger = logging.getLogger(__name__)

# Max chars of full matched pages to include in answer prompts.
_MATCHED_PAGES_MAX_CHARS = 40_000

# Hard cap on total prompt tokens sent to the LLM.
# gpt-5.4 has a 1M context window; we use 400K to stay well within budget
# while allowing much larger documents to be processed in a single call.
_MAX_PROMPT_TOKENS = 400_000

# Baseline sampling temperature for the answering LLM (OpenAI).
# The system prompt instructs the model to self-regulate its effective
# "creative temperature" inside the band [_MIN_LLM_TEMPERATURE, _MAX_LLM_TEMPERATURE]
# depending on whether the question is factual or creative.
_DEFAULT_LLM_TEMPERATURE = 0.4
_MIN_LLM_TEMPERATURE = 0.2
_MAX_LLM_TEMPERATURE = 0.6

# Module-level cache for LLM instance
_llm_instance = None
_llm_provider_key = None

# Multiple seed values to introduce variation for repeated prompts (OpenAI only)
_SEED_OPTIONS = [365, 742, 158, 2901, 4417, 5830, 6193, 7764, 8529, 9046]

# Patterns that trigger quiz mode
_QUIZ_PATTERNS = re.compile(
    r"\b(quiz|kwiz|test|egzamin)\b",
    re.IGNORECASE,
)

_ANSWER_SYSTEM_TEMPLATE = """You answer questions about the user's uploaded files (books in PDF, images, text, etc.). The context sections below are your PRIMARY source of truth.  You can "fill the information holes" with "common knownledge" and admit it, but don't hallucinate, keep close to source material

== QUESTION ==
"{question}"

Read all context sections carefully before answering.

Context sections provided (in the human message):
1. Matching Sources — top embedding matches with similarity scores
2. Welcome Page Description — short summary of each uploaded file
3. Full Pages of Matched Sources — complete page text where matches were found
4. Chapter Context — full text of the most relevant chapter (if available)
5. EXIF Metadata — image file metadata (if available)
6. Conversation Context — conversation name and ID
7. Chat History — all previous exchanges with timestamps
8. Previously Suggested Questions — all action buttons already shown
9. Start Answering

--

<<VOICE_TONE>>
<<RESPONSE_FORMATS>>
<<ACTIONS_RULES>>
<<EMOJI_AND_DASH>>
"""

_ANSWER_SYSTEM = (
    _ANSWER_SYSTEM_TEMPLATE
    .replace("<<VOICE_TONE>>", VOICE_TONE_RULES)
    .replace("<<RESPONSE_FORMATS>>", RESPONSE_FORMATS_RULES)
    .replace("<<ACTIONS_RULES>>", LABELS_ACTIONS_RULES)
    .replace("<<EMOJI_AND_DASH>>", EMOJI_AND_DASH_RULES)
)

ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            _ANSWER_SYSTEM,
        ),
        (
            "human",
            """== SECTION 1: Matching Sources ==
{context}

--

== SECTION 3: Welcome Page Description ==
Below is a short summary generated during file upload/indexing for each source file:
{welcome_messages}

--

== SECTION 4: Full Pages of Matched Sources ==
Below is the full text of pages where matching sources were found. Each block is labeled [Full Page N of filename] so you know which uploaded file the page belongs to. Use this for additional detail beyond the matching chunks.
{matched_pages}

--

== SECTION 4a: Chapter Context (if available) ==
Below is the full text of the chapter that the most relevant matching sources belong to. This provides broader narrative and structural context beyond individual pages. If this section is empty, the document has no detectable chapter structure.
{chapter_context}

--

== SECTION 5: EXIF Metadata ==
{exif_metadata}

--

== SECTION 5a: Conversation Context ==
Conversation name: {conversation_name}
Conversation ID: {conversation_id}
This is a unique conversation where the user uploaded files and is asking questions about them. Use the conversation name (if set) to understand the broader topic or purpose of this session.

--

== SECTION 5b: Full Chat History (All Previous Messages) ==
Below is the COMPLETE conversation history between the user and you (the assistant) in this session, in chronological order. Each message is labeled with its role (User Question / Assistant Answer) and numbered sequentially. Timestamps are included when available.

Use this full history to:
- Understand the full arc of the conversation and what topics have been covered
- Resolve follow-up references ("it", "that", "the previous one", "more details")
- Avoid repeating information already given in earlier answers
- Build on insights and analysis from previous exchanges
- Maintain consistent terminology and style throughout the conversation

{chat_history}

--

== SECTION 5c: Previously Suggested Prompts (with conversation flow) ==
Below is a log of ALL suggested prompts already shown to the user, grouped by the Q&A exchange they appeared after. Prompts use the [action:Label] syntax — the same format you must output.

Rules:
- NEVER repeat or closely rephrase ANY prompt listed here.
- Study which angles were already explored and generate FRESH directions that go deeper.
- Each new [action:] must open a genuinely unexplored angle — not a synonym or restatement.

{previous_suggested_questions}

--

== SECTION 6: Start Answering ==
You have all the context above. Now answer the following question thoroughly with inline [source:N] citations:
"{question}"
""",
        ),
    ]
)


def build_context(rows: list[dict]) -> str:
    if not rows:
        return "(no matching sources found)"
    parts = []
    for i, row in enumerate(rows, 1):
        # Convert L2 distance to approximate cosine similarity: sim ≈ 1 - dist/2
        distance = row.get("distance", 0)
        similarity = max(0.0, 1.0 - distance / 2.0)
        label = f"[Source {i}] File: {row['file_name']}"
        if row.get("page") is not None:
            label += f" (Page {row['page']})"
        if row.get("chapter_number") is not None:
            ch_label = f"Chapter {row['chapter_number']}"
            if row.get("chapter_name"):
                ch_label += f": {row['chapter_name']}"
            label += f" ({ch_label})"
        if row.get("section"):
            label += f" | Section: {row['section']}"
        label += f" | Similarity: {similarity:.2f}"
        parts.append(f'{label}\n"{row["text"]}"')
    return "\n\n--\n\n".join(parts)


def get_llm() -> Any:
    """Get OpenAI LLM instance (cached).

    Raises ValueError if OPENAI_API_KEY is missing.
    """
    global _llm_instance, _llm_provider_key
    settings = get_settings()

    cache_key = f"openai:{settings.openai_chat_model}:{settings.openai_reasoning_effort}"
    if _llm_instance is not None and _llm_provider_key == cache_key:
        seed = random.choice(_SEED_OPTIONS)
        return _llm_instance.bind(seed=seed)

    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable")

    logger.info(
        f"🤖 Using OpenAI model: {settings.openai_chat_model} (reasoning_effort={settings.openai_reasoning_effort})"
    )
    # Explicit timeout prevents a stalled API call from blocking indexing
    # indefinitely (default SDK timeout is 600 s = 10 min).
    _llm_instance = ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=_DEFAULT_LLM_TEMPERATURE,
        reasoning_effort=settings.openai_reasoning_effort,
        timeout=180.0,
    )
    _llm_provider_key = cache_key

    # Bind a random seed to vary responses for repeated prompts
    seed = random.choice(_SEED_OPTIONS)
    logger.info(f"🎲 Selected random seed: {seed}")
    return _llm_instance.bind(seed=seed)


def _build_citations(rows: list[dict]) -> list[dict]:
    citations = []
    for row in rows:
        citation = {
            "fileName": row["file_name"],
            "chunkId": row["chunk_id"],
            "text": row["text"],
            "section": row.get("section"),
            "page": row.get("page"),
        }
        if row.get("image_name"):
            citation["imageName"] = row["image_name"]
        citations.append(citation)
    return citations


def _strip_orphan_source_tags(answer: str, citation_count: int) -> str:
    """Remove [source:N] tags that reference non-existent citations."""

    def _replace(m: re.Match) -> str:
        nums = m.group(1)
        valid = [n.strip() for n in nums.split(",") if int(n.strip()) <= citation_count]
        if not valid:
            return ""
        return "[source:" + ",".join(valid) + "]"

    return re.sub(r"\[source:\s*(\d+(?:,\s*\d+)*)\]", _replace, answer)


# Patterns that trigger EXIF metadata display
_EXIF_PATTERNS = re.compile(
    r"(show exif|exif metadata|pokaż metadane exif|pokaż exif|metadane exif)",
    re.IGNORECASE,
)


def _is_exif_request(question: str) -> bool:
    return bool(_EXIF_PATTERNS.search(question))


def _handle_exif(
    file_metadata: dict[str, dict] | None,
) -> dict | None:
    """Handle 'show EXIF metadata' by formatting stored metadata.

    Returns {"answer": ..., "citations": []} or None if no metadata available.
    """
    if not file_metadata:
        return None

    parts = []
    for filename, meta in file_metadata.items():
        if not meta or meta.get("file_type") not in ("image",):
            continue
        parts.append(f"**{filename}**\n")
        # Build camera string from make/model
        camera_parts = [meta.get("camera_make", ""), meta.get("camera_model", "")]
        camera = " ".join(p for p in camera_parts if p).strip() or None
        # File size in MB
        raw_size = meta.get("file_size_bytes")
        file_size_mb = f"{raw_size / (1024 * 1024):.2f} MB" if raw_size else None
        # Dimensions with labels
        dims = None
        if meta.get("image_width") and meta.get("image_height"):
            dims = f"{meta.get('image_width')} (width) x {meta.get('image_height')} (height)"
        # Core EXIF fields
        fields = [
            ("Camera", camera),
            ("Date taken", meta.get("date_taken")),
            ("Dimensions", dims),
            ("File size", file_size_mb),
            ("Format", meta.get("image_format")),
            ("Color mode", meta.get("image_mode")),
            ("ISO", meta.get("iso")),
            ("Exposure", meta.get("exposure_time")),
            ("F-number", meta.get("f_number")),
            ("Focal length", meta.get("focal_length")),
            ("Lens", meta.get("lens_model")),
            ("Software", meta.get("software")),
            ("Copyright", meta.get("copyright")),
            ("Artist", meta.get("artist")),
            ("Description", meta.get("description")),
            (
                "GPS",
                f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}"
                if meta.get("gps_latitude")
                else None,
            ),
        ]
        has_exif = False
        for label, value in fields:
            if value:
                has_exif = True
                parts.append(f"- **{label}** {value}")
        if not has_exif:
            parts.append("- No EXIF metadata found in this image.")

    if not parts:
        return None

    return {
        "answer": "\n".join(parts),
        "citations": [],
    }


# Patterns that trigger recognition mode (Vision API)
_RECOGNIZE_PATTERNS = re.compile(
    r"\b(recognize|rozpoznaj|identify|identyfikuj)\b.*\b(name|person|osob|face|twarz|imi)",
    re.IGNORECASE,
)

# Simpler pattern: the suggested prompt format itself
_RECOGNIZE_PROMPT_PATTERN = re.compile(
    r"(recognize person name|rozpoznaj osob)",
    re.IGNORECASE,
)

# Natural question format: "Who is the woman/man/person on the photo?"
_RECOGNIZE_QUESTION_PATTERN = re.compile(
    r"(who is the (woman|man|person|girl|boy|lady|guy)|"
    r"kto jest (kobiet|mężczyzn|osob|dziewczyn|chłopak|pani))",
    re.IGNORECASE,
)


def _is_recognize_request(question: str) -> bool:
    m1 = _RECOGNIZE_PATTERNS.search(question)
    m2 = _RECOGNIZE_PROMPT_PATTERN.search(question)
    m3 = _RECOGNIZE_QUESTION_PATTERN.search(question)
    is_match = bool(m1 or m2 or m3)
    logger.info(
        f"🔍 _is_recognize_request('{question[:80]}'): {is_match} (pattern1={bool(m1)}, pattern2={bool(m2)}, pattern3={bool(m3)})"
    )
    return is_match


def _handle_recognize(
    question: str,
    image_file_paths: list[str] | None,
    file_metadata: dict[str, dict] | None,
    welcome_messages: list[str] | None,
) -> dict | None:
    """Handle 'recognize person name' by calling Vision API + LLM identification.

    Returns {"answer": ..., "citations": []} or None if not applicable.
    """
    if not image_file_paths:
        logger.info("🔍 _handle_recognize: no image_file_paths provided, returning None")
        return None

    from .metadata import enrich_metadata_web

    welcome_str = _format_welcome_messages(welcome_messages)

    logger.info(
        f"🔍 Recognition mode: calling Vision API for {len(image_file_paths)} image(s)\n"
        f"   image_file_paths={image_file_paths}\n"
        f"   file_metadata keys={list(file_metadata.keys()) if file_metadata else None}\n"
        f"   welcome_str length={len(welcome_str)} chars"
    )
    enrichment = enrich_metadata_web(
        file_paths=image_file_paths,
        exif_metadata=file_metadata,
        welcome_message=welcome_str,
    )

    if not enrichment:
        # Vision API returned nothing — fall back to normal RAG
        logger.info(
            "🔍 Vision API returned no results (empty enrichment dict), falling back to normal RAG"
        )
        return None

    logger.info(
        f"🔍 Enrichment result keys per file: { {k: list(v.keys()) for k, v in enrichment.items()} }"
    )

    # Build a human-readable answer from the identification results
    parts = []
    for _filename, data in enrichment.items():
        identified_name = data.get("identified_name")
        identification = data.get("identification", {})
        confidence = identification.get("confidence", "unknown")
        category = identification.get("category", "unknown")
        reasoning = identification.get("reasoning", "")
        web_detection = data.get("web_detection", {})
        labels = web_detection.get("best_guess_labels", [])

        if identified_name:
            search_url = "https://www.google.com/search?q=" + identified_name.replace(" ", "+")
            # search_url = "https://babepedia.com/babe/" + identified_name.replace(" ", "_")
            parts.append(
                f"**[{identified_name}]({search_url})** (confidence: {confidence}, category: {category})"
            )
            if reasoning:
                parts.append(f"- {reasoning}")
        elif labels:
            parts.append(
                f"Could not identify a specific name, but the image matches: {', '.join(labels)}"
            )
        else:
            parts.append("Could not identify the person from the available sources.")

        # Add web entities as supporting evidence
        entities = web_detection.get("web_entities", [])
        if entities:
            top = [e["description"] for e in entities[:5] if e.get("description")]
            if top:
                parts.append(f"- Related web entities: {', '.join(top)}")

    return {
        "answer": "\n".join(parts),
        "citations": [],
    }


def _is_quiz_request(question: str) -> bool:
    return bool(_QUIZ_PATTERNS.search(question))


def _format_welcome_messages(welcome_messages: list[str] | None) -> str:
    """Format all welcome/upload messages into a numbered list for the prompt."""
    if not welcome_messages:
        return "(no file descriptions available)"
    if len(welcome_messages) == 1:
        return welcome_messages[0]
    parts = []
    for i, msg in enumerate(welcome_messages, 1):
        parts.append(f"[Upload {i}]\n{msg}")
    return "\n\n".join(parts)


def _format_previous_suggested_questions(
    questions: list[str] | None,
    chat_history: list[dict] | None = None,
) -> str:
    """Format previously shown suggested questions grouped with the Q&A exchanges they followed.

    Output shows the conversation flow so the model sees which prompts appeared
    after each exchange and can avoid repeating them.
    """
    if not questions:
        return "(none - this is the first interaction)"

    if not chat_history:
        return "\n".join(f"- {q}" for q in questions)

    import re

    action_re = re.compile(r"\[action:\s*([^\]]+)\]")

    # Extract [action:] labels per assistant message, paired with the preceding user question
    exchanges: list[dict] = []
    current_user_q: str | None = None
    for msg in chat_history:
        if msg.get("role") == "user":
            current_user_q = msg.get("content", "")
        elif msg.get("role") == "assistant" and current_user_q is not None:
            actions = [m.group(1).strip() for m in action_re.finditer(msg.get("content", ""))]
            if actions:
                exchanges.append({"question": current_user_q, "actions": actions})
            current_user_q = None

    all_exchange_actions: set[str] = set()
    for ex in exchanges:
        all_exchange_actions.update(ex["actions"])

    # Prompts not found as [action:] in any assistant message = initial upload prompts
    initial_prompts = [q for q in questions if q not in all_exchange_actions]

    parts: list[str] = []
    if initial_prompts:
        parts.append("After file upload (initial suggested prompts):")
        for q in initial_prompts:
            parts.append(f"  - {q}")

    for ex in exchanges:
        q_preview = ex["question"][:120]
        parts.append(f'\nAfter user asked: "{q_preview}"')
        parts.append("Suggested prompts shown (using [action:] syntax):")
        for a in ex["actions"]:
            parts.append(f"  - [action:{a}]")

    return "\n".join(parts) if parts else "(none - this is the first interaction)"


# Token budget for chat history section — keeps room for system prompt, sources,
# matched pages, chapter context, etc.  30k tokens ≈ ~120k chars, which leaves
# plenty of headroom in both 200k (Claude Haiku) and 1M (GPT-4.1) context windows.
_MAX_CHAT_HISTORY_TOKENS = 30_000

# Separator used between formatted messages in chat history
_HISTORY_SEP = "\n\n---\n\n"

# Lazy-loaded tiktoken encoder (cl100k_base works well for OpenAI models)
_tiktoken_enc = None


def _count_tokens(text: str) -> int:
    """Estimate token count using tiktoken cl100k_base encoding."""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        import tiktoken

        _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
    return len(_tiktoken_enc.encode(text, disallowed_special=()))


def _format_chat_history(chat_history: list[dict] | None) -> str:
    """Format the full conversation history into a structured string for the prompt.

    Each message is labeled with role (User Question / Assistant Answer) and
    timestamp when available, so the model can clearly distinguish exchanges.

    When total tokens exceed _MAX_CHAT_HISTORY_TOKENS, the oldest exchanges
    are dropped (keeping the most recent ones) to stay within budget.
    """
    if not chat_history:
        return "(no previous conversation)"
    parts = []
    exchange_num = 0
    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        if role == "user":
            exchange_num += 1
            label = f"[User Question #{exchange_num}]"
        else:
            label = f"[Assistant Answer #{exchange_num}]"

        if timestamp:
            label += f" ({timestamp})"

        # Truncate very long assistant answers to keep total context reasonable
        if role == "assistant" and len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"

        parts.append(f"{label}\n{content}")

    # Token-aware truncation: drop oldest exchanges when history exceeds budget.
    # We work backwards (most recent first) and keep exchanges that fit.
    total_tokens = _count_tokens(_HISTORY_SEP.join(parts))
    if total_tokens > _MAX_CHAT_HISTORY_TOKENS:
        kept: list[str] = []
        running_tokens = 0
        for part in reversed(parts):
            part_tokens = _count_tokens(part) + _count_tokens(_HISTORY_SEP)
            if running_tokens + part_tokens > _MAX_CHAT_HISTORY_TOKENS:
                break
            kept.append(part)
            running_tokens += part_tokens
        kept.reverse()
        dropped = len(parts) - len(kept)
        logger.warning(
            f"✂️ Chat history truncated: dropped {dropped} oldest messages "
            f"({total_tokens} tokens → ~{running_tokens} tokens, "
            f"budget={_MAX_CHAT_HISTORY_TOKENS})"
        )
        prefix = f"[... {dropped} earlier messages omitted to fit context window ...]\n\n"
        return prefix + _HISTORY_SEP.join(kept)

    return _HISTORY_SEP.join(parts)


def _load_raw_text_legacy(storage_dir: str | None) -> str:
    """Load raw PDF text from disk (used only for quiz prompt)."""
    if not storage_dir:
        return ""
    try:
        raw_path = Path(storage_dir) / "_raw_text.json"
        if not raw_path.exists():
            return ""
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        parts = []
        for fname, text in data.items():
            parts.append(f"[File: {fname}]\n{text}")
        combined = "\n\n---\n\n".join(parts)
        if len(combined) > 80_000:
            combined = combined[:80_000] + "\n\n[... truncated]"
        return combined
    except Exception:
        return ""


def _load_page_summaries_legacy(storage_dir: str | None) -> str:
    """Load per-page summaries from disk (used only for quiz prompt)."""
    if not storage_dir:
        return ""
    try:
        summaries_path = Path(storage_dir) / "_page_summaries.json"
        if not summaries_path.exists():
            return ""
        summaries = json.loads(summaries_path.read_text(encoding="utf-8"))
        lines = []
        for ps in summaries:
            page = ps.get("page", "?")
            fname = ps.get("file_name", "")
            summary = ps.get("summary", "").strip()
            if summary:
                prefix = f"[{fname} p.{page}]" if fname else f"[p.{page}]"
                lines.append(f"{prefix} {summary}")
        combined = "\n".join(lines)
        if len(combined) > 20_000:
            combined = combined[:20_000] + "\n[... truncated]"
        return combined
    except Exception:
        return ""


def _extract_matched_pages(storage_dir: str | None, rows: list[dict]) -> str:
    """Extract full page text only for pages referenced by matching chunks.

    Instead of sending the entire raw document, we extract only the unique
    pages that the top-k matching sources came from.  This dramatically
    reduces the context window while giving the model complete page text
    for the most relevant pages.
    """
    if not storage_dir or not rows:
        return "(no full page text available)"
    try:
        raw_path = Path(storage_dir) / "_raw_text.json"
        if not raw_path.exists():
            return "(no full page text available)"
        data: dict[str, str] = json.loads(raw_path.read_text(encoding="utf-8"))

        # Collect unique (file_name, page) pairs from matching rows
        needed: dict[str, set[int]] = {}  # file_name -> set of page numbers
        for row in rows:
            page = row.get("page")
            fname = row.get("file_name", "")
            if page is not None and page > 0 and fname:
                needed.setdefault(fname, set()).add(int(page))

        if not needed:
            return "(matched sources have no page numbers)"

        # Parse raw text per file using '# Page N' headers as delimiters
        _page_header_re = re.compile(r"^# Page (\d+)$", re.MULTILINE)
        parts: list[str] = []
        for fname, pages_needed in needed.items():
            raw = data.get(fname, "")
            if not raw:
                continue
            # Split the raw text into pages by finding all '# Page N' headers
            headers = list(_page_header_re.finditer(raw))
            if not headers:
                continue
            page_texts: dict[int, str] = {}
            for idx, match in enumerate(headers):
                page_num = int(match.group(1))
                start = match.start()
                end = headers[idx + 1].start() if idx + 1 < len(headers) else len(raw)
                page_texts[page_num] = raw[start:end].strip()

            # Extract only the needed pages, sorted ascending
            for page_num in sorted(pages_needed):
                text = page_texts.get(page_num)
                if text:
                    parts.append(f'[Full Page {page_num} of {fname}]\n"{text}"')

        if not parts:
            return "(could not extract full page text)"

        combined = "\n\n--\n\n".join(parts)
        if len(combined) > _MATCHED_PAGES_MAX_CHARS:
            combined = combined[:_MATCHED_PAGES_MAX_CHARS] + "\n\n[... truncated]"
        logger.info(f"📄 Extracted {len(parts)} matched pages: {len(combined)} chars")
        return combined
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract matched pages: {e}")
        return "(error extracting page text)"


# Max chars of chapter context to include in answer prompts.
_CHAPTER_CONTEXT_MAX_CHARS = 60_000


def _extract_chapter_context(storage_dir: str | None, rows: list[dict]) -> str:
    """Extract full chapter text for the most relevant matching chapter.

    Finds the chapter that appears most frequently in the top matching chunks,
    then returns all pages of that chapter in order. This gives the model
    broader narrative/structural context beyond individual matched pages.
    """
    if not storage_dir or not rows:
        return ""
    try:
        # Load chapter data
        chapters_path = Path(storage_dir) / "_chapters.json"
        if not chapters_path.exists():
            return ""
        chapters_data: dict[str, list[dict]] = json.loads(
            chapters_path.read_text(encoding="utf-8")
        )
        if not chapters_data:
            return ""

        # Load raw text for page extraction
        raw_path = Path(storage_dir) / "_raw_text.json"
        if not raw_path.exists():
            return ""
        raw_data: dict[str, str] = json.loads(raw_path.read_text(encoding="utf-8"))

        # Count chapter occurrences across matching chunks (weighted by rank)
        chapter_scores: dict[tuple[str, int], float] = {}  # (file_name, chapter_nr) -> score
        for rank, row in enumerate(rows):
            chapter_nr = row.get("chapter_number")
            fname = row.get("file_name", "")
            if chapter_nr is None or not fname:
                continue
            key = (fname, chapter_nr)
            # Higher-ranked matches (lower index) get more weight
            weight = 1.0 / (rank + 1)
            chapter_scores[key] = chapter_scores.get(key, 0.0) + weight

        if not chapter_scores:
            return ""

        # Pick the highest-scoring chapter
        best_key = max(chapter_scores, key=chapter_scores.get)
        best_fname, best_chapter_nr = best_key

        # Find chapter info
        file_chapters = chapters_data.get(best_fname, [])
        chapters = chapters_from_serializable(file_chapters)
        target_chapter: ChapterInfo | None = None
        for ch in chapters:
            if ch.number == best_chapter_nr:
                target_chapter = ch
                break

        if not target_chapter:
            return ""

        # Extract all pages of the chapter from raw text
        raw = raw_data.get(best_fname, "")
        if not raw:
            return ""

        _page_header_re = re.compile(r"^# Page (\d+)$", re.MULTILINE)
        headers = list(_page_header_re.finditer(raw))
        if not headers:
            return ""

        page_texts: dict[int, str] = {}
        for idx, match in enumerate(headers):
            page_num = int(match.group(1))
            start = match.start()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(raw)
            page_texts[page_num] = raw[start:end].strip()

        # Collect pages in the chapter range
        parts: list[str] = []
        for page_num in range(target_chapter.start_page, target_chapter.end_page + 1):
            text = page_texts.get(page_num)
            if text:
                parts.append(text)

        if not parts:
            return ""

        combined = "\n\n".join(parts)
        if len(combined) > _CHAPTER_CONTEXT_MAX_CHARS:
            combined = combined[:_CHAPTER_CONTEXT_MAX_CHARS] + "\n\n[... chapter truncated]"

        ch_display = target_chapter.title
        if target_chapter.chapter_name and target_chapter.chapter_name.lower() != target_chapter.title.lower():
            ch_display += f" — {target_chapter.chapter_name}"
        header = (
            f'[Full Chapter {target_chapter.number}: "{ch_display}" '
            f"of {best_fname}, pages {target_chapter.start_page}-{target_chapter.end_page}]"
        )
        result = f"{header}\n\n{combined}"
        logger.info(
            f"📖 Extracted chapter {target_chapter.number} ({target_chapter.title}) "
            f"from {best_fname}: pages {target_chapter.start_page}-{target_chapter.end_page}, "
            f"{len(result)} chars"
        )
        return result
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract chapter context: {e}")
        return ""


def _trim_prompt_to_budget(
    prompt_vars: dict,
    prompt: ChatPromptTemplate,
    max_tokens: int = _MAX_PROMPT_TOKENS,
) -> dict:
    """Ensure the rendered prompt stays within the per-request token budget.

    Sections are trimmed in order of decreasing size impact:
      chapter_context → matched_pages → context (source chunks)
    Each trimming pass cuts the offending section to 60 % of its current
    length until the budget is met or nothing more can be cut.
    """
    _TRIM_SENTINELS = frozenset({
        "(no chapter structure detected)",
        "(no full page text available)",
        "(no matching sources found)",
        "(matched sources have no page numbers)",
        "(could not extract full page text)",
        "(error extracting page text)",
    })

    vars_copy = dict(prompt_vars)
    for attempt in range(12):
        rendered_messages = prompt.format_messages(**vars_copy)
        full_text = "\n".join(m.content for m in rendered_messages)
        total_tokens = _count_tokens(full_text)

        if total_tokens <= max_tokens:
            if attempt > 0:
                logger.warning(
                    f"✂️ Prompt trimmed after {attempt} reduction(s): "
                    f"{total_tokens:,} tokens (budget={max_tokens:,})"
                )
            return vars_copy

        logger.warning(
            f"⚠️ Prompt too large: {total_tokens:,} tokens "
            f"(budget={max_tokens:,}), trimming (attempt {attempt + 1})"
        )

        trimmed = False
        for key in ("chapter_context", "matched_pages", "context"):
            val = vars_copy.get(key, "")
            if not val or val in _TRIM_SENTINELS:
                continue
            new_len = max(500, int(len(val) * 0.6))
            if new_len < len(val):
                vars_copy[key] = val[:new_len] + "\n\n[... trimmed to fit token budget]"
                trimmed = True
                break

        if not trimmed:
            logger.error(
                f"🚨 Cannot reduce prompt further — sending {total_tokens:,} tokens "
                f"(over budget by {total_tokens - max_tokens:,})"
            )
            break

    return vars_copy


def _format_exif_for_prompt(file_metadata: dict[str, dict] | None) -> str:
    """Format EXIF metadata for all files into a prompt section."""
    if not file_metadata:
        return "(no file metadata available)"
    parts = []
    for filename, meta in file_metadata.items():
        if not meta:
            continue
        file_type = meta.get("file_type", "")
        fields: list[tuple[str, Any]] = []
        if file_type == "image":
            camera_parts = [meta.get("camera_make", ""), meta.get("camera_model", "")]
            camera = " ".join(p for p in camera_parts if p).strip() or None
            fields = [
                ("Camera", camera),
                ("Date taken", meta.get("date_taken")),
                (
                    "Dimensions",
                    f"{meta.get('image_width')}x{meta.get('image_height')}"
                    if meta.get("image_width")
                    else None,
                ),
                ("ISO", meta.get("iso")),
                ("Exposure", meta.get("exposure_time")),
                ("F-number", meta.get("f_number")),
                ("Focal length", meta.get("focal_length")),
                ("Lens", meta.get("lens_model")),
                (
                    "GPS",
                    f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}"
                    if meta.get("gps_latitude")
                    else None,
                ),
                ("Software", meta.get("software")),
                ("Copyright", meta.get("copyright")),
                ("Artist", meta.get("artist")),
            ]
        else:
            # PDF or other file metadata
            fields = [
                ("Title", meta.get("title")),
                ("Author", meta.get("author")),
                ("Subject", meta.get("subject")),
                ("Created", meta.get("creation_date")),
                ("Pages", meta.get("page_count")),
            ]
        line_parts = [f"{label}: {value}" for label, value in fields if value]
        if line_parts:
            parts.append(f"[{filename}] " + " | ".join(line_parts))
    return "\n".join(parts) if parts else "(no file metadata available)"


def answer_with_citations(
    collection_name: str,
    conversation_id: str,
    question: str,
    top_k: int = 10,
    chat_history: list[dict] | None = None,
    welcome_messages: list[str] | None = None,
    image_file_paths: list[str] | None = None,
    file_metadata: dict[str, dict] | None = None,
    storage_dir: str | None = None,
    previous_suggested_questions: list[str] | None = None,
    conversation_name: str | None = None,
) -> dict:
    import sentry_sdk
    from sentry_sdk import logger as sentry_logger

    logger.info(f"❓ Answering question: {question[:100]}...")

    with sentry_sdk.start_span(op="rag.answer", name=f"answer: {question[:60]}") as rag_span:
        rag_span.set_data("conversation_id", conversation_id)
        rag_span.set_data("question", question[:200])

        # Check for "show EXIF metadata" intent — return stored metadata directly
        if _is_exif_request(question) and file_metadata:
            result = _handle_exif(file_metadata)
            if result:
                return result

        # Check for "recognize person name" intent - triggers Vision API
        logger.info(
            f"🔍 Checking recognize intent: image_file_paths={'present, count=' + str(len(image_file_paths)) if image_file_paths else 'None'}"
        )
        if _is_recognize_request(question) and image_file_paths:
            result = _handle_recognize(question, image_file_paths, file_metadata, welcome_messages)
            if result:
                logger.info(
                    f"🔍 Recognition returned answer ({len(result.get('answer', ''))} chars)"
                )
                return result
            logger.info("🔍 _handle_recognize returned None, continuing to normal RAG")

        # Determine max_distance based on question word count
        word_count = len([w for w in question.strip().split() if w])
        max_distance = 1.1  # default for 3+ words
        if word_count == 1:
            max_distance = 1.5
        elif word_count == 2:
            max_distance = 1.3
        logger.info(f"🔎 Using max_distance={max_distance} for question word count={word_count}")
        rows = query_chunks(collection_name, conversation_id, question, top_k, max_distance)
        logger.info(f"📚 Retrieved {len(rows)} context chunks")
        context = build_context(rows)

        # Extract full page text only for pages referenced by matching chunks
        matched_pages = _extract_matched_pages(storage_dir, rows)

        # Extract full chapter context for the most relevant chapter
        chapter_context = _extract_chapter_context(storage_dir, rows)

        # Format EXIF / file metadata for the prompt
        exif_str = _format_exif_for_prompt(file_metadata)

        llm = get_llm()

        # Choose prompt based on whether this is a quiz request
        is_quiz = _is_quiz_request(question)
        if is_quiz:
            logger.info("🧩 Quiz mode detected, using QUIZ_PROMPT")
            # Quiz still uses the old raw_text + page_summaries variables
            raw_text = _load_raw_text_legacy(storage_dir)
            page_summaries = _load_page_summaries_legacy(storage_dir)

        history_str = _format_chat_history(chat_history)
        welcome_str = _format_welcome_messages(welcome_messages)
        prev_questions_str = _format_previous_suggested_questions(
            previous_suggested_questions, chat_history
        )

        prompt = QUIZ_PROMPT if is_quiz else ANSWER_PROMPT
        chain = prompt | llm

        # Build the template variables for this invocation
        if is_quiz:
            prompt_vars = {
                "question": question,
                "context": context,
                "chat_history": history_str,
                "welcome_messages": welcome_str,
                "raw_text": raw_text or "(no raw text available)",
                "page_summaries": page_summaries or "(no page summaries available)",
            }
        else:
            conv_name = conversation_name or "(unnamed conversation)"
            prompt_vars = {
                "question": question,
                "context": context,
                "chat_history": history_str,
                "welcome_messages": welcome_str,
                "matched_pages": matched_pages,
                "chapter_context": chapter_context or "(no chapter structure detected)",
                "exif_metadata": exif_str,
                "previous_suggested_questions": prev_questions_str,
                "conversation_name": conv_name,
                "conversation_id": conversation_id,
            }

        # Trim context sections if total prompt would exceed the per-request token limit
        prompt_vars = _trim_prompt_to_budget(prompt_vars, prompt)

        # Render the full prompt string and log it for debugging
        rendered_messages = prompt.format_messages(**prompt_vars)
        rendered_prompt = "\n\n---MSG---\n\n".join(
            f"[{m.type}]\n{m.content}" for m in rendered_messages
        )
        logger.info(
            f"📋 [FULL PROMPT] conversation={conversation_id} length={len(rendered_prompt)} chars"
        )
        logger.info(f"📋 [FULL PROMPT]\n{rendered_prompt}")

        # Send the rendered prompt to Sentry with full text as attachment
        # (breadcrumbs get [Filtered] by data scrubbing, attachments don't)
        with sentry_sdk.push_scope() as scope:
            scope.set_extra("conversation_id", conversation_id)
            scope.set_extra("question", question)
            scope.set_extra("prompt_length", len(rendered_prompt))
            scope.set_extra("mode", "quiz" if is_quiz else "answer")
            scope.add_attachment(
                bytes=rendered_prompt.encode("utf-8"),
                filename=f"prompt_{conversation_id}.txt",
                content_type="text/plain",
            )
            sentry_sdk.capture_message(
                f"LLM prompt for conversation {conversation_id}",
                level="info",
            )

        logger.info(
            f"🔗 Invoking LLM chain (matched_pages={len(matched_pages) if not is_quiz else 'N/A'} chars, exif={len(exif_str) if not is_quiz else 'N/A'} chars)..."
        )
        model_name = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
        operation = "rag.quiz" if is_quiz else "rag.answer"
        with sentry_sdk.start_span(op="llm.invoke", name=f"LLM {getattr(llm, 'model', 'unknown')}"):
            answer, usage_meta = traced_llm_call(
                chain=chain,
                params=prompt_vars,
                operation=operation,
                model=model_name,
                conversation_id=conversation_id,
                rendered_prompt=rendered_prompt,
            )
        # traced_llm_call returns (text, usage) — answer is already a string

        # Log the full question and model response for observability (visible in GCP Cloud Logging)
        logger.info(f"📝 [Q&A LOG] conversation={conversation_id} model={model_name}")
        logger.info(f"📝 [Q&A LOG] question={question}")
        logger.info(f"📝 [Q&A LOG] answer={answer[:500]}")

        # Token usage already logged by traced_llm_call; extract for Sentry span
        prompt_tokens = usage_meta.get("prompt_tokens", 0)
        completion_tokens = usage_meta.get("completion_tokens", 0)
        total_tokens = usage_meta.get("total_tokens", 0)
        cached = usage_meta.get("cached_tokens", 0)

        if prompt_tokens:
            if cached:
                logger.info(
                    f"💾 Prompt cache hit: {cached}/{prompt_tokens} tokens cached ({cached * 100 // max(prompt_tokens, 1)}%)"
                )
            else:
                logger.info(f"💾 Prompt cache miss: 0/{prompt_tokens} tokens cached")

            sentry_logger.info(
                "LLM invocation completed for conversation {conversation_id}",
                conversation_id=conversation_id,
                attributes={
                    "model": model_name,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cached_tokens": cached,
                    "answer_length": len(answer),
                    "chunk_count": len(rows),
                    "is_quiz": is_quiz,
                },
            )

            rag_span.set_data("model", model_name)
            rag_span.set_data("prompt_tokens", prompt_tokens)
            rag_span.set_data("completion_tokens", completion_tokens)
            rag_span.set_data("total_tokens", total_tokens)

        logger.info(f"✅ Generated answer: {answer[:100]}...")

        citations = _build_citations(rows)
        answer = _strip_orphan_source_tags(answer, len(citations))

        return {
            "answer": answer,
            "citations": citations,
        }
