from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


@dataclass
class Chunk:
    chunk_id: str
    file_name: str
    text: str
    section: str | None
    page: int | None
    metadata: dict


def split_structured_text(text: str) -> list[Document]:
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
    )

    try:
        docs = md_splitter.split_text(text)
        if docs:
            return docs
    except Exception:
        pass

    paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
    return [Document(page_content=paragraph, metadata={}) for paragraph in paragraphs]


def split_into_chunks(file_name: str, text: str) -> list[Chunk]:
    structured_docs = split_structured_text(text)

    token_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1600,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[Chunk] = []
    index = 0

    for doc in structured_docs:
        child_docs = token_splitter.create_documents(
            [doc.page_content],
            metadatas=[doc.metadata],
        )
        for child_doc in child_docs:
            section = child_doc.metadata.get("Header 2") or child_doc.metadata.get("Header 1")
            page = None

            chunk = Chunk(
                chunk_id=f"{Path(file_name).stem}_chunk_{index}",
                file_name=file_name,
                text=child_doc.page_content,
                section=section,
                page=page,
                metadata=child_doc.metadata,
            )
            chunks.append(chunk)
            index += 1

    return chunks
