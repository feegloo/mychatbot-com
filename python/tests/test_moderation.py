"""Unit tests for shared.moderation content moderation module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shared.moderation import SexualContentError, check_content_moderation


def _make_moderation_result(flagged: bool, sexual: bool = False) -> MagicMock:
    """Build a mock OpenAI moderation result."""
    result = MagicMock()
    result.flagged = flagged
    result.categories = MagicMock()
    result.categories.sexual = sexual
    result.categories.sexual_minors = False
    return result


def _make_moderation_response(results: list[MagicMock]) -> MagicMock:
    response = MagicMock()
    response.results = results
    return response


class TestCheckContentModeration:
    def test_clean_text_does_not_raise(self):
        """Non-sexual text content must pass without error."""
        mock_response = _make_moderation_response(
            [_make_moderation_result(flagged=False, sexual=False)]
        )
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            check_content_moderation("This is a normal document about cooking.")

    def test_sexual_text_raises(self):
        """Text flagged as sexual must raise SexualContentError."""
        mock_response = _make_moderation_response(
            [_make_moderation_result(flagged=True, sexual=True)]
        )
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            with pytest.raises(SexualContentError):
                check_content_moderation("explicit sexual content here")

    def test_flagged_but_not_sexual_does_not_raise(self):
        """Content flagged for other reasons (e.g., violence) must not raise SexualContentError."""
        result = _make_moderation_result(flagged=True, sexual=False)
        mock_response = _make_moderation_response([result])
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            # Should not raise
            check_content_moderation("violent content description")

    def test_empty_text_skips_api_call(self):
        """Empty text must skip the moderation API call entirely."""
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            mock_openai_cls.return_value = client

            check_content_moderation("")
            check_content_moderation("   ")

            client.moderations.create.assert_not_called()

    def test_api_error_is_swallowed(self):
        """API errors must not propagate — uploads should be allowed on moderation failure."""
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.side_effect = ConnectionError("timeout")
            mock_openai_cls.return_value = client

            # Must not raise
            check_content_moderation("some text")

    def test_image_bytes_uses_multimodal_model(self):
        """When image_bytes are provided, the omni-moderation model must be used."""
        mock_response = _make_moderation_response(
            [_make_moderation_result(flagged=False)]
        )
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            check_content_moderation(
                "image description",
                image_bytes=b"\x89PNG\r\n\x1a\n",
                mime_type="image/png",
            )

            call_kwargs = client.moderations.create.call_args.kwargs
            assert call_kwargs["model"] == "omni-moderation-latest"
            # Input must be a list containing an image_url entry
            input_items = call_kwargs["input"]
            assert any(item.get("type") == "image_url" for item in input_items)

    def test_text_only_uses_text_model(self):
        """Without image_bytes, the text-moderation model must be used."""
        mock_response = _make_moderation_response(
            [_make_moderation_result(flagged=False)]
        )
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            check_content_moderation("some document text")

            call_kwargs = client.moderations.create.call_args.kwargs
            assert call_kwargs["model"] == "text-moderation-latest"

    def test_sexual_image_raises(self):
        """Image content flagged as sexual must raise SexualContentError."""
        mock_response = _make_moderation_response(
            [_make_moderation_result(flagged=True, sexual=True)]
        )
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            with pytest.raises(SexualContentError):
                check_content_moderation(
                    "",
                    image_bytes=b"\x89PNG\r\n\x1a\n",
                    mime_type="image/png",
                )

    def test_text_truncated_to_max_chars(self):
        """Long text must be truncated before sending to the moderation API."""
        mock_response = _make_moderation_response(
            [_make_moderation_result(flagged=False)]
        )
        with (
            patch("shared.moderation.OpenAI") as mock_openai_cls,
            patch("shared.moderation.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(openai_api_key="sk-test")
            client = MagicMock()
            client.moderations.create.return_value = mock_response
            mock_openai_cls.return_value = client

            long_text = "a" * 50_000
            check_content_moderation(long_text)

            call_kwargs = client.moderations.create.call_args.kwargs
            sent_text = call_kwargs["input"]
            assert len(sent_text) <= 20_000


class TestSexualContentError:
    def test_is_value_error_subclass(self):
        """SexualContentError must be a ValueError for easy catching."""
        assert issubclass(SexualContentError, ValueError)

    def test_has_meaningful_message(self):
        err = SexualContentError("test message")
        assert "test message" in str(err)
