"""Image generation via OpenAI DALL-E API.

Generates images from text descriptions and saves them to the conversation's
storage directory so they can be served via the existing /api/storage/ route.
"""

from __future__ import annotations

import base64
import logging
import os
import random
import uuid
from pathlib import Path

import requests
from openai import OpenAI

from shared.config import get_settings
from shared.llm_instrument import traced_openai_call
from shared.otel import get_tracer

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

    tracer = get_tracer("chatrag.image_gen")
    with tracer.start_as_current_span("image.generate", attributes={"model": model, "size": size, "quality": quality}):
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


_ART_STYLES = [
    "oil painting", "watercolor", "digital illustration", "cinematic photography",
    "charcoal sketch", "impressionist", "surrealist", "Art Nouveau", "woodcut print",
    "neon noir", "vintage poster", "Japanese woodblock", "concept art", "pencil drawing",
    "geometric abstract", "Gothic etching", "soft pastel", "hyper-realistic render",
]

_MOODS = [
    "melancholic", "triumphant", "mysterious", "serene", "dramatic", "whimsical",
    "ominous", "nostalgic", "ethereal", "joyful", "tense", "contemplative",
    "magical", "raw and gritty", "dreamlike", "intimate",
]

_LIGHTING = [
    "golden hour sunlight", "cold moonlight", "soft diffused overcast light",
    "dramatic chiaroscuro shadows", "misty morning haze", "deep twilight glow",
    "candlelight warmth", "harsh midday sun", "stormy backlight", "aurora borealis",
    "neon reflections on wet pavement", "firelight flicker",
]

_PERSPECTIVES = [
    "wide panoramic shot", "intimate close-up", "bird's eye view", "worm's eye looking up",
    "Dutch angle", "symmetrical composition", "rule-of-thirds framing",
    "foreground bokeh with sharp background", "over-the-shoulder perspective",
]


def _random_creative_seed() -> str:
    """Pick one element from each creative dimension to seed unique generation."""
    style = random.choice(_ART_STYLES)
    mood = random.choice(_MOODS)
    lighting = random.choice(_LIGHTING)
    perspective = random.choice(_PERSPECTIVES)
    return (
        f"Creative direction for this specific image: {style} style, {mood} mood, "
        f"{lighting}, {perspective}. "
        "Use this direction to craft a UNIQUE title and visual interpretation — "
        "do NOT produce the most obvious or generic version of the theme."
    )


def build_image_prompt(
    question: str,
    context: str = "",
    welcome_messages: list[str] | None = None,
) -> dict:
    """Build a DALL-E prompt and short title from the user's question and context.

    Returns dict with 'prompt' (detailed visual prompt) and 'title' (short image title).
    A random creative seed is injected each call so repeated requests for the same
    topic produce meaningfully different images and titles.
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    system = (
        "You are an expert prompt engineer for AI image generation. "
        "Given the user's request, context, and the CREATIVE DIRECTION provided, create:\n"
        "1. A detailed, vivid image generation prompt (max 200 words). "
        "Follow the creative direction — style, mood, lighting, and perspective — closely. "
        "Focus on visual elements: composition, style, colors, mood, lighting. "
        "Do NOT produce the most literal or predictable interpretation of the subject.\n"
        "2. A short, evocative title for the image (max 8 words) that reflects the "
        "specific creative angle chosen — NOT a generic description of the subject.\n\n"
        'Output ONLY valid JSON: {"prompt": "...", "title": "..."}'
    )

    creative_seed = _random_creative_seed()
    user_content = f"User request: {question}\n\n{creative_seed}\n"
    if welcome_messages:
        user_content += f"\nDocument context:\n{chr(10).join(welcome_messages[:3])}\n"
    if context:
        user_content += f"\nRecent conversation:\n{context[:1000]}\n"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    raw, _usage = traced_openai_call(
        client=client,
        messages=messages,
        model=settings.openai_chat_model,
        operation="image_prompt_build",
        max_completion_tokens=400,
        temperature=1.0,
    )
    try:
        import json

        parsed = json.loads(raw)
        return {
            "prompt": parsed["prompt"],
            "title": parsed.get("title", "Generated Image"),
        }
    except (json.JSONDecodeError, KeyError):
        return {"prompt": raw, "title": "Generated Image"}
