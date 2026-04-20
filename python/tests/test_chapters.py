"""Tests for chapter detection in PDF documents."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.chapters import (
    ChapterInfo,
    build_page_to_chapter_map,
    chapters_from_serializable,
    chapters_to_serializable,
    detect_chapters,
    detect_chapters_from_text,
    detect_chapters_from_toc,
)

# ── Real PDF tests (Mroz-Remigiusz-Joanna-Chylka) ─────────────────

PDF_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "test-files"
    / "Mroz-Remigiusz-Joanna-Chylka-02-Zaginiecie.pdf"
)

pytestmark_real_pdf = pytest.mark.skipif(
    not PDF_PATH.exists(),
    reason=f"Test PDF not found at {PDF_PATH}",
)


@pytestmark_real_pdf
class TestChapterDetectionWithRealPdf:
    """Test chapter detection against the Mroz Chylka PDF (266 pages, 4 chapters)."""

    def test_detect_chapters_from_toc(self):
        chapters = detect_chapters_from_toc(str(PDF_PATH))
        assert len(chapters) == 4
        assert chapters[0].number == 1
        assert chapters[0].title == "Rozdział 1"
        assert chapters[0].start_page == 8
        assert chapters[1].number == 2
        assert chapters[1].start_page == 73
        assert chapters[2].number == 3
        assert chapters[2].start_page == 154
        assert chapters[3].number == 4
        assert chapters[3].start_page == 202

    def test_chapter_end_pages(self):
        chapters = detect_chapters_from_toc(str(PDF_PATH))
        # Chapter 1 ends before chapter 2 starts
        assert chapters[0].end_page == 72
        # Chapter 2 ends before chapter 3 starts
        assert chapters[1].end_page == 153
        # Chapter 4 goes to end of book (266 pages)
        assert chapters[3].end_page == 266

    def test_detect_chapters_unified(self):
        """detect_chapters() should prefer TOC over text-based detection."""
        chapters = detect_chapters(str(PDF_PATH))
        assert len(chapters) == 4
        assert all(isinstance(ch, ChapterInfo) for ch in chapters)

    def test_page_to_chapter_map(self):
        chapters = detect_chapters(str(PDF_PATH))
        page_map = build_page_to_chapter_map(chapters)
        # Pages before chapter 1 should not be in the map
        assert 1 not in page_map
        assert 7 not in page_map
        # Chapter 1 pages
        assert page_map[8] == 1
        assert page_map[50] == 1
        assert page_map[72] == 1
        # Chapter 2 pages
        assert page_map[73] == 2
        assert page_map[100] == 2
        # Chapter 3 pages
        assert page_map[154] == 3
        # Chapter 4 pages
        assert page_map[202] == 4
        assert page_map[266] == 4


# ── Unit tests with mocked PDFs ───────────────────────────────────


class TestChapterDetectionMocked:
    """Test chapter detection logic with mocked fitz."""

    def test_detect_chapters_from_toc_with_chapters(self):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=100)
        mock_doc.get_toc.return_value = [
            [1, "Chapter 1", 5],
            [2, "Section 1.1", 5],
            [2, "Section 1.2", 15],
            [1, "Chapter 2", 30],
            [2, "Section 2.1", 30],
            [1, "Chapter 3", 60],
        ]

        # Mock pages so _extract_chapter_name_from_page can read text
        def make_page(text="Some regular text\n"):
            p = MagicMock()
            p.get_text.return_value = text
            return p

        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: make_page())

        with patch("shared.chapters.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            chapters = detect_chapters_from_toc("fake.pdf")

        assert len(chapters) == 3
        assert chapters[0].number == 1
        assert chapters[0].title == "Chapter 1"
        assert chapters[0].start_page == 5
        assert chapters[0].end_page == 29
        assert chapters[1].number == 2
        assert chapters[1].start_page == 30
        assert chapters[1].end_page == 59
        assert chapters[2].number == 3
        assert chapters[2].start_page == 60
        assert chapters[2].end_page == 100

    def test_detect_chapters_from_toc_empty(self):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=50)
        mock_doc.get_toc.return_value = []

        with patch("shared.chapters.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            chapters = detect_chapters_from_toc("fake.pdf")

        assert chapters == []

    def test_detect_chapters_from_toc_polish(self):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=200)
        mock_doc.get_toc.return_value = [
            [1, "Rozdział 1", 10],
            [1, "Rozdział 2", 50],
            [1, "Posłowie", 180],  # non-chapter entry
        ]

        def make_page(text="Some regular text\n"):
            p = MagicMock()
            p.get_text.return_value = text
            return p

        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: make_page())

        with patch("shared.chapters.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            chapters = detect_chapters_from_toc("fake.pdf")

        assert len(chapters) == 2
        assert chapters[0].title == "Rozdział 1"
        assert chapters[1].title == "Rozdział 2"
        assert chapters[1].end_page == 200

    def test_detect_chapters_from_text(self):
        """Test text-based fallback detection."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=80)

        # Create mock pages with chapter headings
        pages_text = {
            0: "Some introduction text",
            4: "Rozdział 1\n\nThis is chapter one content",
            29: "Rozdział 2\n\nSecond chapter begins here",
            59: "Chapter 3\n\nThird chapter in English",
        }
        mock_pages = []
        for i in range(80):
            page = MagicMock()
            page.get_text.return_value = pages_text.get(i, "Regular page text")
            mock_pages.append(page)
        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: mock_pages[i])
        mock_doc.__iter__ = MagicMock(return_value=iter(range(80)))

        with patch("shared.chapters.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            chapters = detect_chapters_from_text("fake.pdf")

        assert len(chapters) == 3
        assert chapters[0].number == 1
        assert chapters[0].start_page == 5  # page_idx 4 + 1
        assert chapters[1].number == 2
        assert chapters[1].start_page == 30
        assert chapters[2].number == 3
        assert chapters[2].start_page == 60
        assert chapters[2].end_page == 80

    def test_no_chapters_detected(self):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=10)
        mock_doc.get_toc.return_value = []

        mock_pages = []
        for _i in range(10):
            page = MagicMock()
            page.get_text.return_value = "Just regular text without chapter markers"
            mock_pages.append(page)
        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: mock_pages[i])

        with patch("shared.chapters.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            chapters = detect_chapters("fake.pdf")

        assert chapters == []


class TestBuildPageToChapterMap:
    def test_basic_mapping(self):
        chapters = [
            ChapterInfo(number=1, title="Ch 1", start_page=5, end_page=10),
            ChapterInfo(number=2, title="Ch 2", start_page=11, end_page=20),
        ]
        page_map = build_page_to_chapter_map(chapters)
        assert page_map[5] == 1
        assert page_map[10] == 1
        assert page_map[11] == 2
        assert page_map[20] == 2
        assert 4 not in page_map
        assert 21 not in page_map

    def test_empty_chapters(self):
        assert build_page_to_chapter_map([]) == {}


class TestSerialization:
    def test_roundtrip(self):
        chapters = [
            ChapterInfo(number=1, title="Rozdział 1", start_page=8, end_page=72, chapter_name="Jan"),
            ChapterInfo(number=2, title="Rozdział 2", start_page=73, end_page=153),
        ]
        serialized = chapters_to_serializable(chapters)
        assert isinstance(serialized, list)
        assert serialized[0]["number"] == 1
        assert serialized[0]["title"] == "Rozdział 1"
        assert serialized[0]["chapter_name"] == "Jan"
        assert serialized[1]["chapter_name"] == ""

        restored = chapters_from_serializable(serialized)
        assert restored == chapters
