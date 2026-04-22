"""Tests for _ocr_prefetch_welcome – OCR-first welcome strategy for scanned PDFs.

Verifies that:
- Scanned PDFs (low word count from native extraction) trigger the OCR-prefetch path
- Pages are OCR-ed in parallel and combined into a welcome prompt
- If OCR yields too little text the function returns None gracefully
- Single-page PDFs are skipped (handled by regular path)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import fitz
import pytest

from shared.indexing import _ocr_prefetch_welcome


def _create_image_pdf(tmp_path: Path, num_pages: int) -> str:
    """Create a multi-page PDF with NO embedded text (simulates a scanned book)."""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page(width=400, height=600)
    pdf_path = str(tmp_path / "scanned.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


_DUMMY_FILE_METADATA: dict = {}
_DUMMY_FILE_NAMES = ["scanned.pdf"]
_DUMMY_FILE_TYPES = {"scanned.pdf": "pdf"}

_WELCOME_RESPONSE = "This is a scanned Arabic book about poetry."


def _make_mock_llm():
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    def _invoke(messages, **kwargs):
        return AIMessage(content=_WELCOME_RESPONSE)

    return RunnableLambda(_invoke)


class TestOcrPrefetchWelcome:
    @patch("shared.indexing.describe_documents")
    @patch("shared.indexing.ocr_pdf_page")
    @patch("shared.indexing.detect_language", return_value="ar")
    def test_ocrs_first_pages_in_parallel(
        self, _mock_lang, mock_ocr, mock_describe, tmp_path
    ):
        """OCR is called for each of the first N pages and combined into one doc."""
        mock_ocr.side_effect = lambda path, idx, **kwargs: f"Arabic text on page {idx + 1} " * 5
        mock_describe.return_value = {
            "welcome_message": _WELCOME_RESPONSE,
            "suggested_questions": [],
        }

        pdf_path = _create_image_pdf(tmp_path, 10)
        result = _ocr_prefetch_welcome(
            pdf_path, _DUMMY_FILE_METADATA, _DUMMY_FILE_NAMES, _DUMMY_FILE_TYPES
        )

        assert result is not None
        assert mock_ocr.call_count == 10  # All 10 pages OCR-ed (< _OCR_PREFETCH_PAGES)

        # describe_documents should be called once with combined text
        assert mock_describe.call_count == 1
        extracted = mock_describe.call_args[0][0]
        assert len(extracted) == 1
        assert "# Page 1" in extracted[0]["text"]
        assert "# Page 10" in extracted[0]["text"]

    @patch("shared.indexing.describe_documents")
    @patch("shared.indexing.ocr_pdf_page")
    @patch("shared.indexing.detect_language", return_value="ar")
    def test_caps_at_ocr_prefetch_pages_limit(
        self, _mock_lang, mock_ocr, mock_describe, tmp_path
    ):
        """Only first _OCR_PREFETCH_PAGES pages are OCR-ed for large scanned books."""
        from shared.indexing import _OCR_PREFETCH_PAGES

        mock_ocr.side_effect = lambda path, idx, **kwargs: f"Page {idx + 1} text " * 20
        mock_describe.return_value = {
            "welcome_message": _WELCOME_RESPONSE,
            "suggested_questions": [],
        }

        large_page_count = _OCR_PREFETCH_PAGES + 50
        pdf_path = _create_image_pdf(tmp_path, large_page_count)
        _ocr_prefetch_welcome(
            pdf_path, _DUMMY_FILE_METADATA, _DUMMY_FILE_NAMES, _DUMMY_FILE_TYPES
        )

        assert mock_ocr.call_count == _OCR_PREFETCH_PAGES

    @patch("shared.indexing.describe_documents")
    @patch("shared.indexing.ocr_pdf_page", return_value="x")  # 1 char — below threshold
    @patch("shared.indexing.detect_language", return_value="ar")
    def test_returns_none_when_ocr_yields_too_little_text(
        self, _mock_lang, mock_ocr, mock_describe, tmp_path
    ):
        """If average OCR chars/page < threshold, skip welcome (don't call LLM)."""
        pdf_path = _create_image_pdf(tmp_path, 5)
        result = _ocr_prefetch_welcome(
            pdf_path, _DUMMY_FILE_METADATA, _DUMMY_FILE_NAMES, _DUMMY_FILE_TYPES
        )

        assert result is None
        mock_describe.assert_not_called()

    def test_single_page_pdf_returns_none(self, tmp_path):
        """Single-page PDFs skip OCR prefetch (handled by regular describe path)."""
        pdf_path = _create_image_pdf(tmp_path, 1)
        result = _ocr_prefetch_welcome(
            pdf_path, _DUMMY_FILE_METADATA, _DUMMY_FILE_NAMES, _DUMMY_FILE_TYPES
        )
        assert result is None

    @patch("shared.indexing.describe_documents")
    @patch("shared.indexing.detect_language", return_value="ar")
    def test_failed_ocr_pages_are_skipped_gracefully(
        self, _mock_lang, mock_describe, tmp_path
    ):
        """Pages that raise during OCR contribute empty string, not crash the whole run."""
        mock_describe.return_value = {
            "welcome_message": _WELCOME_RESPONSE,
            "suggested_questions": [],
        }

        call_count = 0

        def flaky_ocr(path, idx, **kwargs):
            nonlocal call_count
            call_count += 1
            if idx % 2 == 0:
                raise RuntimeError("Tesseract failed")
            return f"Good text on page {idx + 1} " * 10  # enough chars for odd pages

        with patch("shared.indexing.ocr_pdf_page", side_effect=flaky_ocr):
            pdf_path = _create_image_pdf(tmp_path, 6)
            result = _ocr_prefetch_welcome(
                pdf_path, _DUMMY_FILE_METADATA, _DUMMY_FILE_NAMES, _DUMMY_FILE_TYPES
            )

        # Even with half the pages failing, the successful ones should produce a welcome
        # (assuming total chars still exceed threshold)
        # 3 odd pages × ~130 chars each ÷ 6 pages = ~65 avg > _OCR_MIN_CHARS_PER_PAGE(50)
        assert result is not None
        assert mock_describe.call_count == 1

    @patch("shared.indexing.describe_documents")
    @patch("shared.indexing.ocr_pdf_page")
    @patch("shared.indexing.detect_language", return_value="ar")
    def test_language_is_detected_from_ocr_text(
        self, mock_lang, mock_ocr, mock_describe, tmp_path
    ):
        """Language detection is called with the combined OCR text."""
        mock_ocr.side_effect = lambda path, idx, **kwargs: "النص العربي على الصفحة " * 20
        mock_describe.return_value = {
            "welcome_message": _WELCOME_RESPONSE,
            "suggested_questions": [],
        }

        pdf_path = _create_image_pdf(tmp_path, 3)
        _ocr_prefetch_welcome(
            pdf_path, _DUMMY_FILE_METADATA, _DUMMY_FILE_NAMES, _DUMMY_FILE_TYPES
        )

        mock_lang.assert_called_once()
        # Language passed to describe_documents
        assert mock_describe.call_args[1]["language"] == "ar"
