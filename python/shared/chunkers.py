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
    # For markdown files with headers, use structured markdown splitting
    if "#" in text[:500]:  # Check if there are markdown headers in the beginning
        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ]
        )
        try:
            docs = md_splitter.split_text(text)
            if docs and len(docs) > 1:  # Only use if it actually split the document
                return docs
        except Exception:
            pass

    # Normalize line endings to \n for consistent splitting
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Split by double newlines (paragraphs) for plain text files
    # This preserves multi-line sections like numbered items with bullet points
    paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
    documents = []
    
    for paragraph in paragraphs:
        lines = paragraph.split("\n")
        
        # Detect if this paragraph is a section header (single line, no special markers)
        # Filter out sentence-like content: lines starting lowercase or ending with period/question mark
        is_header = (
            len(lines) == 1 and 
            not lines[0].startswith("*") and 
            lines[0] and
            not lines[0][0].isdigit() and
            not lines[0][0].islower() and  # Real headers usually start with uppercase
            not lines[0].rstrip().endswith((".", "?", "!"))  # Headers don't end with punctuation
        )
        
        metadata = {"is_header": is_header}
        
        # Extract header info if it's a header
        if is_header:
            metadata["header"] = lines[0]
        
        documents.append(Document(page_content=paragraph, metadata=metadata))
    
    return documents


def split_into_chunks(file_name: str, text: str) -> list[Chunk]:
    structured_docs = split_structured_text(text)

    token_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1600,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[Chunk] = []
    index = 0
    current_section = None

    for doc in structured_docs:
        # Track section headers for context
        if doc.metadata.get("is_header"):
            current_section = doc.page_content
        
        # For small paragraphs, keep them as-is (each paragraph = one embedding)
        # Only split larger paragraphs further
        if len(doc.page_content) <= 1600:
            # For headers, use the header text as section
            # For content chunks, use first line of the chunk as a distinguishing label
            if doc.metadata.get("is_header"):
                section = doc.page_content
            else:
                # Use first line of content as section label for better tab naming
                first_line = doc.page_content.split("\n")[0].strip()
                if len(first_line) > 50:
                    first_line = first_line[:50] + "…"
                section = first_line or current_section
            
            chunk = Chunk(
                chunk_id=f"{Path(file_name).stem}_chunk_{index}",
                file_name=file_name,
                text=doc.page_content,
                section=section,
                page=None,
                metadata=doc.metadata,
            )
            chunks.append(chunk)
            index += 1
        else:
            # Split larger paragraphs
            child_docs = token_splitter.create_documents(
                [doc.page_content],
                metadatas=[doc.metadata],
            )
            for child_doc in child_docs:
                # Try to get section from markdown headers first, then use chunk's first line
                section = (
                    child_doc.metadata.get("Header 2") or 
                    child_doc.metadata.get("Header 1") or 
                    current_section
                )
                
                # If no header metadata, use first line of this specific chunk
                if section == current_section and not doc.metadata.get("is_header"):
                    first_line = child_doc.page_content.split("\n")[0].strip()
                    if len(first_line) > 50:
                        first_line = first_line[:50] + "…"
                    if first_line:
                        section = first_line

                chunk = Chunk(
                    chunk_id=f"{Path(file_name).stem}_chunk_{index}",
                    file_name=file_name,
                    text=child_doc.page_content,
                    section=section,
                    page=None,
                    metadata=child_doc.metadata,
                )
                chunks.append(chunk)
                index += 1

    return chunks
