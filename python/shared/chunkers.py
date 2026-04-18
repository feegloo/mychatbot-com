from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from chonkie import RecursiveChunker, RecursiveRules


@dataclass
class Chunk:
    chunk_id: str
    file_name: str
    text: str
    section: str | None
    page: int | None
    metadata: dict


# Markdown-aware recursive rules (splits at headers before paragraphs)
_MARKDOWN_RULES = RecursiveRules.from_recipe("markdown")

# Shared chunker instance (character-based, ~1600 chars per chunk)
_chunker = RecursiveChunker(
    chunk_size=1600,
    tokenizer="character",
    rules=_MARKDOWN_RULES,
    min_characters_per_chunk=24,
)


def _section_label(text: str) -> str | None:
    """Extract a short section label from the first line of a chunk."""
    first_line = text.split("\n")[0].strip()
    if not first_line:
        return None
    if len(first_line) > 50:
        first_line = first_line[:50] + "…"
    return first_line


# Regex matching "# Page N" headers inserted by extract_pdf()
_PAGE_HEADER_RE = re.compile(r"^# Page (\d+)\b", re.MULTILINE)


def _extract_page_from_chunk(text: str) -> int | None:
    """Return the page number from the first '# Page N' header in *text*."""
    m = _PAGE_HEADER_RE.search(text)
    return int(m.group(1)) if m else None


def _last_page_before(text: str, offset: int) -> int | None:
    """Return the page number from the last '# Page N' header before *offset*."""
    page: int | None = None
    for m in _PAGE_HEADER_RE.finditer(text):
        if m.start() > offset:
            break
        page = int(m.group(1))
    return page


def _has_markdown_headers(text: str) -> bool:
    """Check if text contains markdown-style headers."""
    return bool(re.search(r"^#{1,6}\s", text, re.MULTILINE))


def _split_paragraphs(text: str) -> list[str]:
    """Split text on blank lines into paragraphs, stripping extra whitespace."""
    paragraphs = re.split(r"\n\s*\n", text)
    result = []
    for p in paragraphs:
        stripped = p.strip()
        if stripped:
            result.append(stripped)
    return result


def split_into_chunks(file_name: str, text: str, *, page_num: int | None = None) -> list[Chunk]:
    if not text or not text.strip():
        return []

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Build ID prefix: include page number when processing per-page
    _id_prefix = f"{Path(file_name).stem}_p{page_num}" if page_num is not None else Path(file_name).stem

    # Plain text without markdown headers: split by paragraphs
    if not _has_markdown_headers(text):
        paragraphs = _split_paragraphs(text)
        chunks: list[Chunk] = []
        index = 0
        for para in paragraphs:
            if len(para) > _chunker.chunk_size:
                # Large paragraph: further split with recursive chunker
                for raw in _chunker(para):
                    section = _section_label(raw.text)
                    chunks.append(Chunk(
                        chunk_id=f"{_id_prefix}_chunk_{index}",
                        file_name=file_name,
                        text=raw.text,
                        section=section,
                        page=page_num,
                        metadata={},
                    ))
                    index += 1
            else:
                section = _section_label(para)
                chunks.append(Chunk(
                    chunk_id=f"{_id_prefix}_chunk_{index}",
                    file_name=file_name,
                    text=para,
                    section=section,
                    page=page_num,
                    metadata={},
                ))
                index += 1
        return chunks

    # Markdown text: use chonkie recursive chunker
    raw_chunks = _chunker(text)

    chunks = []
    for index, raw in enumerate(raw_chunks):
        section = _section_label(raw.text)
        # Use the explicit page_num when processing per-page;
        # otherwise try to find page number inside the chunk text itself,
        # or fall back to the last "# Page N" header before this
        # chunk's position in the original text.
        if page_num is not None:
            page = page_num
        else:
            page = _extract_page_from_chunk(raw.text)
            if page is None:
                page = _last_page_before(text, raw.start_index)
        chunks.append(Chunk(
            chunk_id=f"{_id_prefix}_chunk_{index}",
            file_name=file_name,
            text=raw.text,
            section=section,
            page=page,
            metadata={},
        ))

    return chunks
