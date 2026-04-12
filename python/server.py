"""Persistent FastAPI server for the RAG pipeline.

Keeps heavy imports (langchain, chromadb, openai) loaded in memory
so answering questions doesn't pay the ~20s import cost each time.
"""
from __future__ import annotations

import json
import logging
import asyncio
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.rag import answer_with_citations, stream_answer_events
from shared.indexing import index_documents
from shared.vector_store import collection_count

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MyChatbot RAG Server")


class AnswerRequest(BaseModel):
    conversation_id: str
    collection_name: str
    question: str
    chat_history: list[dict] | None = None


class IndexRequest(BaseModel):
    conversation_id: str
    collection_name: str
    file_paths: list[str]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/collection-count/{collection_name}")
async def get_collection_count(collection_name: str):
    count = collection_count(collection_name)
    return {"collection_name": collection_name, "count": count}


@app.post("/index")
async def index(req: IndexRequest):
    try:
        result = await asyncio.to_thread(
            index_documents,
            conversation_id=req.conversation_id,
            collection_name=req.collection_name,
            file_paths=req.file_paths,
        )
        return result
    except Exception as e:
        logger.exception("Error indexing documents")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/answer")
async def answer(req: AnswerRequest):
    try:
        result = await asyncio.to_thread(
            answer_with_citations,
            collection_name=req.collection_name,
            conversation_id=req.conversation_id,
            question=req.question,
            chat_history=req.chat_history,
        )
        return result
    except Exception as e:
        logger.exception("Error answering question")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stream-answer")
async def stream_answer(req: AnswerRequest):
    async def generate() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _produce():
            try:
                for event in stream_answer_events(
                    collection_name=req.collection_name,
                    conversation_id=req.conversation_id,
                    question=req.question,
                    chat_history=req.chat_history,
                ):
                    queue.put_nowait(event + "\n")
            except Exception as e:
                logger.exception("Error streaming answer")
                queue.put_nowait(f"event: error\ndata: {json.dumps({'error': str(e)})}\n")
            finally:
                queue.put_nowait(None)  # sentinel

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _produce)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8321)
