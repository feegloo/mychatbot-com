"""Content moderation for uploaded files.

Uses the OpenAI Moderation API to detect sexual content in uploaded files.
When detected, raises SexualContentError which the indexing pipeline propagates
as a user-facing error, preventing the file from being indexed and stored.
"""

from __future__ import annotations

import base64
import logging

from openai import OpenAI

from .config import get_settings

logger = logging.getLogger(__name__)

# Multimodal model: supports both image and text inputs.
# Falls back to text-only model when no image is provided.
_MODERATION_MODEL_IMAGE = "omni-moderation-latest"
_MODERATION_MODEL_TEXT = "text-moderation-latest"

# Maximum text length sent to the moderation API (characters).
# The API supports up to 32 768 tokens; 20 000 chars is a safe proxy.
_MAX_TEXT_CHARS = 20_000


class SexualContentError(ValueError):
    """Raised when uploaded file content is classified as sexual by the moderation API."""


def check_content_moderation(
    text: str,
    *,
    image_bytes: bytes | None = None,
    mime_type: str = "image/png",
) -> None:
    """Check uploaded content for sexual material using the OpenAI Moderation API.

    For image files, the image bytes are sent directly to the multimodal
    moderation endpoint alongside any extracted text description.
    For text-only files, only the extracted text is checked.

    Raises:
        SexualContentError: if the content is flagged as sexual.

    This function does NOT raise on moderation API errors (network issues,
    quota, etc.).  Those are logged as warnings so that temporary API
    unavailability does not block legitimate uploads.
    """
    try:
        _run_moderation(text, image_bytes=image_bytes, mime_type=mime_type)
    except SexualContentError:
        raise
    except Exception as exc:
        logger.warning("⚠️ Content moderation API call failed (upload allowed): %s", exc)


def _run_moderation(
    text: str,
    *,
    image_bytes: bytes | None = None,
    mime_type: str = "image/png",
) -> None:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        input_items: list[dict] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            }
        ]
        if text and text.strip():
            input_items.append({"type": "text", "text": text[:_MAX_TEXT_CHARS]})

        response = client.moderations.create(
            model=_MODERATION_MODEL_IMAGE,
            input=input_items,  # type: ignore[arg-type]
        )
    else:
        if not text or not text.strip():
            return
        response = client.moderations.create(
            model=_MODERATION_MODEL_TEXT,
            input=text[:_MAX_TEXT_CHARS],
        )

    for result in response.results:
        categories = result.categories
        if result.flagged and (
            getattr(categories, "sexual", False)
            or getattr(categories, "sexual_minors", False)
        ):
            logger.warning("🚫 Sexual content detected in uploaded file — upload blocked")
            raise SexualContentError(
                "This file contains sexual or explicit content and cannot be uploaded."
            )
