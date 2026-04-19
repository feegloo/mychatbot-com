"""Chapter detection for PDF documents.

Extracts chapter structure from PDFs using two strategies:
1. PDF TOC bookmarks (fitz.Document.get_toc()) — most reliable
2. Text-based pattern matching — fallback for PDFs without bookmarks

Supports Polish (Rozdział) and English (Chapter) chapter naming conventions,
plus "Spis treści" / "Table of Contents" parsing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)


@dataclass
class ChapterInfo:
    """A detected chapter with its page range."""

    number: int
    title: str
    start_page: int
    end_page: int  # inclusive


# Patterns for text-based chapter detection (case-insensitive)
_CHAPTER_TEXT_RE = re.compile(
    r"^\s*(?:Rozdzia[lł]|Chapter|ROZDZIA[LŁ]|CHAPTER)\s+(\d+)",
    re.IGNORECASE | re.MULTILINE,
)


def detect_chapters_from_toc(pdf_path: str) -> list[ChapterInfo]:
    """Extract chapter structure from PDF bookmarks/TOC.

    Uses fitz.Document.get_toc() which reads the PDF outline.
    Only level-1 TOC entries matching chapter patterns are treated as chapters.
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    toc = doc.get_toc()
    doc.close()

    if not toc:
        return []

    # Filter to level-1 entries that look like chapters
    chapter_re = re.compile(
        r"^(?:Rozdzia[lł]|Chapter|ROZDZIA[LŁ]|CHAPTER)\s+(\d+)",
        re.IGNORECASE,
    )

    raw_chapters: list[tuple[int, str, int]] = []  # (number, title, start_page)
    for level, title, page in toc:
        if level != 1:
            continue
        m = chapter_re.match(title.strip())
        if m:
            raw_chapters.append((int(m.group(1)), title.strip(), page))

    if not raw_chapters:
        return []

    # Compute end_page for each chapter (page before next chapter starts, or last page)
    chapters: list[ChapterInfo] = []
    for i, (number, title, start_page) in enumerate(raw_chapters):
        end_page = raw_chapters[i + 1][2] - 1 if i + 1 < len(raw_chapters) else total_pages
        chapters.append(
            ChapterInfo(
                number=number,
                title=title,
                start_page=start_page,
                end_page=end_page,
            )
        )

    logger.info(
        f"📖 Detected {len(chapters)} chapters from TOC in {Path(pdf_path).name}"
    )
    return chapters


def detect_chapters_from_text(pdf_path: str) -> list[ChapterInfo]:
    """Detect chapters by scanning page text for chapter heading patterns.

    Fallback for PDFs without TOC bookmarks. Looks for lines like:
    "Rozdział 1", "Chapter 2", "CHAPTER 3", etc.
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    raw_chapters: list[tuple[int, str, int]] = []  # (number, title, page_num)
    for page_idx in range(total_pages):
        text = doc[page_idx].get_text()
        for m in _CHAPTER_TEXT_RE.finditer(text):
            chapter_num = int(m.group(1))
            title = m.group(0).strip()
            page_num = page_idx + 1
            # Avoid duplicate detections of the same chapter
            if not any(c[0] == chapter_num for c in raw_chapters):
                raw_chapters.append((chapter_num, title, page_num))

    doc.close()

    if not raw_chapters:
        return []

    # Sort by page number to ensure correct ordering
    raw_chapters.sort(key=lambda c: c[2])

    chapters: list[ChapterInfo] = []
    for i, (number, title, start_page) in enumerate(raw_chapters):
        end_page = raw_chapters[i + 1][2] - 1 if i + 1 < len(raw_chapters) else total_pages
        chapters.append(
            ChapterInfo(
                number=number,
                title=title,
                start_page=start_page,
                end_page=end_page,
            )
        )

    logger.info(
        f"📖 Detected {len(chapters)} chapters from text in {Path(pdf_path).name}"
    )
    return chapters


def detect_chapters(pdf_path: str) -> list[ChapterInfo]:
    """Detect chapters using TOC first, falling back to text-based detection.

    Returns empty list if no chapters found.
    """
    # Strategy 1: PDF TOC bookmarks (most reliable)
    chapters = detect_chapters_from_toc(pdf_path)
    if chapters:
        return chapters

    # Strategy 2: Text-based pattern matching
    chapters = detect_chapters_from_text(pdf_path)
    if chapters:
        return chapters

    logger.info(f"📖 No chapters detected in {Path(pdf_path).name}")
    return []


def build_page_to_chapter_map(chapters: list[ChapterInfo]) -> dict[int, int]:
    """Build a mapping from page number to chapter number.

    Returns {page_number: chapter_number} for all pages that belong to a chapter.
    Pages before the first chapter or after the last are not included.
    """
    page_map: dict[int, int] = {}
    for ch in chapters:
        for page in range(ch.start_page, ch.end_page + 1):
            page_map[page] = ch.number
    return page_map


def chapters_to_serializable(chapters: list[ChapterInfo]) -> list[dict]:
    """Convert ChapterInfo list to JSON-serializable format."""
    return [
        {
            "number": ch.number,
            "title": ch.title,
            "start_page": ch.start_page,
            "end_page": ch.end_page,
        }
        for ch in chapters
    ]


def chapters_from_serializable(data: list[dict]) -> list[ChapterInfo]:
    """Reconstruct ChapterInfo list from JSON data."""
    return [
        ChapterInfo(
            number=d["number"],
            title=d["title"],
            start_page=d["start_page"],
            end_page=d["end_page"],
        )
        for d in data
    ]
