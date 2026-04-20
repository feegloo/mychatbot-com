"""Chapter detection for PDF documents.

Extracts chapter structure from PDFs using multiple strategies:
1. PDF TOC bookmarks (fitz.Document.get_toc()) — most reliable
2. Enhanced TOC extraction with chapter name detection from page content
3. Text-based pattern matching — fallback for PDFs without bookmarks

Supports Polish (Rozdział) and English (Chapter) chapter naming conventions,
plus "Spis treści" / "Table of Contents" parsing.
Also detects POV character names (e.g. TYRION, DAENERYS) from chapter pages.
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
    chapter_name: str = ""  # extracted name/subtitle (e.g. POV character name)


# Patterns for text-based chapter detection (case-insensitive)
_CHAPTER_TEXT_RE = re.compile(
    r"^\s*(?:Rozdzia[lł]|Chapter|ROZDZIA[LŁ]|CHAPTER)\s+(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

# Pattern for numbered chapter in TOC
_CHAPTER_TOC_RE = re.compile(
    r"^(?:Rozdzia[lł]|Chapter|ROZDZIA[LŁ]|CHAPTER)\s+(\d+)",
    re.IGNORECASE,
)

# Special TOC entries that are chapter-like (Prologue, Epilogue, etc.)
_SPECIAL_CHAPTER_RE = re.compile(
    r"^(?:Prolog(?:ue)?|Epilog(?:ue)?|Introduction|Wstęp|Zakończenie|Afterword|Foreword|Preface)$",
    re.IGNORECASE,
)

# Pattern to detect POV character name at the top of a chapter page
# Matches 1-3 uppercase words at the very start of the page
# Includes Polish diacritics and common punctuation (apostrophes, hyphens)
_POV_NAME_RE = re.compile(
    r"^\s*([A-Z][A-Z\s\u0104\u0106\u0118\u0141\u0143\u00D3\u015A\u0179\u017B'\u2018\u2019'-]{1,50})\s*\n",
)


def _extract_chapter_name_from_page(doc: fitz.Document, page_idx: int) -> str:
    """Try to extract a chapter name/subtitle from the first lines of a page.

    In many novels (e.g. ASOIAF), each chapter starts with a character name
    in all-caps (TYRION, DAENERYS, JON). This function extracts that name.
    """
    if page_idx < 0 or page_idx >= len(doc):
        return ""

    text = doc[page_idx].get_text()
    if not text:
        return ""

    m = _POV_NAME_RE.match(text)
    if m:
        name = m.group(1).strip()
        # Reject if it's too short or looks like a page marker
        if len(name) >= 2 and not name.isdigit():
            return name.title()

    return ""


def detect_chapters_from_toc(pdf_path: str) -> list[ChapterInfo]:
    """Extract chapter structure from PDF bookmarks/TOC.

    Uses fitz.Document.get_toc() which reads the PDF outline.
    Level-1 TOC entries matching chapter patterns are treated as chapters.
    Also detects Prologue/Epilogue and extracts POV character names from pages.
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    toc = doc.get_toc()

    if not toc:
        doc.close()
        return []

    # Collect all chapter-like entries: numbered chapters + special entries
    raw_chapters: list[tuple[int, str, int]] = []  # (number, title, start_page)
    prologue_number = 0  # Prologue gets number 0
    next_number = 1

    for level, title, page in toc:
        if level != 1:
            continue

        title_stripped = title.strip()
        m = _CHAPTER_TOC_RE.match(title_stripped)
        if m:
            raw_chapters.append((int(m.group(1)), title_stripped, page))
            next_number = max(next_number, int(m.group(1)) + 1)
        elif _SPECIAL_CHAPTER_RE.match(title_stripped):
            if title_stripped.lower().startswith(("prolog", "wstęp", "introduction", "foreword", "preface")):
                raw_chapters.append((prologue_number, title_stripped, page))
                prologue_number -= 1  # Handle multiple prologues
            else:
                raw_chapters.append((next_number, title_stripped, page))
                next_number += 1

    if not raw_chapters:
        doc.close()
        return []

    # Sort by page to ensure correct ordering
    raw_chapters.sort(key=lambda c: c[2])

    # Compute end_page and extract chapter names from page content
    chapters: list[ChapterInfo] = []
    for i, (number, title, start_page) in enumerate(raw_chapters):
        end_page = raw_chapters[i + 1][2] - 1 if i + 1 < len(raw_chapters) else total_pages

        # Try to extract a chapter name from the first page
        chapter_name = _extract_chapter_name_from_page(doc, start_page - 1)

        chapters.append(
            ChapterInfo(
                number=number,
                title=title,
                start_page=start_page,
                end_page=end_page,
                chapter_name=chapter_name,
            )
        )

    doc.close()

    logger.info(
        f"📖 Detected {len(chapters)} chapters from TOC in {Path(pdf_path).name}"
        + (f" (with names: {sum(1 for c in chapters if c.chapter_name)}/{len(chapters)})"
           if any(c.chapter_name for c in chapters) else "")
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
            "chapter_name": ch.chapter_name,
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
            chapter_name=d.get("chapter_name", ""),
        )
        for d in data
    ]
