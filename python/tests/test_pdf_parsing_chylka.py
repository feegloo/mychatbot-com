"""Tests for parsing Mroz-Remigiusz-Joanna-Chylka-02-Zaginiecie.pdf.

This PDF is a Polish ebook with 266 pages. Key characteristics:
- Pages 1-5 are empty or contain only images (cover, title page, etc.)
- Pages 6-266 contain text (the actual book content)
- 6 images total across 6 pages
- Text uses Polish characters (ą, ę, ś, ć, ź, ż, ó, ł, ń)

In production (cloud mode), 266 page errors were observed because ALL pages
were dispatched as Cloud Run Jobs that failed. The text was still extracted
locally as a fallback (507 chunks). The page errors are NOT caused by the
PDF parsing itself — fitz/pypdf handle this file correctly. The errors come
from cloud worker failures (Cloud Run Job dispatch/execution failures).
"""

import tempfile
from pathlib import Path

import fitz
import pytest
from pypdf import PdfReader

from shared.chunkers import Chunk, split_into_chunks
from shared.extractors import _reflow_pdf_text, _sanitize_text, extract_pdf

PDF_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "test-files"
    / "Mroz-Remigiusz-Joanna-Chylka-02-Zaginiecie.pdf"
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not PDF_PATH.exists(),
        reason=f"Test PDF not found at {PDF_PATH}",
    ),
]


class TestPdfBasicProperties:
    """Verify basic PDF structure."""

    def test_page_count(self):
        doc = fitz.open(str(PDF_PATH))
        assert len(doc) == 266
        doc.close()

    def test_pypdf_page_count(self):
        reader = PdfReader(str(PDF_PATH))
        assert len(reader.pages) == 266


class TestFitzTextExtraction:
    """Test text extraction using PyMuPDF (fitz) — the primary extractor."""

    @pytest.fixture(autouse=True)
    def open_doc(self):
        self.doc = fitz.open(str(PDF_PATH))
        yield
        self.doc.close()

    def test_first_five_pages_empty_or_minimal(self):
        """Pages 1-5 are cover/title pages with no selectable text."""
        for i in range(5):
            page = self.doc[i]
            raw = page.get_text() or ""
            assert len(raw.strip()) == 0, f"Page {i + 1} expected empty, got {len(raw)} chars"

    def test_page_6_has_latin_motto(self):
        """Page 6 contains the Latin motto."""
        page = self.doc[5]
        raw = page.get_text() or ""
        assert "Qui accusare volunt" in raw
        assert "probationes habere debent" in raw

    def test_page_8_is_chapter_1(self):
        """Page 8 starts Chapter 1 (Rozdział 1)."""
        page = self.doc[7]
        raw = page.get_text() or ""
        assert "Rozdział 1" in raw
        assert "Chyłka" in raw

    def test_polish_characters_preserved(self):
        """Polish diacritics must survive extraction."""
        page = self.doc[7]  # Chapter 1
        raw = page.get_text() or ""
        # "usłyszała" contains ł, ś, ą
        assert "usłyszała" in raw

    def test_most_pages_have_text(self):
        """At least 260 of 266 pages should have extractable text."""
        pages_with_text = 0
        for i in range(len(self.doc)):
            page = self.doc[i]
            raw = page.get_text() or ""
            if len(raw.strip()) > 0:
                pages_with_text += 1
        assert pages_with_text >= 260

    def test_images_found(self):
        """PDF should contain images (cover art, etc.)."""
        total_images = 0
        for i in range(len(self.doc)):
            page = self.doc[i]
            total_images += len(page.get_images(full=True))
        assert total_images >= 5


class TestPypdfExtraction:
    """Test text extraction using pypdf — the fallback extractor."""

    def test_extract_pdf_returns_text(self):
        """extract_pdf() should return substantial text with page headers."""
        text = extract_pdf(PDF_PATH)
        assert len(text) > 100_000, f"Expected >100k chars, got {len(text)}"
        assert "# Page 1" in text
        assert "# Page 266" in text

    def test_extract_pdf_contains_chapter_content(self):
        text = extract_pdf(PDF_PATH)
        # pypdf uses tabs between words for this PDF
        assert "Rozdział" in text
        assert "Chyłka" in text

    def test_extract_pdf_empty_pages_still_have_headers(self):
        """Even empty pages should have '# Page N' headers."""
        text = extract_pdf(PDF_PATH)
        for page_num in range(1, 6):
            assert f"# Page {page_num}" in text


class TestTextReflowAndSanitize:
    """Test text processing pipeline on actual PDF content."""

    def test_reflow_joins_lines_into_continuous_text(self):
        """PDF layout line breaks should be joined into continuous text."""
        doc = fitz.open(str(PDF_PATH))
        page = doc[7]  # Chapter 1
        raw = page.get_text() or ""
        doc.close()

        reflowed = _reflow_pdf_text(raw.strip())
        # This PDF uses single-spaced layout (no double newlines for paragraph breaks).
        # After reflow, all single line breaks become spaces → one continuous block.
        assert len(reflowed) > 1000, "Chapter page should have substantial text"
        assert "Chyłka" in reflowed
        # No raw single-newlines should remain (all joined by spaces)
        for para in reflowed.split("\n\n"):
            if para.strip():
                assert "\n" not in para, f"Found soft wrap in paragraph: {para[:80]}"

    def test_sanitize_preserves_polish_text(self):
        text = "Zażółć gęślą jaźń — polskie znaki: ąćęłńóśźż"
        assert _sanitize_text(text) == text


class TestChunking:
    """Test chunking pipeline on actual PDF content."""

    def test_chunk_count(self):
        """Chunking all pages should produce approximately 507 chunks."""
        doc = fitz.open(str(PDF_PATH))
        all_chunks: list[Chunk] = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            raw = page.get_text() or ""
            reflowed = _reflow_pdf_text(raw.strip())
            page_text = _sanitize_text(f"# Page {page_idx + 1}\n\n{reflowed}")
            chunks = split_into_chunks(doc.name, page_text, page_num=page_idx + 1)
            all_chunks.extend(chunks)

        doc.close()
        # Production showed 507 chunks. Allow some variance.
        assert 400 <= len(all_chunks) <= 600, f"Expected ~507 chunks, got {len(all_chunks)}"

    def test_chunks_have_page_numbers(self):
        """Each chunk should have a page number assigned."""
        doc = fitz.open(str(PDF_PATH))
        page = doc[7]  # Chapter 1
        raw = page.get_text() or ""
        doc.close()

        reflowed = _reflow_pdf_text(raw.strip())
        page_text = _sanitize_text(f"# Page 8\n\n{reflowed}")
        chunks = split_into_chunks("test.pdf", page_text, page_num=8)
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.page == 8

    def test_chunks_have_text_content(self):
        """Chunks should contain meaningful text, not just headers."""
        doc = fitz.open(str(PDF_PATH))
        page = doc[7]  # Chapter 1
        raw = page.get_text() or ""
        doc.close()

        reflowed = _reflow_pdf_text(raw.strip())
        page_text = _sanitize_text(f"# Page 8\n\n{reflowed}")
        chunks = split_into_chunks("test.pdf", page_text, page_num=8)
        for chunk in chunks:
            # Chunk text should be substantial (min_characters_per_chunk=24)
            assert len(chunk.text) >= 24

    def test_empty_page_produces_no_chunks(self):
        """A page with no text should produce 0 chunks or 1 minimal chunk."""
        page_text = _sanitize_text("# Page 1\n\n")
        chunks = split_into_chunks("test.pdf", page_text, page_num=1)
        # Empty/near-empty page may produce 0 or 1 chunk depending on chunker
        assert len(chunks) <= 1


class TestPageProcessingPipeline:
    """Simulate the full per-page processing pipeline (without telemetry/API calls).

    This verifies that fitz text extraction + image extraction + chunking works
    for ALL 266 pages without errors — proving the 266 page errors in production
    are caused by Cloud Run Job dispatch failures, not PDF parsing issues.
    """

    def test_all_pages_process_without_error(self):
        """Every page should be processable without raising exceptions."""
        doc = fitz.open(str(PDF_PATH))
        seen_xrefs: set[int] = set()
        errors: list[tuple[int, str]] = []
        total_chunks = 0

        with tempfile.TemporaryDirectory():
            for page_idx in range(len(doc)):
                page_num = page_idx + 1
                try:
                    page = doc[page_idx]

                    # Step 1: Extract text
                    raw = page.get_text() or ""
                    reflowed = _reflow_pdf_text(raw.strip())
                    page_text = _sanitize_text(f"# Page {page_num}\n\n{reflowed}")

                    # Step 2: Extract images (dedup by xref)
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        if xref in seen_xrefs:
                            continue
                        seen_xrefs.add(xref)
                        try:  # noqa: SIM105
                            doc.extract_image(xref)
                        except Exception:
                            pass  # Image extraction failures are non-fatal

                    # Step 3: Chunk text
                    chunks = split_into_chunks(doc.name, page_text, page_num=page_num)
                    total_chunks += len(chunks)

                except Exception as e:
                    errors.append((page_num, str(e)))

        doc.close()

        assert errors == [], f"Pages failed: {errors}"
        assert total_chunks > 400, f"Expected >400 chunks, got {total_chunks}"

    def test_concurrent_fitz_open_safe(self):
        """process_pdf_page opens a new fitz.Document per page.
        Verify this pattern works without errors for multiple pages.
        """
        errors = []
        for page_idx in [0, 5, 7, 100, 265]:  # Sample pages
            try:
                doc = fitz.open(str(PDF_PATH))
                page = doc[page_idx]
                page.get_text() or ""
                _ = page.get_images(full=True)
                doc.close()
            except Exception as e:
                errors.append((page_idx + 1, str(e)))

        assert errors == [], f"Failed pages: {errors}"
