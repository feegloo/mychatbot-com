from __future__ import annotations

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import get_settings
from .vector_store import query_chunks


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


def answer_with_citations(collection_name: str, conversation_id: str, question: str, top_k: int = 4) -> dict:
    settings = get_settings()
    rows = query_chunks(collection_name, conversation_id, question, top_k=top_k)
    context = build_context(rows)

    llm = ChatOpenAI(model=settings.openai_chat_model, temperature=0, api_key=settings.openai_api_key)
    chain = ANSWER_PROMPT | llm | StrOutputParser()
    answer = chain.invoke({
        "question": question,
        "context": context,
    })

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
    result = answer_with_citations(collection_name, conversation_id, question)
    for token in result["answer"]:
        yield f"event: token\ndata: {json.dumps({'token': token})}"
    yield f"event: citations\ndata: {json.dumps({'citations': result['citations']})}"
