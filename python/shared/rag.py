from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from .config import get_settings
from .vector_store import query_chunks

logger = logging.getLogger(__name__)


ANSWER_PROMPT = ChatPromptTemplate.from_template(
    """
    You are a helpful RAG assistant.

    Answer the user's question using only the retrieved context below.
    If the answer is not present, say that you could not find enough evidence in the uploaded files.

    Question:
    {question}

    Retrieved context:
    {context}

    Return a concise but useful answer.
    """
)


    
    
    
def build_context(rows: list[dict]) -> str:
    parts = []
    for row in rows:
        label = f"File: {row['file_name']}"
        if row.get("section"):
            label += f" | Section: {row['section']}"
        if row.get("page") is not None:
            label += f" | Page: {row['page']}"
        parts.append(f"{label}\n{row['text']}")
    return "\n\n---\n\n".join(parts)


def get_llm() -> Any:
    """Get LLM instance based on configured provider.
    
    Raises ValueError if required API key is missing.
    """
    settings = get_settings()
    
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable "
                "or set LLM_PROVIDER=openai with OPENAI_API_KEY"
            )
        logger.info(f"🤖 Using Anthropic Claude model: {settings.anthropic_chat_model}")
        return ChatAnthropic(
            model=settings.anthropic_chat_model,
            api_key=settings.anthropic_api_key,
            temperature=0,
        )
    else:  # openai
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable"
            )
        logger.info(f"🤖 Using OpenAI model: {settings.openai_chat_model}")
        return ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )


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
    chain = ANSWER_PROMPT | llm | StrOutputParser()
    logger.info(f"🔗 Invoking LLM chain...")
    answer = chain.invoke({
        "question": question,
        "context": context,
    })
    logger.info(f"✅ Generated answer: {answer[:100]}...")

    citations = []
    for row in rows:
        citations.append({
            "fileName": row["file_name"],
            "chunkId": row["chunk_id"],
            "text": row["text"],
            "section": row.get("section"),
            "page": row.get("page"),
        })

    return {
        "answer": answer,
        "citations": citations,
    }


def stream_answer_events(collection_name: str, conversation_id: str, question: str):
    logger.info(f"❓ Streaming answer for question: {question[:100]}...")
    
    rows = query_chunks(collection_name, conversation_id, question, top_k=4)
    logger.info(f"📚 Retrieved {len(rows)} context chunks")
    context = build_context(rows)

    llm = get_llm()
    chain = ANSWER_PROMPT | llm | StrOutputParser()
    logger.info(f"🔗 Starting stream...")

    # Stream real tokens from the LLM
    for token in chain.stream({"question": question, "context": context}):
        if token:
            yield f"event: token\ndata: {json.dumps({'token': token})}"

    # Send citations after streaming is done
    citations = []
    for row in rows:
        citations.append({
            "fileName": row["file_name"],
            "chunkId": row["chunk_id"],
            "text": row["text"],
            "section": row.get("section"),
            "page": row.get("page"),
        })
    yield f"event: citations\ndata: {json.dumps({'citations': citations})}"
