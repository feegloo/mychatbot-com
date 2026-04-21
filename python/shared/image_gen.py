"""Image generation via OpenAI DALL-E API.

Generates images from text descriptions and saves them to the conversation's
storage directory so they can be served via the existing /api/storage/ route.
"""

from __future__ import annotations

import base64
import contextlib
import logging
import mimetypes
import os
import random
import uuid
from pathlib import Path

import requests
from openai import OpenAI

# gpt-image-1 edit endpoint currently accepts at most 10 reference images;
# we cap much lower to keep request size sane.
MAX_REFERENCE_IMAGES = 4
# OpenAI edits endpoint accepts png/jpeg/webp for gpt-image-1.
_ALLOWED_REFERENCE_MIME = {"image/png", "image/jpeg", "image/webp"}

from shared.config import get_settings
from shared.llm_instrument import traced_openai_call
from shared.otel import get_tracer

logger = logging.getLogger(__name__)


def _validate_reference_paths(paths: list[str] | None) -> list[Path]:
    """Normalize and validate reference image paths for the edit endpoint.

    Filters out missing files, unsupported mime types, and anything above
    ``MAX_REFERENCE_IMAGES``. Returns resolved Path objects in input order.
    """
    if not paths:
        return []

    resolved: list[Path] = []
    for raw in paths[:MAX_REFERENCE_IMAGES]:
        p = Path(raw)
        if not p.is_file():
            logger.warning(f"⚠️ Reference image not found, skipping: {raw}")
            continue
        mime, _ = mimetypes.guess_type(p.name)
        if mime not in _ALLOWED_REFERENCE_MIME:
            logger.warning(
                f"⚠️ Unsupported reference image mime '{mime}' for {p.name}, skipping"
            )
            continue
        resolved.append(p)
    return resolved


def _call_images_edit(
    *,
    client: OpenAI,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    reference_paths: list[Path],
):
    """Call OpenAI images.edit with one or more reference images."""
    with contextlib.ExitStack() as stack:
        handles = [stack.enter_context(open(p, "rb")) for p in reference_paths]
        image_arg = handles[0] if len(handles) == 1 else handles
        return client.images.edit(
            model=model,
            image=image_arg,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )


def generate_image(
    prompt: str,
    storage_dir: str,
    size: str = "1024x1024",
    quality: str = "low",
    model: str = "gpt-image-1",
    reference_image_paths: list[str] | None = None,
) -> dict:
    """Generate an image from a text prompt using OpenAI.

    When ``reference_image_paths`` is provided, the OpenAI ``images.edit``
    endpoint is used so the model can visually ground the generation in the
    uploaded references (style, subject, composition). Otherwise the standard
    ``images.generate`` endpoint is used.

    Args:
        prompt: The text description for image generation.
        storage_dir: Directory to save the generated image.
        size: Image size (1024x1024, 1024x1792, 1792x1024).
        quality: Image quality (auto, high, low).
        model: OpenAI image model to use.
        reference_image_paths: Optional list of local paths to reference images.
            Each must be a readable png/jpeg/webp file. Capped at
            ``MAX_REFERENCE_IMAGES``.

    Returns:
        dict with 'file_name' (saved filename) and 'revised_prompt' (DALL-E's prompt).
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    reference_paths = _validate_reference_paths(reference_image_paths)

    logger.info(
        f"🎨 Generating image: prompt='{prompt[:100]}...' size={size} "
        f"quality={quality} model={model} refs={len(reference_paths)}"
    )

    tracer = get_tracer("chatrag.image_gen")
    span_attrs = {
        "model": model,
        "size": size,
        "quality": quality,
        "reference_count": len(reference_paths),
    }
    with tracer.start_as_current_span("image.generate", attributes=span_attrs):
        if reference_paths:
            result = _call_images_edit(
                client=client,
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                reference_paths=reference_paths,
            )
        else:
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
        f"Creative direction suggestion for this image: {style} style, {mood} mood, "
        f"{lighting}, {perspective}. "
        "Treat this as a starting point for variety — but if it conflicts with the "
        "SUBJECT-TYPE RULES (e.g. woodcut for a human portrait, cartoon for a "
        "scientific concept), override it and follow the rules. Within whatever "
        "register you end up in, still find a UNIQUE angle — do NOT produce the "
        "most obvious or generic version of the theme."
    )


def build_image_prompt(
    question: str,
    context: str = "",
    welcome_messages: list[str] | None = None,
    rag_chunks: list[dict] | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """Build a DALL-E prompt, title, and source references from the user's question and context.

    Uses top RAG chunks and recent conversation history to produce a richer, more grounded
    image prompt. Returns a dict with 'prompt', 'title', and 'source_indices' (0-based
    indices into rag_chunks that informed the image concept).

    A random creative seed is injected each call so repeated requests produce unique images.
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    system = (
        "You are an expert prompt engineer for AI image generation. "
        "Given the user's request, document sources, conversation history, and the CREATIVE DIRECTION, create:\n"
        "1. A detailed, vivid image generation prompt (max 200 words). "
        "FIRST classify the subject, then pick a visual register that fits it. "
        "The CREATIVE DIRECTION is a suggestion — override any element of it that "
        "clashes with the subject-type rules below.\n\n"
        "SUBJECT-TYPE RULES (these take precedence over the creative direction):\n"
        "• People, portraits, real individuals, biographies, interviews, medical/anatomy → "
        "photorealistic photography. Natural skin, anatomically correct proportions, realistic "
        "lighting (softbox, natural light, cinematic key light). Avoid cartoon, caricature, "
        "surreal distortion, or heavy stylization unless the user explicitly asks for it.\n"
        "• Books, novels, stories, chapters, fiction, screenplays, films → cinematic film-still "
        "aesthetic. Think wide anamorphic framing, teal-and-orange or moody color grading, "
        "shallow depth of field, production-design detail, 35mm film grain.\n"
        "• Poetry, song lyrics, creative writing, philosophy, dreams, emotions, abstract ideas → "
        "abstract, surreal, or symbolic imagery. Flowing forms, metaphorical composition, "
        "impressionist or surrealist style, evocative color palettes.\n"
        "• Science, cosmos, space, physics, math, biology at a conceptual level → abstract "
        "scientific visualization. Nebulae, particle fields, data-art, luminous geometry, "
        "macro/micro imagery, dark backgrounds with vibrant accents.\n"
        "• History, historical figures, ancient civilizations → period-appropriate painting or "
        "photograph style (e.g., Renaissance oil, sepia daguerreotype, Dutch Golden Age).\n"
        "• Food, recipes, cooking → realistic overhead or three-quarter food photography with "
        "natural light, shallow depth of field, rustic props.\n"
        "• Nature, landscapes, travel, architecture → cinematic photography or impressionist "
        "painting; emphasize atmosphere and scale.\n"
        "• Technology, code, UI, diagrams → clean isometric illustration or minimalist "
        "digital art; avoid realism of text (generate no readable text).\n"
        "• Children's books, fairy tales, whimsical → storybook illustration, watercolor, or "
        "soft digital painting.\n\n"
        "Ground the image in the actual content from the provided sources when relevant. "
        "Focus on visual elements: composition, style, colors, mood, lighting. "
        "Never render readable text, logos, or watermarks in the image. "
        "Do NOT produce the most literal or predictable interpretation of the subject — "
        "within the register the rules dictate, still find a fresh angle.\n"
        "2. A short, evocative title for the image (max 8 words) that reflects the "
        "specific creative angle chosen — NOT a generic description of the subject.\n"
        "3. A list of source indices (0-based integers) from the provided chunks that "
        "most directly informed the image concept. Include 1–5 indices; use [] if none apply.\n\n"
        'Output ONLY valid JSON: {"prompt": "...", "title": "...", "source_indices": [0, 2]}'
    )

    creative_seed = _random_creative_seed()
    user_content = f"User request: {question}\n\n{creative_seed}\n"

    if welcome_messages:
        user_content += f"\nDocument summary:\n{chr(10).join(welcome_messages[:3])}\n"

    # Include top RAG chunks as numbered source passages
    if rag_chunks:
        user_content += "\nRelevant document passages (use source_indices to cite which ones informed the image):\n"
        for i, chunk in enumerate(rag_chunks[:10]):
            file_label = chunk.get("file_name", "")
            page = chunk.get("page")
            loc = f" (p.{page})" if page else ""
            user_content += f"\n[{i}] {file_label}{loc}:\n{chunk.get('text', '')[:600]}\n"

    # Include recent conversation history (last 6 exchanges) for context continuity
    if chat_history:
        user_content += "\nRecent conversation:\n"
        for msg in chat_history[-6:]:
            role = msg.get("role", "")
            content = msg.get("content", "")[:400]
            user_content += f"{role}: {content}\n"
    elif context:
        # Fallback to the pre-formatted context string
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
        max_completion_tokens=500,
        temperature=1.0,
    )
    try:
        import json

        parsed = json.loads(raw)
        return {
            "prompt": parsed["prompt"],
            "title": parsed.get("title", "Generated Image"),
            "source_indices": parsed.get("source_indices", []),
        }
    except (json.JSONDecodeError, KeyError):
        return {"prompt": raw, "title": "Generated Image", "source_indices": []}
