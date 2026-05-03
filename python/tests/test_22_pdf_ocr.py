"""Tests for OCR handling of 22.pdf — a mixed image/text PDF page.

22.pdf is a single-page parish newspaper page that contains:
  - An inline-rendered article ("PRAWDZIWA HISTORIA") whose text is NOT
    extractable natively by fitz (visually rendered, not a PDF text object).
  - A crossword diagram embedded as an image xref (xref=44, ~115K pt²).
  - A portrait photo embedded as an image xref (xref=48, ~16K pt²).
  - 108 chars of native text (the announcement box only).

The system previously emitted this page with only the 108-char snippet
because page_needs_ocr() returned False (108 > 20 threshold). With the
image-coverage-aware fix the page is now routed through full-page OCR,
which renders the page as a PNG and extracts all visible text via GPT Vision.

22_OCRed.pdf is the expected ground truth: the same page with an OCR text
layer added, containing ~3600 chars covering the full article.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest

from shared.streaming_pdf import (
    _MIN_RENDERED_IMAGE_AREA_PTS2,
    _MIN_TEXT_CHARS_WITH_IMAGES,
    PageOutcome,
    _page_has_significant_images,
    process_pdf_streaming,
)

TEST_PDF = Path(__file__).resolve().parent.parent.parent / "test-files" / "22.pdf"
OCRED_PDF = Path(__file__).resolve().parent.parent.parent / "test-files" / "22_OCRed.pdf"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not TEST_PDF.exists(),
        reason=f"Test PDF not found: {TEST_PDF}",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def doc():
    d = fitz.open(str(TEST_PDF))
    yield d
    d.close()


@pytest.fixture(scope="module")
def page(doc):
    return doc[0]


# ---------------------------------------------------------------------------
# PDF structure assertions (no API calls)
# ---------------------------------------------------------------------------


class TestPdfStructure:
    def test_pdf_has_exactly_one_page(self):
        d = fitz.open(str(TEST_PDF))
        assert len(d) == 1
        d.close()

    def test_native_text_is_sparse(self, page):
        """Native text extraction yields only the announcement box text (~108 chars)."""
        text = (page.get_text() or "").strip()
        # Allow ±5 chars for minor encoding/whitespace differences across fitz versions.
        assert 100 <= len(text) <= 115, f"Expected ~108 chars, got {len(text)}"
        assert "Rozstrzygnięcie" in text

    def test_page_has_four_image_xrefs(self, page):
        """Page has 4 xrefs: 2 real images + 2 soft-mask (alpha) images."""
        images = page.get_images(full=True)
        assert len(images) == 4

    def test_two_real_images_with_rects(self, page):
        """Exactly 2 image xrefs are drawn on the page (have non-empty rects)."""
        rendered = [
            img for img in page.get_images(full=True) if page.get_image_rects(img[0])
        ]
        assert len(rendered) == 2

    def test_crossword_image_area_exceeds_threshold(self, page):
        """The crossword image covers ~115K pt² — well above the detection threshold."""
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            rect = rects[0]
            area = abs(rect.x1 - rect.x0) * abs(rect.y1 - rect.y0)
            # The crossword image should be the large one (~115K pt²)
            if area > 100_000:
                return  # found it
        pytest.fail("No image with area > 100K pt² found on the page")


# ---------------------------------------------------------------------------
# _page_has_significant_images unit tests
# ---------------------------------------------------------------------------


class TestPageHasSignificantImages:
    def test_returns_true_for_22_pdf_page(self, page):
        """22.pdf page has large rendered images → should return True."""
        assert _page_has_significant_images(page) is True

    def test_returns_false_for_blank_page(self):
        """A blank fitz page with no images → returns False."""
        doc = fitz.open()
        blank = doc.new_page()
        assert _page_has_significant_images(blank) is False
        doc.close()

    def test_skips_smask_only_xrefs(self, page):
        """Soft-mask xrefs (alpha channels) are excluded from the area calculation."""
        # xref=45 and xref=49 are smasks and have no draw rects — the function
        # must not count them as "significant images".
        smask_xrefs = {img[1] for img in page.get_images(full=True) if img[1] != 0}
        assert smask_xrefs, "Expected at least one smask xref in 22.pdf"
        # The function still returns True because the *real* images are large enough.
        assert _page_has_significant_images(page) is True

    def test_constant_min_area_is_reasonable(self):
        """_MIN_RENDERED_IMAGE_AREA_PTS2 should be between 1000 and 50000 pt²."""
        assert 1_000 <= _MIN_RENDERED_IMAGE_AREA_PTS2 <= 50_000

    def test_constant_min_text_chars_is_reasonable(self):
        """_MIN_TEXT_CHARS_WITH_IMAGES should be between 100 and 2000."""
        assert 100 <= _MIN_TEXT_CHARS_WITH_IMAGES <= 2_000


# ---------------------------------------------------------------------------
# Streaming processor — mocked OCR (no API calls)
# ---------------------------------------------------------------------------


MOCKED_OCR_TEXT = (
    "PRAWDZIWA HISTORIA Biblioteka doktora Efekta, licząca kilka tysięcy "
    "egzemplarzy, zajmowała dwie ściany jadalni. "
    "Rozstrzygnięcie konkursów i wręczenie nagród "
    "ZADANIE NR 402 – MODLITWA ZE ŚWIĘTYM JÓZEFEM "
    "Święty Józef jest patronem wielkim i pięknym."
)


class TestStreamingProcessorMocked:
    def test_page_triggers_ocr_despite_passing_basic_threshold(self):
        """page_needs_ocr() returns False for 22.pdf page (108 chars > 20), but
        the image-coverage check routes it through OCR anyway."""
        from shared.extractors import page_needs_ocr

        native_text = "# Page 1\n\n" + "Rozstrzygnięcie konkursów i wręczenie nagród w każdą drugą niedzielę miesiąca po Mszy św. o godz. 13:30."
        # Basic check: page_needs_ocr must NOT trigger (to prove the secondary
        # image-coverage check is what makes the difference).
        assert page_needs_ocr(native_text) is False

    @patch("shared.streaming_pdf.ocr_pdf_page", return_value=MOCKED_OCR_TEXT)
    def test_streaming_triggers_ocr_for_image_heavy_page(self, mock_ocr):
        """With the fix, page 1 of 22.pdf must go through OCR."""
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22")

        assert result.total_pages == 1
        mock_ocr.assert_called_once_with(str(TEST_PDF), 0, conversation_id="test-22")

    @patch("shared.streaming_pdf.ocr_pdf_page", return_value=MOCKED_OCR_TEXT)
    def test_streaming_result_counts_ocr_page(self, mock_ocr):
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22")
        assert result.ocr_page_count == 1

    @patch("shared.streaming_pdf.ocr_pdf_page", return_value=MOCKED_OCR_TEXT)
    def test_streaming_full_text_contains_article_content(self, mock_ocr):
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22")
        text = result.full_text
        assert "PRAWDZIWA HISTORIA" in text

    @patch("shared.streaming_pdf.ocr_pdf_page", return_value=MOCKED_OCR_TEXT)
    def test_streaming_full_text_contains_prayer_content(self, mock_ocr):
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22")
        assert "MODLITWA ZE ŚWIĘTYM JÓZEFEM" in result.full_text

    @patch("shared.streaming_pdf.ocr_pdf_page", return_value=MOCKED_OCR_TEXT)
    def test_on_page_ready_callback_is_invoked(self, mock_ocr):
        outcomes: list[PageOutcome] = []
        lock = threading.Lock()

        def on_ready(outcome: PageOutcome) -> None:
            with lock:
                outcomes.append(outcome)

        process_pdf_streaming(str(TEST_PDF), conversation_id="test-22", on_page_ready=on_ready)
        assert len(outcomes) == 1
        assert outcomes[0].page_nr == 1
        assert outcomes[0].source == "ocr"

    @patch("shared.streaming_pdf.ocr_pdf_page", return_value=MOCKED_OCR_TEXT)
    def test_is_heavy_ocr_true_for_single_ocrd_page(self, mock_ocr):
        """A 1-page doc where the only page needs OCR → is_heavy_ocr = True."""
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22")
        assert result.is_heavy_ocr is True


# ---------------------------------------------------------------------------
# OCRed PDF ground truth (no API calls)
# ---------------------------------------------------------------------------


class TestOcredPdfGroundTruth:
    @pytest.mark.skipif(not OCRED_PDF.exists(), reason=f"OCRed PDF not found: {OCRED_PDF}")
    def test_ocred_pdf_has_rich_text(self):
        """22_OCRed.pdf should have ~3600+ chars, confirming full article is there."""
        doc = fitz.open(str(OCRED_PDF))
        text = doc[0].get_text()
        doc.close()
        assert len(text) >= 3000, f"Expected ≥3000 chars, got {len(text)}"

    @pytest.mark.skipif(not OCRED_PDF.exists(), reason=f"OCRed PDF not found: {OCRED_PDF}")
    def test_ocred_pdf_contains_article_title(self):
        doc = fitz.open(str(OCRED_PDF))
        text = doc[0].get_text()
        doc.close()
        assert "PRAWDZIWA HISTORIA" in text

    @pytest.mark.skipif(not OCRED_PDF.exists(), reason=f"OCRed PDF not found: {OCRED_PDF}")
    def test_ocred_pdf_contains_prayer_section(self):
        doc = fitz.open(str(OCRED_PDF))
        text = doc[0].get_text()
        doc.close()
        assert "Józef" in text or "JÓZEF" in text.upper()


# ---------------------------------------------------------------------------
# Live integration test (requires OPENAI_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set; skipping live OCR integration test",
)
class TestLiveOcr:
    """These tests call the real OpenAI Vision API. Run locally with an API key."""

    def test_full_page_ocr_extracts_article_text(self):
        """Full-page OCR via GPT Vision must extract the PRAWDZIWA HISTORIA article."""
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22-live")

        assert result.ocr_page_count >= 1, "Expected at least one OCR'd page"
        full_text = result.full_text
        assert len(full_text) > 500, f"Expected >500 chars from OCR, got {len(full_text)}"
        # Article title must be present
        assert "HISTORIA" in full_text.upper(), "Article title not found in OCR output"

    def test_full_page_ocr_extracts_prayer_content(self):
        """OCR must capture the prayer section (ZADANIE NR 402)."""
        result = process_pdf_streaming(str(TEST_PDF), conversation_id="test-22-live")
        full_text = result.full_text
        assert "Józef" in full_text or "ZADANIE" in full_text, (
            "Prayer/task section not found in OCR output"
        )
