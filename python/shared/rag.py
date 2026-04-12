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
    ("system", """You are a quiz generator. Based on the retrieved context, create an interactive quiz.

If the retrieved context is empty or does not contain enough information, respond with: "I could not find enough evidence in the uploaded files to create a quiz on this topic."

Output format: Start with a brief intro sentence, then output a quiz block using EXACTLY this format:

[quiz:{{"title":"Quiz title","questions":[{{"q":"Question text?","options":["Option A","Option B","Option C","Option D"],"correct":[0],"explanation":"Why this is correct"}}]}}]

Rules:
- Generate 3-5 multiple choice questions based on the content
- Each question has 3-4 options
- "correct" is an array of 0-based indices of correct answers (can be multiple)
- Include a brief explanation for each correct answer
- Questions should test understanding, not just recall
- Use [source:N] citations in questions/explanations where relevant
- The quiz JSON must be valid JSON on a single line after [quiz:
- Write the quiz in the same language as the retrieved context
- Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead.
- Before the [quiz:...] block, write 1-2 intro sentences about the quiz topic"""),
    ("human", """Question:
    {question}

    Retrieved context:
    {context}"""),
])


ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful RAG assistant.

    Answer the user's question using only the retrieved context below.
    If the answer is not present, say that you could not find enough evidence in the uploaded files.

    Additional guidelines:
    a) try to format the answer in bullet points or with "-" for easier readability when possible (or other format that suits the question)
    - but omit bullets if there are less than 3 points
    - avoid starting with a bullet point but rather start with a short intro sentence if using bullets
    - after bullets, you can add a concluding sentence if it adds value, but keep it concise
    b) avoid too many sentences in a row without any formatting - break them up with bullets or newlines if it improves readability
    c) use ** for bolding and _ for italics if it helps readability, use other markdown formatting sparingly
    d) do not just repeat the retrieved text, try to synthesize it into a helpful answer
    e) try to use information from multiple chunks if relevant
    f) IMPORTANT – citation format: After every sentence or claim that uses information from the retrieved context, you MUST insert an inline citation using EXACTLY this format: [source:N] where N is the source number. Examples of CORRECT citation format: [source:1], [source:2], [source:1][source:3]. If a sentence uses multiple sources, place multiple [source:N] markers, e.g. [source:1][source:2]. NEVER use bare brackets like [1], [2], [1][2][3][4], [1,2,3,4] — always include the "source:" prefix. ALWAYS write the word "source" in English, even if the rest of the answer is in another language. Do NOT translate "source" (e.g. do not write [źródło:1], [quelle:1], [fuente:1], etc.). Always cite your sources.

    Return a concise but useful answer with inline source citations using [source:N] format.
    Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead."""),
    ("human", """Question:
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
            model_kwargs={"reasoning_effort": settings.openai_reasoning_effort},
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


def _is_quiz_request(question: str) -> bool:
    return bool(_QUIZ_PATTERNS.search(question))


def answer_with_citations(collection_name: str, conversation_id: str, question: str, top_k: int = 4) -> dict:
    logger.info(f"❓ Answering question: {question[:100]}...")
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

    chain = prompt | llm
    logger.info(f"🔗 Invoking LLM chain...")
    ai_message = chain.invoke({
        "question": question,
        "context": context,
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

    return {
        "answer": answer,
        "citations": _build_citations(rows),
    }


def stream_answer_events(collection_name: str, conversation_id: str, question: str):
    logger.info(f"❓ Streaming answer for question: {question[:100]}...")
    
    rows = query_chunks(collection_name, conversation_id, question, top_k=4)
    logger.info(f"📚 Retrieved {len(rows)} context chunks")
    context = build_context(rows)

    llm = get_llm()

    # Choose prompt based on whether this is a quiz request
    is_quiz = _is_quiz_request(question)
    prompt = QUIZ_PROMPT if is_quiz else ANSWER_PROMPT
    if is_quiz:
        logger.info("🧩 Quiz mode detected, using QUIZ_PROMPT for streaming")

    chain = prompt | llm | StrOutputParser()
    logger.info(f"🔗 Starting stream...")

    # Stream real tokens from the LLM
    for token in chain.stream({"question": question, "context": context}):
        if token:
            yield f"event: token\ndata: {json.dumps({'token': token})}"

    # Send citations after streaming is done
    yield f"event: citations\ndata: {json.dumps({'citations': _build_citations(rows)})}"
