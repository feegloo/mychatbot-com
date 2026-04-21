"""Unit tests for shared.image_gen.generate_image.

Focus: reference-image routing between OpenAI's images.generate and
images.edit endpoints, and validation of reference paths.
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared import image_gen


PNG_1x1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


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


class TestOutput:
    def test_saves_png_and_returns_file_name(self, mock_openai, tmp_path):
        result = image_gen.generate_image(prompt="p", storage_dir=str(tmp_path))

        assert result["file_name"].endswith(".png")
        assert result["revised_prompt"] == "revised"
        assert (tmp_path / result["file_name"]).is_file()
