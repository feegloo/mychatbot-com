from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import get_settings
from .vector_store import query_chunks

import re

logger = logging.getLogger(__name__)

# Max chars of full matched pages to include in answer prompts.
_MATCHED_PAGES_MAX_CHARS = 40_000

# Module-level cache for LLM instance
_llm_instance = None
_llm_provider_key = None

# Multiple seed values to introduce variation for repeated prompts (OpenAI only)
_SEED_OPTIONS = [365, 742, 158, 2901, 4417, 5830, 6193, 7764, 8529, 9046]

# Patterns that trigger quiz mode
_QUIZ_PATTERNS = re.compile(
    r'\b(quiz|kwiz|test|egzamin)\b',
    re.IGNORECASE,
)

QUIZ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a quiz generator. Based on the retrieved context and chat history, create an interactive quiz.

If neither the retrieved context nor the chat history contain enough information, respond with: "I could not find enough evidence in the uploaded files to create a quiz on this topic."

IMPORTANT: Randomly choose ONE quiz type (roughly 50/50 chance):
- **Single choice** ("multiple": false) — each question has exactly ONE correct answer.
- **Multiple choice** ("multiple": true) — each question can have 1-4 correct answers (but never 0).

Output format: Start with a brief intro sentence, then output a quiz block using EXACTLY this format:

[quiz:{{"title":"Quiz title","multiple":false,"questions":[{{"q":"Question text?","options":["Option A","Option B","Option C","Option D"],"correct":[0],"explanation":"Why this is correct"}}]}}]

Rules:
- Generate exactly 5 questions based on the content
- The top-level "multiple" field MUST be present: true for multiple choice, false for single choice
- Each question has 3-4 options
- For single choice ("multiple": false): "correct" must contain exactly ONE index
- For multiple choice ("multiple": true): "correct" contains 1-4 indices (never 0)
- Include a brief explanation for each correct answer
- Questions should test understanding, not just recall
- CRITICAL: NEVER include [source:N], [source:1], [source:2] or any source citations anywhere in the quiz JSON. No citations in questions, options, explanations, or title. Source references break the JSON rendering and must be completely omitted from the entire [quiz:...] block.
- The quiz JSON must be valid JSON on a single line after [quiz:
- Write the quiz in the same language as the retrieved context
- Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead.
- Before the [quiz:...] block, write 1-2 intro sentences about the quiz topic. Explicitly mention whether this is a single choice quiz (one correct answer per question) or a multiple choice quiz (one or more correct answers per question)."""),
    ("human", """Raw document text (original file content - use for quiz questions):
    {raw_text}

    Page summaries (overview of each page):
    {page_summaries}

    Uploaded file descriptions (in chronological order):
    {welcome_messages}

    Chat history (last exchange):
    {chat_history}

    Question:
    {question}

    Retrieved context (most relevant chunks):
    {context}"""),
])


ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful AI chatbot assistant. Answer the user's question accurately using ONLY the context provided below.

== USER QUESTION ==
"{question}"

Now read all context sections below carefully before answering.

Sections provided:
1. Matching Sources (top embedding matches from the vector database, with similarity scores)
2. Answer Guidelines (tone, structured output, citation rules)
3. Welcome Page Description (short summary of each uploaded file)
4. Full Pages of Matched Sources (complete page text for pages where matches were found)
5. EXIF Metadata (image file metadata, if available)
6. Start Answering

--

== SECTION 2: Answer Guidelines ==

a) Tone & Goal:
- Be helpful, accurate, and concise. Synthesize information - do not just repeat the retrieved text.
- If none of the context contains enough information, say you could not find enough evidence in the uploaded files.
- Use the chat history to resolve follow-up references (e.g. "it", "that", "more details").

b) Expert Insight:
- When the content is domain-specific (medical, legal, financial, technical), adopt the perspective of a domain expert.
- Provide actionable analysis, not just facts.

b2) Style & Tone Mimicry:
- Carefully analyze the writing style, tone, and voice of the uploaded source text in the context sections below.
- Adapt your own response to mirror that style. Write as if the AUTHOR of the uploaded material were personally answering the question in conversation.
- For example: if the source is a Stephen King novel, respond with King's vivid, colloquial, suspenseful storytelling voice. If it is an academic paper, respond with precise, formal, scholarly prose. If it is a casual blog post, be breezy and conversational. If it is poetry, let your language be lyrical.
- Match specific stylistic traits you detect: sentence length, vocabulary level, use of metaphor, humor, directness, formality, rhythm, and emotional register.
- This style adaptation applies to your explanations and commentary. Citations, action buttons, and structural formatting rules still apply as specified.
- When multiple files with different styles are uploaded, blend them or lean toward the style of the most relevant source for the current question.

c) Structured Output:
- Use bullet points or "-" for readability when there are 3+ points. Start with a short intro sentence before bullets.
- **Bolding**: Use VERY sparingly. Bold at most 1-2 words per paragraph — only a single key name, number, or term that the user absolutely must notice. NEVER bold entire phrases, book titles, or multiple words in a row. If more than ~10% of the text is bold, you are overdoing it. When in doubt, do not bold.
- Supported rich output formats: source citations, quiz, checklist, recipe, poem, diagram, mermaid, table. Use whichever best fits the question.
- Poem / Quote block: When writing a poem, lyrics, inspirational quote, or literary passage, wrap the content in [poem]...[/poem] markers. NEVER use bullet points or lists inside a poem block — write free verse, one line per line. The frontend renders this as a beautiful centered blockquote with decorative quotation marks and elegant typography. Example:
  [poem]
  I listen to the pull of my heart,
  where dreams begin before they are seen.
  I risk the wrong turn,
  because stillness is the safest kind of fear.
  [/poem]
- Markdown formatting: The frontend renders full Markdown. Use rich formatting when it improves readability:
  - Use ### for section headings (rendered as <h3>). Use them to break up longer answers into logical sections.
  - Use `inline code` for technical terms, file names, commands, variable names.
  - Use fenced code blocks with language tags for multi-line code, configs, or structured data:
    ```python
    def example():
        pass
    ```
  - Use > blockquotes for direct quotes from the source documents.
  - Use tables (| col1 | col2 |) when presenting structured/comparative data.
  - Use numbered lists (1. 2. 3.) for ordered sequences, steps, or rankings. Use bullet lists (- or *) for unordered items.
  - Use _italics_ generously for: book/film/song titles (_The Alchemist_), foreign words, direct quotes from sources, rhetorical emphasis, and softer highlighting when bold would be too heavy. Italics add elegance — use them often.
  - Use ++underline++ for key terms, definitions, or words that deserve visual emphasis different from bold/italic.
  - Use --- horizontal rules to separate major sections if the answer is very long.
- Colored text: OCCASIONALLY highlight important words with color markers using [c:color]word[/c] syntax. Use meaningfully and sparingly (max 2-3 per answer):
  - [c:green]word[/c] — positive, correct, success, approved, healthy, growth
  - [c:red]word[/c] — negative, danger, error, warning, critical, decline
  - [c:amber]word[/c] — caution, moderate, pending, attention needed
  - [c:blue]word[/c] — informational, links, references, technical terms
  - [c:purple]word[/c] — creative, special, unique, premium, rare
  - [c:pink]word[/c] — love, beauty, emotion, personal, warm
  - [c:cyan]word[/c] — data, science, cool facts, measurements
  - [c:orange]word[/c] — energy, excitement, important dates, prices
  - [c:lime]word[/c] — nature, eco, fresh, new, organic
  - [c:rose]word[/c] — elegant, delicate, subtle emphasis
- Math / LaTeX: When answering math, science, or technical questions, use LaTeX syntax. Use $...$ for inline math (e.g. $E = mc^2$) and $$...$$ for display math blocks. The frontend renders KaTeX.
- IMPORTANT - citation format: Use EXACTLY [source:N] where N is the source number. Examples: [source:1], [source:2], [source:1][source:3]. NEVER use bare brackets like [1], [2]. ALWAYS write "source" in English, never translate it.
- Citation frequency: Cite generously for each key fact or claim. Place citations at the end of each paragraph or bullet point. When a group of bullets comes from the same source, use a single citation at the end.
- If a source has a high similarity score (close to 1.0), it is highly relevant - prioritize it. Lower scores mean weaker matches.

d) Action Buttons:
- When suggesting a follow-up action (diagram, quiz, summary, checklist, etc.), output action markers: [action:Label]. The label MUST include the main topic and be at least 4 words long. Place them at the very end of your answer, after all content.
- ALWAYS generate 1-5 follow-up action buttons after your answer. These should be natural next questions or actions the user might want based on your answer and the context.
- Each label should be concise (max 10 words), include the topic, and be written in the SAME language as your answer.
- EVERY action button MUST end with a relevant emoji. Pick the emoji that best matches the action or topic.
- Pick from: deeper questions about the topic, related facts, creative actions (write inspired poem, write inspired chapter, create diagram, quiz, checklist, summary, comparison table, generate image, etc.)
- When suggesting "generate image", the label MUST contain the exact phrase "generate image" (in English) or "wygeneruj obraz" (in Polish). This triggers the image generation API.
- Example: [action:Socrates quotes - create diagram 🖼️] [action:What were Socrates' main teachings? 🤔] [action:Socrates philosophy - write inspired poem 🎭] [action:generate image - ancient Greek agora 🎨]

e) Emoji Usage:
- Use emojis naturally throughout your answers to make them more engaging, fun, and scannable.
- Prefer playful, expressive, light-hearted emoji over plain/boring ones. For example:
  - Instead of 📄 use 🪄 or ✨ for magic/interesting findings
  - Instead of 📝 use 🧠 for knowledge, 💡 for ideas, 🔥 for hot takes
  - Use 🎯 for key points, 🌟 for highlights, 🚀 for progress/speed
  - Use 👀 for "look at this", 🤯 for surprising facts, 🎉 for celebrations
  - Use 🍀 for luck/positive, 🌈 for variety/diversity, 🧩 for connections
  - Use 💎 for valuable info, 🏆 for best/top items, 🎨 for creative content
  - Use ⚡ for quick facts, 🔮 for predictions, 🗝️ for key insights
  - Avoid plain document-style emoji like 📄📁📂📃 — they are boring
  - Never use offensive, violent, or inappropriate emoji
- Add a relevant emoji at the start of bullet point sections or key headings.
- Do not overdo it - 1 emoji per section header or key bullet is enough. Avoid emoji in the middle of sentences.
- For action buttons [action:...], also include a trailing emoji in the label.

Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead."""),
    ("human", """== SECTION 1: Matching Sources ==
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

== SECTION 5: EXIF Metadata ==
{exif_metadata}

--

== SECTION 5b: Chat History (Previous Messages) ==
Below is the most recent question the user asked and the answer you gave. Use this to understand follow-up questions and maintain conversational continuity. If empty, this is the first question in the conversation.
{chat_history}

--

== SECTION 6: Start Answering ==
You have all the context above. Now answer the following question thoroughly with inline [source:N] citations:
"{question}"
"""),
])
    
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
        if row.get("section"):
            label += f" | Section: {row['section']}"
        label += f" | Similarity: {similarity:.2f}"
        parts.append(f"{label}\n\"{row['text']}\"")
    return "\n\n--\n\n".join(parts)


def get_llm() -> Any:
    """Get LLM instance based on configured provider (cached).
    
    When USE_GEMMA=true, uses local Ollama Gemma 4 model.
    Otherwise falls back to OpenAI / Anthropic cloud models.
    Raises ValueError if required API key is missing or Ollama is unreachable.
    """
    global _llm_instance, _llm_provider_key
    settings = get_settings()
    
    # Gemma overrides all other provider settings when enabled
    if settings.use_gemma:
        cache_key = f"gemma:{settings.gemma_model}:{settings.gemma_base_url}"
        if _llm_instance is not None and _llm_provider_key == cache_key:
            return _llm_instance
        
        from langchain_ollama import ChatOllama
        logger.info(f"🤖 Using local Gemma model via Ollama: {settings.gemma_model} at {settings.gemma_base_url}")
        _llm_instance = ChatOllama(
            model=settings.gemma_model,
            base_url=settings.gemma_base_url,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
        )
        _llm_provider_key = cache_key
        return _llm_instance

    # Cache key: provider + model so we reuse the same instance within a process
    cache_key = f"{settings.llm_provider}:{settings.anthropic_chat_model if settings.llm_provider == 'anthropic' else settings.openai_chat_model}:{settings.openai_reasoning_effort}"
    if _llm_instance is not None and _llm_provider_key == cache_key:
        if settings.llm_provider not in ("anthropic",):
            seed = random.choice(_SEED_OPTIONS)
            return _llm_instance.bind(seed=seed)
        return _llm_instance
    
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable "
                "or set LLM_PROVIDER=openai with OPENAI_API_KEY"
            )
        from langchain_anthropic import ChatAnthropic
        logger.info(f"🤖 Using Anthropic Claude model: {settings.anthropic_chat_model}")
        _llm_instance = ChatAnthropic(
            model=settings.anthropic_chat_model,
            api_key=settings.anthropic_api_key,
            temperature=0,
        )
    else:  # openai
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable"
            )
        logger.info(f"🤖 Using OpenAI model: {settings.openai_chat_model} (reasoning_effort={settings.openai_reasoning_effort})")
        _llm_instance = ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            temperature=1,
            reasoning_effort=settings.openai_reasoning_effort,
        )
    
    _llm_provider_key = cache_key
    # Bind a random seed to OpenAI calls to vary responses for repeated prompts
    if settings.llm_provider not in ("anthropic",) and not settings.use_gemma:
        seed = random.choice(_SEED_OPTIONS)
        logger.info(f"🎲 Selected random seed: {seed}")
        return _llm_instance.bind(seed=seed)
    return _llm_instance


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
    return re.sub(r'\[source:\s*(\d+(?:,\s*\d+)*)\]', _replace, answer)


# Patterns that trigger EXIF metadata display
_EXIF_PATTERNS = re.compile(
    r'(show exif|exif metadata|pokaż metadane exif|pokaż exif|metadane exif)',
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
            ("GPS", f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}" if meta.get("gps_latitude") else None),
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
    r'\b(recognize|rozpoznaj|identify|identyfikuj)\b.*\b(name|person|osob|face|twarz|imi)',
    re.IGNORECASE,
)

# Simpler pattern: the suggested prompt format itself
_RECOGNIZE_PROMPT_PATTERN = re.compile(
    r'(recognize person name|rozpoznaj osob)',
    re.IGNORECASE,
)


def _is_recognize_request(question: str) -> bool:
    m1 = _RECOGNIZE_PATTERNS.search(question)
    m2 = _RECOGNIZE_PROMPT_PATTERN.search(question)
    is_match = bool(m1 or m2)
    logger.info(f"🔍 _is_recognize_request('{question[:80]}'): {is_match} (pattern1={bool(m1)}, pattern2={bool(m2)})")
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
        logger.info("🔍 Vision API returned no results (empty enrichment dict), falling back to normal RAG")
        return None
    
    logger.info(f"🔍 Enrichment result keys per file: { {k: list(v.keys()) for k, v in enrichment.items()} }")

    # Build a human-readable answer from the identification results
    parts = []
    for filename, data in enrichment.items():
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
            parts.append(f"**[{identified_name}]({search_url})** (confidence: {confidence}, category: {category})")
            if reasoning:
                parts.append(f"- {reasoning}")
        elif labels:
            parts.append(f"Could not identify a specific name, but the image matches: {', '.join(labels)}")
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


def _format_chat_history(chat_history: list[dict] | None) -> str:
    """Format the last Q&A exchange into a string for the prompt."""
    if not chat_history:
        return "(no previous conversation)"
    parts = []
    for msg in chat_history:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        # Truncate long assistant answers to keep context window reasonable
        if len(content) > 1000:
            content = content[:1000] + "..."
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


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
        _page_header_re = re.compile(r'^# Page (\d+)$', re.MULTILINE)
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
                    parts.append(f"[Full Page {page_num} of {fname}]\n\"{text}\"")

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
                ("Dimensions", f"{meta.get('image_width')}x{meta.get('image_height')}" if meta.get("image_width") else None),
                ("ISO", meta.get("iso")),
                ("Exposure", meta.get("exposure_time")),
                ("F-number", meta.get("f_number")),
                ("Focal length", meta.get("focal_length")),
                ("Lens", meta.get("lens_model")),
                ("GPS", f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}" if meta.get("gps_latitude") else None),
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


def answer_with_citations(collection_name: str, conversation_id: str, question: str, top_k: int = 10, chat_history: list[dict] | None = None, welcome_messages: list[str] | None = None, image_file_paths: list[str] | None = None, file_metadata: dict[str, dict] | None = None, storage_dir: str | None = None) -> dict:
    import sentry_sdk
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
        logger.info(f"🔍 Checking recognize intent: image_file_paths={'present, count=' + str(len(image_file_paths)) if image_file_paths else 'None'}")
        if _is_recognize_request(question) and image_file_paths:
            result = _handle_recognize(question, image_file_paths, file_metadata, welcome_messages)
            if result:
                logger.info(f"🔍 Recognition returned answer ({len(result.get('answer', ''))} chars)")
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
            prompt_vars = {
                "question": question,
                "context": context,
                "chat_history": history_str,
                "welcome_messages": welcome_str,
                "matched_pages": matched_pages,
                "exif_metadata": exif_str,
            }

        # Render the full prompt string and log it for debugging
        rendered_messages = prompt.format_messages(**prompt_vars)
        rendered_prompt = "\n\n---MSG---\n\n".join(
            f"[{m.type}]\n{m.content}" for m in rendered_messages
        )
        logger.info(f"📋 [FULL PROMPT] conversation={conversation_id} length={len(rendered_prompt)} chars")
        logger.info(f"📋 [FULL PROMPT]\n{rendered_prompt}")

        # Send the rendered prompt to Sentry as a debug message
        sentry_sdk.capture_message(
            f"LLM prompt for conversation {conversation_id}",
            level="info",
            extras={
                "conversation_id": conversation_id,
                "question": question,
                "prompt_length": len(rendered_prompt),
                "prompt": rendered_prompt[:100_000],  # cap at 100K to avoid Sentry limits
                "mode": "quiz" if is_quiz else "answer",
            },
        )

        logger.info(f"🔗 Invoking LLM chain (matched_pages={len(matched_pages) if not is_quiz else 'N/A'} chars, exif={len(exif_str) if not is_quiz else 'N/A'} chars)...")
        with sentry_sdk.start_span(op="llm.invoke", name=f"LLM {getattr(llm, 'model', 'unknown')}"):
            ai_message = chain.invoke(prompt_vars)
        answer = ai_message.content

        # Log the full question and model response for observability (visible in GCP Cloud Logging)
        model_name = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
        logger.info(f"📝 [Q&A LOG] conversation={conversation_id} model={model_name}")
        logger.info(f"📝 [Q&A LOG] question={question}")
        logger.info(f"📝 [Q&A LOG] answer={answer[:500]}")

        # Log prompt cache metrics if available
        usage = ai_message.response_metadata.get("token_usage") or ai_message.response_metadata.get("usage", {})
        if usage:
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            if cached:
                logger.info(f"💾 Prompt cache hit: {cached}/{prompt_tokens} tokens cached ({cached*100//prompt_tokens}%)")
            else:
                logger.info(f"💾 Prompt cache miss: 0/{prompt_tokens} tokens cached")
            logger.info(f"📊 Token usage: prompt={prompt_tokens} completion={completion_tokens} total={prompt_tokens + completion_tokens}")

            rag_span.set_data("model", model_name)
            rag_span.set_data("prompt_tokens", prompt_tokens)
            rag_span.set_data("completion_tokens", completion_tokens)
            rag_span.set_data("total_tokens", prompt_tokens + completion_tokens)

        logger.info(f"✅ Generated answer: {answer[:100]}...")

        citations = _build_citations(rows)
        answer = _strip_orphan_source_tags(answer, len(citations))

        return {
            "answer": answer,
            "citations": citations,
        }
