from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import get_settings
from .vector_store import query_chunks

import re

logger = logging.getLogger(__name__)

# Module-level cache for LLM instance
_llm_instance = None
_llm_provider_key = None

# Patterns that trigger quiz mode
_QUIZ_PATTERNS = re.compile(
    r'\b(quiz|kwiz|test|egzamin)\b',
    re.IGNORECASE,
)

QUIZ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a quiz generator. Based on the retrieved context and chat history, create an interactive quiz.

If neither the retrieved context nor the chat history contain enough information, respond with: "I could not find enough evidence in the uploaded files to create a quiz on this topic."

Output format: Start with a brief intro sentence, then output a quiz block using EXACTLY this format:

[quiz:{{"title":"Quiz title","questions":[{{"q":"Question text?","options":["Option A","Option B","Option C","Option D"],"correct":[0],"explanation":"Why this is correct"}}]}}]

Rules:
- Generate 3-5 multiple choice questions based on the content
- Each question has 3-4 options
- "correct" is an array of 0-based indices of correct answers (can be multiple)
- Include a brief explanation for each correct answer
- Questions should test understanding, not just recall
- Do NOT put [source:N] citations inside the quiz JSON (not in questions, options, or explanations)
- The quiz JSON must be valid JSON on a single line after [quiz:
- Write the quiz in the same language as the retrieved context
- Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead.
- Before the [quiz:...] block, write 1-2 intro sentences about the quiz topic"""),
    ("human", """Uploaded file descriptions (in chronological order):
    {welcome_messages}

    Chat history (last exchange):
    {chat_history}

    Question:
    {question}

    Retrieved context:
    {context}"""),
])


ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful RAG assistant.

    Answer the user's question using the retrieved context below, the uploaded file descriptions, and (when relevant) the chat history.
    The uploaded file descriptions contain summaries of ALL files uploaded to this conversation (in chronological order) - always treat them as primary context.
    The chat history may contain previous answers that are directly relevant to the current question - use them as additional context for follow-ups and creative or synthesis tasks.
    If neither the retrieved context, file descriptions, nor the chat history contain enough information to answer, say that you could not find enough evidence in the uploaded files.
    Use the chat history to understand follow-up questions and resolve references (e.g. "it", "that", "more details").

    Additional guidelines:
    a) try to format the answer in bullet points or with "-" for easier readability when possible (or other format that suits the question)
    - but omit bullets if there are less than 3 points
    - avoid starting with a bullet point but rather start with a short intro sentence if using bullets
    - after bullets, you can add a concluding sentence if it adds value, but keep it concise
    b) avoid too many sentences in a row without any formatting - break them up with bullets or newlines if it improves readability
    c) use **bolding** sparingly — only for the most important keywords, names, or numbers that the user should notice at a glance. Do not bold entire phrases or sentences. Use _ for italics if it helps readability. Use other markdown formatting sparingly
    d) do not just repeat the retrieved text, try to synthesize it into a helpful answer
    e) try to use information from multiple chunks if relevant
    f) IMPORTANT – citation format: Use EXACTLY this format: [source:N] where N is the source number. Examples: [source:1], [source:2], [source:1][source:3]. NEVER use bare brackets like [1], [2] — always include the "source:" prefix. ALWAYS write "source" in English, never translate it.
    g) Citation frequency: Do NOT cite every sentence. Place citations sparingly — only at the end of a paragraph or section, not after each individual point. When a section or group of bullets comes from the same source, use a single citation at the end. Aim for roughly one citation per paragraph or topic block, not per sentence.
    h) Action buttons: When you want to suggest a follow-up action to the user (like creating a diagram, quiz, summary, checklist, etc.), do NOT write it as inline text. Instead, output action markers using this format: [action:Label]. For example, instead of writing "mogę też stworzyć diagram albo quiz", write: [action:Socrates quotes - create diagram] [action:Socrates quotes - create quiz]. The label MUST include the main topic/subject for context (so the model can answer it standalone), and be at least 4 words long. You can place multiple action markers next to each other. Always place them at the very end of your answer, after all content.

    Return a concise but useful answer with inline source citations using [source:N] format.
    Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead."""),
    ("human", """Uploaded file descriptions (in chronological order):
    {welcome_messages}

    Chat history (last exchange):
    {chat_history}

    Question:
    {question}

    Retrieved context:
    {context}"""),
])
    
def build_context(rows: list[dict]) -> str:
    parts = []
    for i, row in enumerate(rows, 1):
        label = f"[{i}] File: {row['file_name']}"
        if row.get("section"):
            label += f" | Section: {row['section']}"
        if row.get("page") is not None:
            label += f" | Page: {row['page']}"
        parts.append(f"{label}\n{row['text']}")
    return "\n\n---\n\n".join(parts)


def get_llm() -> Any:
    """Get LLM instance based on configured provider (cached).
    
    Raises ValueError if required API key is missing.
    """
    global _llm_instance, _llm_provider_key
    settings = get_settings()
    
    # Cache key: provider + model so we reuse the same instance within a process
    cache_key = f"{settings.llm_provider}:{settings.anthropic_chat_model if settings.llm_provider == 'anthropic' else settings.openai_chat_model}:{settings.openai_reasoning_effort}"
    if _llm_instance is not None and _llm_provider_key == cache_key:
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
        # Core EXIF fields
        fields = [
            ("Camera", camera),
            ("Date taken", meta.get("date_taken")),
            ("Dimensions", f"{meta.get('image_width')}x{meta.get('image_height')}" if meta.get("image_width") else None),
            ("File size", meta.get("file_size_bytes")),
            ("ISO", meta.get("iso")),
            ("Exposure", meta.get("exposure_time")),
            ("F-number", meta.get("f_number")),
            ("Focal length", meta.get("focal_length")),
            ("Lens", meta.get("lens_model")),
            ("Software", meta.get("software")),
            ("GPS", f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}" if meta.get("gps_latitude") else None),
        ]
        has_exif = False
        for label, value in fields:
            if value:
                has_exif = True
                parts.append(f"- **{label}**: {value}")
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
    r'(recognize name|rozpoznaj osob)',
    re.IGNORECASE,
)


def _is_recognize_request(question: str) -> bool:
    return bool(_RECOGNIZE_PATTERNS.search(question) or _RECOGNIZE_PROMPT_PATTERN.search(question))


def _handle_recognize(
    question: str,
    image_file_paths: list[str] | None,
    file_metadata: dict[str, dict] | None,
    welcome_messages: list[str] | None,
) -> dict | None:
    """Handle 'recognize name' by calling Vision API + LLM identification.
    
    Returns {"answer": ..., "citations": []} or None if not applicable.
    """
    if not image_file_paths:
        return None

    from .metadata import enrich_metadata_web

    welcome_str = _format_welcome_messages(welcome_messages)

    logger.info(f"🔍 Recognition mode: calling Vision API for {len(image_file_paths)} image(s)")
    enrichment = enrich_metadata_web(
        file_paths=image_file_paths,
        exif_metadata=file_metadata,
        welcome_message=welcome_str,
    )

    if not enrichment:
        # Vision API returned nothing — fall back to normal RAG
        logger.info("🔍 Vision API returned no results, falling back to normal RAG")
        return None

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


def answer_with_citations(collection_name: str, conversation_id: str, question: str, top_k: int = 4, chat_history: list[dict] | None = None, welcome_messages: list[str] | None = None, image_file_paths: list[str] | None = None, file_metadata: dict[str, dict] | None = None) -> dict:
    logger.info(f"❓ Answering question: {question[:100]}...")

    # Check for "show EXIF metadata" intent — return stored metadata directly
    if _is_exif_request(question) and file_metadata:
        result = _handle_exif(file_metadata)
        if result:
            return result

    # Check for "recognize name" intent — triggers Vision API
    if _is_recognize_request(question) and image_file_paths:
        result = _handle_recognize(question, image_file_paths, file_metadata, welcome_messages)
        if result:
            return result

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

    llm = get_llm()

    # Choose prompt based on whether this is a quiz request
    is_quiz = _is_quiz_request(question)
    prompt = QUIZ_PROMPT if is_quiz else ANSWER_PROMPT
    if is_quiz:
        logger.info("🧩 Quiz mode detected, using QUIZ_PROMPT")

    history_str = _format_chat_history(chat_history)
    welcome_str = _format_welcome_messages(welcome_messages)

    chain = prompt | llm
    logger.info(f"🔗 Invoking LLM chain...")
    ai_message = chain.invoke({
        "question": question,
        "context": context,
        "chat_history": history_str,
        "welcome_messages": welcome_str,
    })
    answer = ai_message.content

    # Log prompt cache metrics if available
    usage = ai_message.response_metadata.get("token_usage") or ai_message.response_metadata.get("usage", {})
    if usage:
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        if cached:
            logger.info(f"💾 Prompt cache hit: {cached}/{prompt_tokens} tokens cached ({cached*100//prompt_tokens}%)")
        else:
            logger.info(f"💾 Prompt cache miss: 0/{prompt_tokens} tokens cached")

    logger.info(f"✅ Generated answer: {answer[:100]}...")

    citations = _build_citations(rows)
    answer = _strip_orphan_source_tags(answer, len(citations))

    return {
        "answer": answer,
        "citations": citations,
    }
