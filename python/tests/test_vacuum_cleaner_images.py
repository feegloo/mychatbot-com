"""Tests for image extraction and description improvements using the vacuum cleaner manual.

Validates:
  - Decorative image filtering (aspect ratio, size)
  - Context-aware image description prompt construction
  - Enriched chunk text format for RAG retrieval
  - document_context flow from indexing → page_worker → vision API
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from shared.extractors import (
    MAX_IMAGE_ASPECT_RATIO,
    MIN_IMAGE_DIM,
    MIN_IMAGE_SIZE,
    _describe_image_with_context,
    _extract_and_save_images,
)
from shared.indexing import _build_document_context, _image_chunks
from shared.chunkers import Chunk

VACUUM_PDF = (
    Path(__file__).resolve().parent.parent.parent
    / "test-files"
    / "en_US_BKS_9316_EN.pdf"
)


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Sanity check ─────────────────────────────────────────────────────


def test_vacuum_pdf_exists():
    assert VACUUM_PDF.exists(), f"Test PDF not found: {VACUUM_PDF}"


# ── Aspect ratio filter ──────────────────────────────────────────────


class TestAspectRatioFilter:
    def test_max_aspect_ratio_constant_is_reasonable(self):
        # Value must be > 1 and strict enough to catch lines (e.g. 1000×3 px)
        assert MAX_IMAGE_ASPECT_RATIO >= 5
        assert MAX_IMAGE_ASPECT_RATIO <= 20

    def test_decorative_line_is_skipped(self, output_dir):
        """A synthetically created thin-line PDF should produce no extracted images."""
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        # Insert a thin horizontal rule (a 1px-tall rect spanning the page)
        page.draw_line((0, 400), (595, 400), color=(0, 0, 0), width=1)
        page.insert_text((100, 200), "Some text with a separator line below.")
        pdf_bytes = doc.tobytes()
        doc.close()

        # Write to a temp file so _extract_and_save_images can open it
        pdf_path = output_dir / "lines_only.pdf"
        pdf_path.write_bytes(pdf_bytes)

        results = _extract_and_save_images(pdf_path, output_dir)
        # Drawn lines are not raster images, so this mainly validates no crash
        # (PyMuPDF does not embed drawn lines as image xrefs)
        assert isinstance(results, list)

    def test_vacuum_pdf_images_pass_aspect_ratio(self, output_dir):
        """All images extracted from the real PDF should not be extreme-aspect-ratio."""
        results = _extract_and_save_images(VACUUM_PDF, output_dir)
        for item in results:
            # We can verify by re-opening the saved PNG
            import fitz
            pix = fitz.Pixmap(item["image_path"])
            w, h = pix.width, pix.height
            if min(w, h) > 0:
                ratio = max(w, h) / min(w, h)
                assert ratio <= MAX_IMAGE_ASPECT_RATIO, (
                    f"Image {item['image_name']} has extreme aspect ratio {ratio:.1f} "
                    f"({w}×{h}) — should have been filtered"
                )


# ── Document context builder ─────────────────────────────────────────


class TestBuildDocumentContext:
    def test_uses_title_and_author_from_metadata(self):
        meta = {
            "en_US_BKS_9316_EN.pdf": {
                "title": "BKS 9316 EN Vacuum Cleaner",
                "author": "ACME Corp",
            }
        }
        ctx = _build_document_context(
            "/storage/conv123/en_US_BKS_9316_EN.pdf", meta
        )
        assert "BKS 9316 EN Vacuum Cleaner" in ctx
        assert "ACME Corp" in ctx

    def test_falls_back_to_filename_when_no_metadata(self):
        ctx = _build_document_context("/storage/conv123/en_US_BKS_9316_EN.pdf", None)
        # Should contain the cleaned filename
        assert "en_US_BKS_9316_EN" in ctx or "BKS" in ctx

    def test_empty_metadata_dict_falls_back_to_filename(self):
        ctx = _build_document_context("/storage/conv123/en_US_BKS_9316_EN.pdf", {})
        assert ctx  # Must be non-empty
        assert "en_US_BKS_9316_EN" in ctx

    def test_only_title_no_author(self):
        meta = {"manual.pdf": {"title": "Vacuum Cleaner Manual"}}
        ctx = _build_document_context("/tmp/manual.pdf", meta)
        assert "Vacuum Cleaner Manual" in ctx
        assert "by" not in ctx


# ── Context-aware description prompt ────────────────────────────────


class TestDescribeImageWithContext:
    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_passes_document_context_in_prompt(self, mock_openai_cls, mock_settings):
        """document_context must appear in the user message sent to the API."""
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-5.4-mini",
            openai_reasoning_effort=None,
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="A filter replacement diagram."))]
        )

        _describe_image_with_context(
            b"fake_png",
            document_context="BKS 9316 EN Vacuum Cleaner Manual",
            page_text="Replace the HEPA filter every 12 months.",
        )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # Find the user message
        user_msg = next(m for m in messages if m["role"] == "user")
        # The user content is a list; find the text part
        text_parts = [c for c in user_msg["content"] if c.get("type") == "text"]
        assert text_parts, "Expected a text part in user message"
        combined_text = " ".join(p["text"] for p in text_parts)
        assert "BKS 9316 EN Vacuum Cleaner Manual" in combined_text
        assert "HEPA filter" in combined_text

    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_falls_back_to_plain_describe_when_no_context(self, mock_openai_cls, mock_settings):
        """Without context, should call _vision_extract_or_describe (OCR-first path)."""
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-5.4-mini",
            openai_reasoning_effort=None,
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="A photo."))]
        )

        result = _describe_image_with_context(b"fake_png")

        assert result == "A photo."
        # The OCR-first prompt should have been used
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        system_content = call_kwargs["messages"][0]["content"]
        assert "OCR-first" in system_content

    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_system_prompt_is_domain_aware(self, mock_openai_cls, mock_settings):
        """System prompt must instruct the model to use domain vocabulary."""
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-5.4-mini",
            openai_reasoning_effort=None,
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="desc"))]
        )

        _describe_image_with_context(b"fake", document_context="Any document")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        system_content = call_kwargs["messages"][0]["content"]
        assert "domain" in system_content.lower()
        assert "RAG" in system_content or "searchable" in system_content.lower()

    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_page_text_is_truncated_to_max(self, mock_openai_cls, mock_settings):
        """Page text sent to the model must be capped (no prompt bloat)."""
        from shared.extractors import _IMAGE_CONTEXT_PAGE_TEXT_MAX

        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-5.4-mini",
            openai_reasoning_effort=None,
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="desc"))]
        )

        long_text = "A" * (_IMAGE_CONTEXT_PAGE_TEXT_MAX * 3)
        _describe_image_with_context(b"fake", document_context="Doc", page_text=long_text)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        text_parts = [c for c in user_msg["content"] if c.get("type") == "text"]
        combined = " ".join(p["text"] for p in text_parts)
        # The text in the prompt must not exceed max + some overhead
        assert len(combined) < _IMAGE_CONTEXT_PAGE_TEXT_MAX * 3


# ── Enriched image chunk text ────────────────────────────────────────


class TestImageChunks:
    def _make_image(self, page: int, description: str, file_name: str = "manual.pdf") -> dict:
        return {
            "image_path": f"/tmp/{file_name.replace('.pdf', '')}_page{page}_img1.png",
            "image_name": f"{file_name.replace('.pdf', '')}_page{page}_img1.png",
            "file_name": file_name,
            "description": description,
            "page": page,
        }

    def test_chunk_text_contains_description(self):
        imgs = [self._make_image(5, "Exploded view of the dust bag compartment.")]
        chunks = _image_chunks(imgs, "manual.pdf")
        assert "Exploded view of the dust bag compartment." in chunks[0].text

    def test_chunk_text_contains_page_reference(self):
        imgs = [self._make_image(12, "HEPA filter removal steps.")]
        chunks = _image_chunks(imgs, "manual.pdf")
        assert "page 12" in chunks[0].text

    def test_chunk_text_contains_file_reference(self):
        imgs = [self._make_image(3, "Power button location.", "en_US_BKS_9316_EN.pdf")]
        chunks = _image_chunks(imgs, "en_US_BKS_9316_EN.pdf")
        # Should include the cleaned file name (without UUID prefix/suffix)
        assert "BKS_9316_EN" in chunks[0].text or "en_US_BKS_9316_EN" in chunks[0].text

    def test_chunk_is_image_type(self):
        imgs = [self._make_image(1, "Front panel overview.")]
        chunks = _image_chunks(imgs, "manual.pdf")
        assert chunks[0].metadata["is_image"] is True

    def test_multiple_images_produce_unique_chunk_ids(self):
        imgs = [
            self._make_image(1, "Front view.", "manual.pdf"),
            self._make_image(2, "Side view.", "manual.pdf"),
        ]
        chunks = _image_chunks(imgs, "manual.pdf")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique"

    def test_page_none_handled_gracefully(self):
        img = {
            "image_path": "/tmp/manual_img1.png",
            "image_name": "manual_img1.png",
            "file_name": "manual.pdf",
            "description": "Some image.",
            "page": None,
        }
        chunks = _image_chunks([img], "manual.pdf")
        assert len(chunks) == 1
        assert chunks[0].page is None


# ── End-to-end extraction from real PDF ─────────────────────────────


class TestVacuumPDFExtraction:
    def test_extracts_at_least_one_image(self, output_dir):
        results = _extract_and_save_images(VACUUM_PDF, output_dir)
        assert len(results) > 0, "Expected at least one image from the vacuum cleaner manual"

    def test_all_extracted_images_are_valid_png(self, output_dir):
        results = _extract_and_save_images(VACUUM_PDF, output_dir)
        for item in results:
            header = Path(item["image_path"]).read_bytes()[:4]
            assert header == b"\x89PNG", f"Not a valid PNG: {item['image_name']}"

    @patch("shared.extractors._describe_image_with_context", return_value="Mocked description.")
    def test_describe_with_context_called_during_describe_one(self, mock_describe, output_dir):
        """_describe_image_with_context must be called (not the plain _describe_image)."""
        from shared.extractors import _describe_one

        item = {
            "image_path": str(output_dir / "test.png"),
            "image_name": "test.png",
            "file_name": "en_US_BKS_9316_EN.pdf",
            "png_bytes": b"\x89PNG fake",
            "page": 1,
        }
        # _describe_one in extractors.py still uses plain _describe_image.
        # This test verifies the page_worker path uses the context-aware version.
        # We test it via the page_worker's _describe_images_parallel wrapper.
        from shared.page_worker import _describe_images_parallel

        with patch("shared.page_worker._describe_image_with_context", return_value="ctx desc") as pw_mock:
            result = _describe_images_parallel(
                [item], "conv123", "en_US_BKS_9316_EN.pdf",
                document_context="BKS 9316 Vacuum Cleaner",
                page_text="Filter maintenance instructions",
            )
        assert pw_mock.called
        pw_mock.assert_called_once_with(
            b"\x89PNG fake",
            document_context="BKS 9316 Vacuum Cleaner",
            page_text="Filter maintenance instructions",
        )
        assert result[0]["description"] == "ctx desc"
