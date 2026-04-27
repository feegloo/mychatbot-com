import json
from unittest.mock import MagicMock, patch

from shared.extractors import (
    _reflow_pdf_text,
    _render_pdf_page_to_png,
    _sanitize_text,
    _vision_extract_or_describe,
    extract_csv,
    extract_json,
    extract_plain_text,
    extract_text,
    page_needs_ocr,
)

PNG_HEADER = b"\x89PNG"


class TestSanitizeText:
    def test_removes_null_bytes(self):
        assert _sanitize_text("hello\x00world") == "helloworld"

    def test_preserves_newlines_and_tabs(self):
        assert _sanitize_text("line1\nline2\ttab") == "line1\nline2\ttab"

    def test_removes_control_characters(self):
        assert _sanitize_text("hello\x01\x02\x03world") == "helloworld"

    def test_preserves_normal_text(self):
        text = "Normal text with Unicode: zażółć gęślą jaźń"
        assert _sanitize_text(text) == text


class TestReflowPdfText:
    def test_joins_single_line_breaks(self):
        result = _reflow_pdf_text("hello\nworld")
        assert result == "hello world"

    def test_preserves_paragraph_breaks(self):
        result = _reflow_pdf_text("paragraph 1\n\nparagraph 2")
        assert result == "paragraph 1\n\nparagraph 2"

    def test_handles_empty_string(self):
        assert _reflow_pdf_text("") == ""

    def test_strips_whitespace(self):
        result = _reflow_pdf_text("  hello  \n  world  ")
        assert result == "hello world"


class TestExtractPlainText:
    def test_reads_text_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello, World!", encoding="utf-8")
        assert extract_plain_text(f) == "Hello, World!"


class TestExtractJson:
    def test_formats_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key":"value"}', encoding="utf-8")
        result = extract_json(f)
        parsed = json.loads(result)
        assert parsed == {"key": "value"}


class TestExtractCsv:
    def test_reads_csv(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")
        result = extract_csv(f)
        assert "Alice" in result
        assert "Bob" in result


class TestExtractText:
    def test_dispatch_txt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("plain text content", encoding="utf-8")
        result = extract_text(str(f))
        assert result == "plain text content"

    def test_dispatch_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        result = extract_text(str(f))
        assert '"a": 1' in result

    def test_dispatch_md(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\nContent", encoding="utf-8")
        result = extract_text(str(f))
        assert "Title" in result


class TestPageNeedsOcr:
    def test_empty_page_needs_ocr(self):
        assert page_needs_ocr("# Page 1\n\n") is True

    def test_page_with_only_heading_needs_ocr(self):
        assert page_needs_ocr("# Page 5") is True

    def test_sparse_text_needs_ocr(self):
        assert page_needs_ocr("# Page 1\n\nshort") is True

    def test_real_text_does_not_need_ocr(self):
        assert page_needs_ocr("# Page 1\n\nThis is a paragraph with enough text content.") is False

    def test_arabic_text_does_not_need_ocr(self):
        arabic = "# Page 1\n\n" + "على كتب المنشوي الستة ما يكشف عن كثير"
        assert page_needs_ocr(arabic) is False

    def test_blank_string_needs_ocr(self):
        assert page_needs_ocr("") is True


class TestOcrPdfPage:
    @patch("shared.extractors._get_local_ocr_pages", return_value=["local arabic text"])
    @patch("shared.extractors.OpenAI")
    def test_ocr_uses_local_pdf_ocr_when_available(
        self, mock_openai_cls, _mock_local_pages, tmp_path
    ):
        import fitz

        doc = fitz.open()
        doc.new_page(width=200, height=200)
        pdf_path = str(tmp_path / "scan.pdf")
        doc.save(pdf_path)
        doc.close()

        from shared.extractors import ocr_pdf_page

        result = ocr_pdf_page(pdf_path, 0)
        assert result == "local arabic text"
        mock_openai_cls.assert_not_called()

    @patch("shared.extractors._get_local_ocr_pages", return_value=[""])
    @patch("shared.extractors.OpenAI")
    def test_ocr_falls_back_to_openai_when_local_page_empty(
        self, mock_openai_cls, _mock_local_pages, tmp_path
    ):
        import fitz

        doc = fitz.open()
        doc.new_page(width=200, height=200)
        pdf_path = str(tmp_path / "scan.pdf")
        doc.save(pdf_path)
        doc.close()

        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from shared.extractors import ocr_pdf_page

        result = ocr_pdf_page(pdf_path, 0)
        assert result == "ok"
        mock_client.chat.completions.create.assert_called_once()

    @patch("shared.extractors.OpenAI")
    def test_ocr_returns_extracted_text(self, mock_openai_cls, tmp_path):
        import fitz

        # Create a minimal 1-page PDF
        doc = fitz.open()
        doc.new_page(width=200, height=200)
        pdf_path = str(tmp_path / "scan.pdf")
        doc.save(pdf_path)
        doc.close()

        mock_choice = MagicMock()
        mock_choice.message.content = "بسم الله الرحمن الرحيم"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from shared.extractors import ocr_pdf_page

        result = ocr_pdf_page(pdf_path, 0)
        assert result == "بسم الله الرحمن الرحيم"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_completion_tokens"] == 5000
        assert "OCR-first" in call_kwargs["messages"][0]["content"]

    @patch("shared.extractors.OpenAI")
    def test_ocr_handles_real_arabic_pdf_fixture(self, mock_openai_cls):
        from pathlib import Path

        from shared.extractors import ocr_pdf_page

        repo_root = Path(__file__).resolve().parent.parent.parent
        arabic_pdf = repo_root / "test-files" / "54_Mathnawi_Arabic01.pdf"
        assert arabic_pdf.exists(), f"Missing fixture: {arabic_pdf}"
        rendered = _render_pdf_page_to_png(str(arabic_pdf), 0)
        assert rendered.startswith(PNG_HEADER), "Arabic PDF page should render to PNG"

        mock_choice = MagicMock()
        mock_choice.message.content = "بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        result = ocr_pdf_page(str(arabic_pdf), 0)
        assert result == "بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
        assert any("\u0600" <= ch <= "\u06FF" for ch in result)
        mock_client.chat.completions.create.assert_called_once()


class TestVisionExtractOrDescribe:
    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_passes_mime_tokens_and_detail(self, mock_openai_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-5.4-mini",
            openai_reasoning_effort="low",
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )

        result = _vision_extract_or_describe(
            b"fake",
            mime_type="image/jpeg",
            max_completion_tokens=777,
            detail="high",
        )

        assert result == "ok"
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 777
        assert call_kwargs["messages"][1]["content"][0]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )
        assert call_kwargs["messages"][1]["content"][0]["image_url"]["detail"] == "high"

# ── GIF description tests ──────────────────────────────────────────


def _make_gif(path, n_frames: int = 1, size: tuple[int, int] = (20, 20)) -> None:
    """Create a minimal GIF file with `n_frames` distinct frames."""
    from PIL import Image

    frames = []
    for i in range(n_frames):
        img = Image.new("RGB", size, color=(i * 40 % 255, 100, 200))
        frames.append(img)

    frames[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=100,
    )


class TestExtractGifFrames:
    def test_single_frame_gif_returns_empty(self, tmp_path):
        from shared.extractors import _extract_gif_frames

        gif = tmp_path / "static.gif"
        _make_gif(gif, n_frames=1)
        assert _extract_gif_frames(gif) == []

    def test_animated_gif_returns_png_bytes(self, tmp_path):
        from shared.extractors import _extract_gif_frames

        gif = tmp_path / "anim.gif"
        _make_gif(gif, n_frames=10)
        frames = _extract_gif_frames(gif, max_frames=4)
        assert len(frames) > 0
        # Each extracted frame should be a PNG (starts with PNG magic bytes)
        for frame_bytes in frames:
            assert frame_bytes[:4] == b"\x89PNG"

    def test_animated_gif_capped_at_max_frames(self, tmp_path):
        from shared.extractors import _extract_gif_frames

        gif = tmp_path / "long.gif"
        _make_gif(gif, n_frames=30)
        frames = _extract_gif_frames(gif, max_frames=4)
        assert len(frames) <= 4

    def test_first_and_last_frame_always_included(self, tmp_path):
        from shared.extractors import _extract_gif_frames

        # 10 frames, max_frames=4 → linear indices: 0, 3, 6, 9 (last=9 ✓)
        gif = tmp_path / "anim.gif"
        _make_gif(gif, n_frames=10)
        frames = _extract_gif_frames(gif, max_frames=4)
        assert len(frames) == 4  # exactly 4 distinct indices

    def test_invalid_max_frames_raises(self, tmp_path):
        import pytest
        from shared.extractors import _extract_gif_frames

        gif = tmp_path / "anim.gif"
        _make_gif(gif, n_frames=5)
        with pytest.raises(ValueError, match="max_frames must be >= 2"):
            _extract_gif_frames(gif, max_frames=1)

    def test_max_frames_larger_than_gif_returns_all_frames(self, tmp_path):
        from shared.extractors import _extract_gif_frames

        gif = tmp_path / "short.gif"
        _make_gif(gif, n_frames=3)
        frames = _extract_gif_frames(gif, max_frames=10)
        # Only 3 frames exist; all 3 should be returned
        assert len(frames) == 3


class TestDescribeGif:
    @patch("shared.extractors.get_settings")
    @patch("shared.extractors.OpenAI")
    def test_animated_gif_sends_multiple_frames(self, mock_openai_cls, mock_settings, tmp_path):
        from shared.extractors import _describe_gif

        mock_settings.return_value = MagicMock(
            openai_api_key="test",
            openai_chat_model="gpt-5.4-mini",
            openai_reasoning_effort="low",
        )
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="a spoon stirs honey"))]
        mock_resp.usage = MagicMock(
            prompt_tokens=10, completion_tokens=5, total_tokens=15,
            prompt_tokens_details=None,
        )
        mock_client.chat.completions.create.return_value = mock_resp

        gif = tmp_path / "anim.gif"
        _make_gif(gif, n_frames=12)

        result = _describe_gif(gif)

        assert result == "a spoon stirs honey"
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        # First content item is the text preamble, rest are images
        image_items = [c for c in user_content if c.get("type") == "image_url"]
        assert len(image_items) >= 1
        for item in image_items:
            assert item["image_url"]["url"].startswith("data:image/png;base64,")
        # reasoning_effort must be forwarded to the API call
        assert call_kwargs.get("reasoning_effort") == "low"

    @patch("shared.extractors._describe_image")
    def test_static_gif_falls_back_to_describe_image(self, mock_describe, tmp_path):
        from shared.extractors import _describe_gif

        mock_describe.return_value = "a static honey comb image"

        gif = tmp_path / "static.gif"
        _make_gif(gif, n_frames=1)

        result = _describe_gif(gif)

        assert result == "a static honey comb image"
        mock_describe.assert_called_once()

    @patch("shared.extractors._extract_gif_frames", side_effect=Exception("corrupt"))
    @patch("shared.extractors._describe_image")
    def test_extraction_failure_falls_back_to_describe_image(
        self, mock_describe, _mock_frames, tmp_path
    ):
        from shared.extractors import _describe_gif

        mock_describe.return_value = "fallback description"

        gif = tmp_path / "bad.gif"
        gif.write_bytes(b"GIF89a" + b"\x00" * 10)  # minimal corrupt GIF header (6 byte sig + padding)

        result = _describe_gif(gif)

        assert result == "fallback description"
        mock_describe.assert_called_once()
