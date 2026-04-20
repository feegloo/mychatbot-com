"""Image generation via OpenAI DALL-E API.

Generates images from text descriptions and saves them to the conversation's
storage directory so they can be served via the existing /api/storage/ route.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path

import requests
from openai import OpenAI

from shared.config import get_settings

logger = logging.getLogger(__name__)


def generate_image(
    prompt: str,
    storage_dir: str,
    size: str = "1024x1024",
    quality: str = "low",
    model: str = "gpt-image-1",
) -> dict:
    """Generate an image from a text prompt using OpenAI DALL-E.

    Args:
        prompt: The text description for image generation.
        storage_dir: Directory to save the generated image.
        size: Image size (1024x1024, 1024x1792, 1792x1024).
        quality: Image quality (auto, high, low).
        model: OpenAI image model to use.

    Returns:
        dict with 'file_name' (saved filename) and 'revised_prompt' (DALL-E's prompt).
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    logger.info(
        f"🎨 Generating image: prompt='{prompt[:100]}...' size={size} quality={quality} model={model}"
    )

    result = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size=size,
        quality=quality,
    )

    image_data = result.data[0]
    revised_prompt = getattr(image_data, "revised_prompt", prompt)

    # gpt-image-1 returns b64_json by default; dall-e-3 returns a URL
    image_url = getattr(image_data, "url", None)
    b64_json = getattr(image_data, "b64_json", None)

    if b64_json:
        image_bytes = base64.b64decode(b64_json)
    elif image_url:
        resp = requests.get(image_url, timeout=60)
        resp.raise_for_status()
        image_bytes = resp.content
    else:
        raise ValueError("OpenAI image response contained neither url nor b64_json")

    # Save to storage dir
    file_name = f"generated-{uuid.uuid4().hex[:12]}.png"
    os.makedirs(storage_dir, exist_ok=True)
    file_path = Path(storage_dir) / file_name
    file_path.write_bytes(image_bytes)

    logger.info(f"🖼️ Image saved: {file_path} ({len(image_bytes)} bytes)")

    return {
        "file_name": file_name,
        "revised_prompt": revised_prompt,
    }


def build_image_prompt(
    question: str,
    context: str = "",
    welcome_messages: list[str] | None = None,
) -> str:
    """Build a DALL-E prompt from the user's question and conversation context.

    Extracts the visual intent and creates a descriptive image generation prompt.
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    system = (
        "You are an expert prompt engineer for AI image generation. "
        "Given the user's request and context, create a detailed, vivid image generation prompt. "
        "Focus on visual elements: composition, style, colors, mood, lighting. "
        "Prefer a clear composition and avoid unnecessary micro-details unless explicitly requested. "
        "Output ONLY the image prompt text, nothing else. Max 200 words."
    )

    user_content = f"User request: {question}\n"
    if welcome_messages:
        user_content += f"\nDocument context:\n{chr(10).join(welcome_messages[:3])}\n"
    if context:
        user_content += f"\nRecent conversation:\n{context[:1000]}\n"

    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=300,
        temperature=0.8,
    )

    return response.choices[0].message.content.strip()
