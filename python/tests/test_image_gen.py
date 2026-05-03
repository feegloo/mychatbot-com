"""Unit tests for shared.image_gen.generate_image.

Focus: reference-image routing between OpenAI's images.generate and
images.edit endpoints, and validation of reference paths.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from shared import image_gen

PNG_1x1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _make_jpeg_bytes(width: int, height: int, color: tuple[int, int, int] = (32, 64, 96)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def mock_openai():
    """Patch OpenAI client + settings and return the mocked client."""
    with patch("shared.image_gen.OpenAI") as mock_cls, patch(
        "shared.image_gen.get_settings"
    ) as mock_settings:
        mock_settings.return_value = MagicMock(openai_api_key="sk-test")
        client = MagicMock()
        mock_cls.return_value = client

        # Both endpoints return the same minimal shape
        fake_response = MagicMock(
            data=[MagicMock(b64_json=base64.b64encode(PNG_1x1).decode(), url=None)]
        )
        fake_response.data[0].revised_prompt = "revised"
        client.images.generate.return_value = fake_response
        client.images.edit.return_value = fake_response
        yield client


def _make_png(tmp_path: Path, name: str = "ref.png") -> Path:
    p = tmp_path / name
    p.write_bytes(PNG_1x1)
    return p


class TestReferenceImageRouting:
    def test_no_references_uses_generate_endpoint(self, mock_openai, tmp_path):
        image_gen.generate_image(prompt="a cat", storage_dir=str(tmp_path))

        assert mock_openai.images.generate.called
        assert not mock_openai.images.edit.called

    def test_with_single_reference_uses_edit_endpoint(self, mock_openai, tmp_path):
        ref = _make_png(tmp_path)

        image_gen.generate_image(
            prompt="make it a sunset",
            storage_dir=str(tmp_path),
            reference_image_paths=[str(ref)],
        )

        assert mock_openai.images.edit.called
        assert not mock_openai.images.generate.called
        call_kwargs = mock_openai.images.edit.call_args.kwargs
        assert call_kwargs["prompt"] == "make it a sunset"
        # Single reference is passed as a single file handle, not a list.
        assert not isinstance(call_kwargs["image"], list)

    def test_with_multiple_references_passes_list(self, mock_openai, tmp_path):
        refs = [str(_make_png(tmp_path, f"r{i}.png")) for i in range(3)]

        image_gen.generate_image(
            prompt="blend these",
            storage_dir=str(tmp_path),
            reference_image_paths=refs,
        )

        call_kwargs = mock_openai.images.edit.call_args.kwargs
        assert isinstance(call_kwargs["image"], list)
        assert len(call_kwargs["image"]) == 3

    def test_caps_references_at_max(self, mock_openai, tmp_path):
        refs = [
            str(_make_png(tmp_path, f"r{i}.png"))
            for i in range(image_gen.MAX_REFERENCE_IMAGES + 3)
        ]

        image_gen.generate_image(
            prompt="p",
            storage_dir=str(tmp_path),
            reference_image_paths=refs,
        )

        call_kwargs = mock_openai.images.edit.call_args.kwargs
        assert len(call_kwargs["image"]) == image_gen.MAX_REFERENCE_IMAGES


class TestReferenceValidation:
    def test_missing_file_is_skipped(self, mock_openai, tmp_path):
        real = _make_png(tmp_path)
        missing = tmp_path / "does-not-exist.png"

        image_gen.generate_image(
            prompt="p",
            storage_dir=str(tmp_path),
            reference_image_paths=[str(missing), str(real)],
        )

        # Only the real file survived -> single handle, routed to edit
        call_kwargs = mock_openai.images.edit.call_args.kwargs
        assert not isinstance(call_kwargs["image"], list)

    def test_unsupported_mime_is_skipped(self, mock_openai, tmp_path):
        bad = tmp_path / "notes.txt"
        bad.write_bytes(b"hello")

        image_gen.generate_image(
            prompt="p",
            storage_dir=str(tmp_path),
            reference_image_paths=[str(bad)],
        )

        # All refs dropped -> falls back to plain generate
        assert mock_openai.images.generate.called
        assert not mock_openai.images.edit.called

    def test_empty_list_falls_back_to_generate(self, mock_openai, tmp_path):
        image_gen.generate_image(
            prompt="p",
            storage_dir=str(tmp_path),
            reference_image_paths=[],
        )

        assert mock_openai.images.generate.called
        assert not mock_openai.images.edit.called


class TestPdfCoverReference:
    def test_pdf_reference_is_rendered_as_png_cover(self, mock_openai, tmp_path):
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-fake")
        cover = tmp_path / "book.pdf.cover.png"

        def _fake_render(p):
            cover.write_bytes(PNG_1x1)
            return cover

        with patch(
            "shared.image_gen._render_pdf_cover_png", side_effect=_fake_render
        ) as render:
            image_gen.generate_image(
                prompt="illustrate this book",
                storage_dir=str(tmp_path),
                reference_image_paths=[str(pdf)],
            )

        render.assert_called_once()
        assert cover.is_file()
        assert mock_openai.images.edit.called
        assert not mock_openai.images.generate.called

    def test_pdf_render_failure_drops_reference(self, mock_openai, tmp_path):
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-fake")

        with patch(
            "shared.image_gen._render_pdf_cover_png", return_value=None
        ):
            image_gen.generate_image(
                prompt="p",
                storage_dir=str(tmp_path),
                reference_image_paths=[str(pdf)],
            )

        # No usable references -> plain generate endpoint
        assert mock_openai.images.generate.called
        assert not mock_openai.images.edit.called


class TestOutput:
    def test_saves_png_and_returns_file_name(self, mock_openai, tmp_path):
        result = image_gen.generate_image(prompt="p", storage_dir=str(tmp_path))

        # Default output_format is "jpeg", so the saved file uses the .jpg extension.
        assert result["file_name"].endswith(".jpg")
        assert (tmp_path / result["file_name"]).is_file()

    def test_saved_image_dimensions_match_requested_size(self, tmp_path):
        requested_size = "320x640"
        expected_width, expected_height = (320, 640)
        jpeg_bytes = _make_jpeg_bytes(expected_width, expected_height)

        with patch("shared.image_gen.OpenAI") as mock_cls, patch(
            "shared.image_gen.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                openai_api_key="sk-test", openai_image_model="gpt-image-2"
            )
            client = MagicMock()
            mock_cls.return_value = client
            response = MagicMock(
                data=[MagicMock(b64_json=base64.b64encode(jpeg_bytes).decode(), url=None)]
            )
            response.data[0].revised_prompt = "revised"
            client.images.generate.return_value = response

            result = image_gen.generate_image(
                prompt="wide clinical portrait",
                storage_dir=str(tmp_path),
                size=requested_size,
            )

        call_kwargs = client.images.generate.call_args.kwargs
        assert call_kwargs["size"] == requested_size

        saved_path = tmp_path / result["file_name"]
        assert saved_path.is_file()

        with Image.open(saved_path) as saved_image:
            assert saved_image.size == (expected_width, expected_height)


class TestStreamingModelFallback:
    def test_streaming_switches_from_gpt_image_1_to_gpt_image_2(self, tmp_path):
        with patch("shared.image_gen.OpenAI") as mock_cls, patch(
            "shared.image_gen.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                openai_api_key="sk-test", openai_image_model="gpt-image-1"
            )
            client = MagicMock()
            mock_cls.return_value = client

            partial_event = MagicMock(type="response.image.partial_image", b64_json="cA==", partial_image_index=0)
            completed_event = MagicMock(type="response.image.completed", b64_json=base64.b64encode(PNG_1x1).decode(), revised_prompt="revised")
            client.images.generate.return_value = [partial_event, completed_event]

            events = list(
                image_gen.generate_image_streaming(
                    prompt="a calm scene",
                    storage_dir=str(tmp_path),
                )
            )

            assert events[0]["type"] == "partial"
            assert events[-1]["type"] == "completed"
            call_kwargs = client.images.generate.call_args.kwargs
            assert call_kwargs["model"] == "gpt-image-2"


class TestInspiredRetry:
    def test_retries_once_with_inspired_emphasis_on_failure(self, mock_openai, tmp_path):
        # First call fails (e.g. OpenAI content filter block), second succeeds.
        fake_response = MagicMock(
            data=[MagicMock(b64_json=base64.b64encode(PNG_1x1).decode(), url=None)]
        )
        fake_response.data[0].revised_prompt = "revised"
        mock_openai.images.generate.side_effect = [
            Exception("request blocked"),
            fake_response,
        ]

        result = image_gen.generate_image(
            prompt="Daenerys in the Great Pyramid",
            storage_dir=str(tmp_path),
        )

        assert mock_openai.images.generate.call_count == 2
        retry_prompt = mock_openai.images.generate.call_args_list[1].kwargs["prompt"]
        assert "inspired" in retry_prompt.lower()
        assert result["file_name"].endswith(".jpg")

    def test_propagates_error_when_retry_also_fails(self, mock_openai, tmp_path):
        mock_openai.images.generate.side_effect = Exception("still blocked")

        with pytest.raises(Exception, match="still blocked"):
            image_gen.generate_image(prompt="anything", storage_dir=str(tmp_path))

        # Exactly two attempts: original + one inspired-retry.
        assert mock_openai.images.generate.call_count == 2


class TestAspectFraming:
    def test_infer_prompt_aspect_normalizes_landscape_request_to_3_2(self):
        assert (
            image_gen.infer_prompt_aspect("Generate image inspired by clinic interior, 2:3 landscape")
            == "3:2"
        )

    def test_infer_prompt_aspect_accepts_explicit_3_2_landscape(self):
        assert (
            image_gen.infer_prompt_aspect("Generate image inspired by clinic interior, 3:2 landscape")
            == "3:2"
        )

    def test_infer_prompt_aspect_detects_supported_portrait_request(self):
        assert (
            image_gen.infer_prompt_aspect("Generate image inspired by doctor portrait, 3:4 portrait")
            == "3:4"
        )

    def test_build_aspect_framing_instruction_for_landscape_uses_black_bars(self):
        instruction = image_gen.build_aspect_framing_instruction("3:2")

        assert "1:1 square canvas" in instruction
        assert "3:2 landscape" in instruction
        assert "solid black matte bars above and below" in instruction

    def test_build_aspect_framing_instruction_for_portrait_uses_black_bars(self):
        instruction = image_gen.build_aspect_framing_instruction("3:4")

        assert "1:1 square canvas" in instruction
        assert "3:4 portrait" in instruction
        assert "solid black matte bars on the left and right sides" in instruction

    def test_build_image_prompt_returns_inferred_aspect_and_passes_framing_to_llm(self):
        captured_messages: list[dict] = []

        def fake_traced_openai_call(**kwargs):
            nonlocal captured_messages
            captured_messages = kwargs["messages"]
            return ('{"prompt":"built prompt","title":"Built Title","source_indices":[0]}', {})

        with patch("shared.image_gen.OpenAI") as mock_cls, patch(
            "shared.image_gen.get_settings"
        ) as mock_settings, patch(
            "shared.image_gen.traced_openai_call", side_effect=fake_traced_openai_call
        ):
            mock_settings.return_value = MagicMock(
                openai_api_key="sk-test", openai_chat_model="gpt-4.1-mini"
            )
            mock_cls.return_value = MagicMock()

            result = image_gen.build_image_prompt(
                question="Generate image inspired by hair treatment clinic, 2:3 landscape",
                rag_chunks=[{"text": "clinic interior", "file_name": "notes.txt"}],
            )

        assert result["aspect"] == "3:2"
        assert captured_messages[1]["content"]
        assert "true 3:2 landscape rectangle" in captured_messages[1]["content"]
        assert "solid black matte bars above and below" in captured_messages[1]["content"]


class TestRandomCreativeSeed:
    """Verify that pixel-art styles inject rendering rules; others don't."""

    # One representative from each pixel-art style (exact strings from _PIXEL_ART_STYLES).
    _PIXEL_STYLES = [
        "16-bit SNES / Mega Drive pixel art — vibrant 256-color palette, chunky character sprites, tiled scrolling background",
        "1994 DOS VGA pixel art — 320×200 resolution aesthetic, dithered gradients, flat EGA-palette scenes, subtle scanline overlay",
        "8-bit NES / Famicom pixel art — 4-color-per-tile sprites, side-scroll or top-down perspective, blocky retro look",
        "Game Boy 4-shade monochrome pixel art — LCD green dot-matrix palette, stark high-contrast silhouettes, handheld screen feel",
        "retro isometric pixel art RPG tilemap — axonometric 2D grid, classic dungeon or city scene, limited color ramp, Ultima / Syndicate era",
    ]

    # Non-pixel styles that must NOT trigger the rendering rules.
    _NON_PIXEL_STYLES = [
        "oil painting",
        "watercolor",
        "vaporwave glitch art — hot pink and purple neons, chrome shape distortion, tropical retro-futurism, A E S T H E T I C",
        "noir graphic novel panel — heavy black ink, stark chiaroscuro, selective single-accent color (crimson or gold)",
    ]

    def _seed_for_style(self, style: str) -> str:
        """Call _random_creative_seed() with a deterministic style choice."""
        choices = iter([style, "melancholic", "golden hour sunlight", "wide panoramic shot"])
        with patch("shared.image_gen.random.choice", side_effect=choices):
            return image_gen._random_creative_seed()

    @pytest.mark.parametrize("style", _PIXEL_STYLES)
    def test_pixel_art_style_appends_rendering_rules(self, style: str):
        seed = self._seed_for_style(style)
        assert "PIXEL ART RENDERING RULES" in seed

    @pytest.mark.parametrize("style", _NON_PIXEL_STYLES)
    def test_non_pixel_style_omits_rendering_rules(self, style: str):
        seed = self._seed_for_style(style)
        assert "PIXEL ART RENDERING RULES" not in seed

    def test_all_pixel_art_styles_are_present_in_art_styles_list(self):
        """Guard: every entry in _PIXEL_ART_STYLES must exist in _ART_STYLES."""
        for style in image_gen._PIXEL_ART_STYLES:
            assert style in image_gen._ART_STYLES, (
                f"_PIXEL_ART_STYLES entry not found in _ART_STYLES: {style!r}"
            )
