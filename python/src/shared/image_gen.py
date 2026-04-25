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

# Keep a single fixed image size while image generation is being stabilized.
# The previous aspect-ratio map is intentionally disabled for now.
# ASPECT_SIZE_MAP: dict[str, str] = {
#     "1:1":  "880x880",
#     "3:4":  "768x1024",
#     "4:3":  "1024x768",
#     "2:3":  "688x1024",
#     "3:2":  "1024x688",
#     "16:9": "1024x576",
#     "9:16": "576x1024",
# }
_DEFAULT_ASPECT = "1:1"
_FIXED_IMAGE_SIZE = "880x880"


def aspect_to_image_size(aspect: str) -> str:
    """Map an aspect ratio string (e.g. "3:4") to a concrete WxH size string.

    Falls back to the default 1:1 square if the aspect is unknown.
    """
    # Aspect-based size selection is disabled intentionally.
    _ = aspect
    return _FIXED_IMAGE_SIZE


from shared.config import get_settings
from shared.llm_instrument import traced_openai_call
from shared.otel import get_tracer

logger = logging.getLogger(__name__)


def _emphasize_inspired(prompt: str) -> str:
    """Reframe a prompt as "inspired by" so OpenAI's content filter is less
    likely to block references to copyrighted characters/scenes. If the
    prompt already mentions "inspired", prepend an extra emphasis so the
    retry request is not byte-identical to the blocked one.
    """
    if "inspired" in prompt.lower():
        return f"Inspired artwork. {prompt}"
    return f"Inspired image of: {prompt}"


def _render_pdf_cover_png(pdf_path: Path) -> Path | None:
    """Render the first page of ``pdf_path`` to a cached PNG next to it.

    The rendered cover is cached as ``<pdf>.cover.png`` so repeated image
    generations reuse the same file. Returns ``None`` if rendering fails.
    """
    cover_path = pdf_path.with_suffix(pdf_path.suffix + ".cover.png")
    if cover_path.is_file() and cover_path.stat().st_size > 0:
        return cover_path
    try:
        # Lazy import — fitz is only needed when a PDF reference is requested.
        from .extractors import _render_pdf_page_to_png

        png_bytes = _render_pdf_page_to_png(str(pdf_path), 0, dpi=150)
        cover_path.write_bytes(png_bytes)
        logger.info(f"📘 Rendered PDF cover for reference: {cover_path.name}")
        return cover_path
    except Exception as exc:
        logger.warning(f"⚠️ Failed to render PDF cover for {pdf_path.name}: {exc}")
        return None


def _validate_reference_paths(paths: list[str] | None) -> list[Path]:
    """Normalize and validate reference image paths for the edit endpoint.

    Filters out missing files, unsupported mime types, and anything above
    ``MAX_REFERENCE_IMAGES``. PDF inputs are transparently replaced with a
    rendered PNG of their first page (the "book cover"). Returns resolved
    Path objects in input order.
    """
    if not paths:
        return []

    resolved: list[Path] = []
    for raw in paths[:MAX_REFERENCE_IMAGES]:
        p = Path(raw)
        if not p.is_file():
            logger.warning(f"⚠️ Reference image not found, skipping: {raw}")
            continue
        if p.suffix.lower() == ".pdf":
            cover = _render_pdf_cover_png(p)
            if cover is None:
                continue
            p = cover
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
    output_format: str = "jpeg",
    output_compression: int = 85,
):
    """Call OpenAI images.edit with one or more reference images."""
    # output_compression is only valid for jpeg/webp — omit for png to avoid API error.
    compression_kwarg = {} if output_format == "png" else {"output_compression": output_compression}
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
            output_format=output_format,
            **compression_kwarg,
        )


def generate_image(
    prompt: str,
    storage_dir: str,
    size: str = "880x880",
    quality: str = "low",
    model: str | None = None,
    reference_image_paths: list[str] | None = None,
    output_format: str = "jpeg",
    output_compression: int = 85,
) -> dict:
    """Generate an image from a text prompt using OpenAI.

    When ``reference_image_paths`` is provided, the OpenAI ``images.edit``
    endpoint is used so the model can visually ground the generation in the
    uploaded references (style, subject, composition). Otherwise the standard
    ``images.generate`` endpoint is used.

    ``model`` defaults to ``settings.openai_image_model`` (env:
    ``OPENAI_IMAGE_MODEL``, fallback ``gpt-image-2``). gpt-image-2 accepts any
    WxH where both dimensions are multiples of 16 (range 16–4096).

    Args:
        prompt: The text description for image generation.
        storage_dir: Directory to save the generated image.
        size: Image size string "WxH" — use ``aspect_to_image_size()`` to get a
            well-formed value from an aspect ratio.
        quality: Image quality (auto, high, medium, low). "low" is fastest.
        model: OpenAI image model id; default taken from settings.
        reference_image_paths: Optional list of local paths to reference images.
            Each must be a readable png/jpeg/webp file. Capped at
            ``MAX_REFERENCE_IMAGES``.

    Returns:
        dict with 'file_name' (saved filename) and 'revised_prompt' (DALL-E's prompt).
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    model = model or settings.openai_image_model

    reference_paths = _validate_reference_paths(reference_image_paths)

    logger.info(
        f"🎨 Generating image: prompt='{prompt[:100]}...' size={size} "
        f"quality={quality} format={output_format} model={model} refs={len(reference_paths)}"
    )

    tracer = get_tracer("chatrag.image_gen")
    span_attrs = {
        "model": model,
        "size": size,
        "quality": quality,
        "reference_count": len(reference_paths),
    }

    compression_kwarg = {} if output_format == "png" else {"output_compression": output_compression}

    def _call(p: str):
        if reference_paths:
            return _call_images_edit(
                client=client,
                model=model,
                prompt=p,
                size=size,
                quality=quality,
                reference_paths=reference_paths,
                output_format=output_format,
                output_compression=output_compression,
            )
        return client.images.generate(
            model=model,
            prompt=p,
            n=1,
            size=size,
            quality=quality,
            output_format=output_format,
            **compression_kwarg,
        )

    with tracer.start_as_current_span("image.generate", attributes=span_attrs):
        try:
            result = _call(prompt)
        except Exception as exc:
            # OpenAI often blocks prompts that reference copyrighted
            # characters verbatim (e.g. "Daenerys in the Great Pyramid").
            # Reframing the prompt as "inspired by" tends to pass the
            # content filter — retry once with that emphasis before
            # surfacing the error to the caller.
            retry_prompt = _emphasize_inspired(prompt)
            logger.warning(
                f"⚠️ OpenAI image gen failed ({exc}); "
                f"retrying once with 'inspired' emphasis: '{retry_prompt[:120]}...'"
            )
            result = _call(retry_prompt)

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

    # Save to storage dir — use the correct extension for the chosen output format.
    ext = "jpg" if output_format == "jpeg" else output_format
    file_name = f"generated-{uuid.uuid4().hex[:12]}.{ext}"
    os.makedirs(storage_dir, exist_ok=True)
    file_path = Path(storage_dir) / file_name
    file_path.write_bytes(image_bytes)

    logger.info(f"🖼️ Image saved: {file_path} ({len(image_bytes)} bytes)")

    return {
        "file_name": file_name,
        "revised_prompt": revised_prompt,
    }


def generate_image_streaming(
    prompt: str,
    storage_dir: str,
    size: str = "880x880",
    quality: str = "low",
    model: str | None = None,
    reference_image_paths: list[str] | None = None,
    # 3 partial frames gives the morph animation enough stages to look smooth
    # and, crucially, makes the FIRST intermediate arrive at ~25% of generation
    # time instead of ~50% (which is where a single partial lands).  More frames
    # earlier = morph starts sooner and has more visible sharpening steps.
    partial_images: int = 3,
    output_format: str = "jpeg",
    output_compression: int = 85,
):
    """Streaming variant of ``generate_image`` that yields progressive frames.

    Uses OpenAI's ``stream=True, partial_images=N`` parameters to surface
    intermediate lower-fidelity frames while the final render is still being
    computed. When reference images are provided, we first try streaming
    ``images.edit``. If the runtime/account does not support edit streaming,
    we gracefully fall back to the blocking edit path.

    Yields dicts of shape:
      {"type": "partial", "b64": "...", "index": 0|1|...}
      {"type": "completed", "file_name": "...", "revised_prompt": "..."}

    Any exception during streaming falls through to the caller so the
    endpoint can emit an "error" event.
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    model = model or settings.openai_image_model
    stream_model = model

    # Morphing in the UI depends on streamed partial frames. If the runtime
    # model is set to gpt-image-1, switch the streaming request to gpt-image-2
    # because gpt-image-1 may not emit partial-image events.
    if stream_model == "gpt-image-1":
        logger.info(
            "ℹ️ Switching streaming model from gpt-image-1 to gpt-image-2 to enable partial frames"
        )
        stream_model = "gpt-image-2"

    reference_paths = _validate_reference_paths(reference_image_paths)

    logger.info(
        f"🎨 Streaming image: prompt='{prompt[:100]}...' size={size} "
        f"quality={quality} format={output_format} model={stream_model} partials={partial_images}"
    )

    _ext = "jpg" if output_format == "jpeg" else output_format
    _compression_kwarg = {} if output_format == "png" else {"output_compression": output_compression}

    def _yield_stream(events, default_prompt: str):
        final_b64: str | None = None
        revised_prompt = default_prompt
        for event in events:
            ev_type = getattr(event, "type", "")
            if ev_type.endswith("partial_image"):
                b64 = getattr(event, "b64_json", None)
                idx = getattr(event, "partial_image_index", 0)
                if b64:
                    yield {"type": "partial", "b64": b64, "index": idx}
            elif ev_type.endswith("completed"):
                final_b64 = getattr(event, "b64_json", None)
                revised_prompt = getattr(event, "revised_prompt", default_prompt) or default_prompt

        if not final_b64:
            raise ValueError("OpenAI streaming image response contained no final frame")

        image_bytes = base64.b64decode(final_b64)
        file_name = f"generated-{uuid.uuid4().hex[:12]}.{_ext}"
        os.makedirs(storage_dir, exist_ok=True)
        file_path = Path(storage_dir) / file_name
        file_path.write_bytes(image_bytes)

        logger.info(f"🖼️ Streamed image saved: {file_path} ({len(image_bytes)} bytes)")
        yield {
            "type": "completed",
            "file_name": file_name,
            "revised_prompt": revised_prompt,
        }

    tracer = get_tracer("chatrag.image_gen")
    span_attrs = {
        "model": stream_model,
        "size": size,
        "quality": quality,
        "streaming": True,
        "partial_images": partial_images,
    }

    with tracer.start_as_current_span("image.generate.stream", attributes=span_attrs):
        if reference_paths:
            logger.info(f"🎬 Streaming with {len(reference_paths)} reference image(s)")
            try:
                with contextlib.ExitStack() as stack:
                    handles = [stack.enter_context(open(p, "rb")) for p in reference_paths]
                    image_arg = handles[0] if len(handles) == 1 else handles
                    events = client.images.edit(
                        model=stream_model,
                        image=image_arg,
                        prompt=prompt,
                        n=1,
                        size=size,
                        quality=quality,
                        output_format=output_format,
                        **_compression_kwarg,
                        stream=True,
                        partial_images=partial_images,
                    )
                    for item in _yield_stream(events, prompt):
                        logger.debug(f"📸 Streaming edit event: {item.get('type')}")
                        yield item
                return
            except Exception as exc:
                logger.warning(
                    f"⚠️ Streaming edit unavailable ({exc}); falling back to blocking edit"
                )
                result = generate_image(
                    prompt=prompt,
                    storage_dir=storage_dir,
                    size=size,
                    quality=quality,
                    model=stream_model,
                    reference_image_paths=reference_image_paths,
                )
                yield {
                    "type": "completed",
                    "file_name": result["file_name"],
                    "revised_prompt": result["revised_prompt"],
                }
                return

        def _stream_generate(p: str):
            return client.images.generate(
                model=stream_model,
                prompt=p,
                n=1,
                size=size,
                quality=quality,
                output_format=output_format,
                **_compression_kwarg,
                stream=True,
                partial_images=partial_images,
            )

        try:
            events = _stream_generate(prompt)
            for item in _yield_stream(events, prompt):
                yield item
        except Exception as exc:
            retry_prompt = _emphasize_inspired(prompt)
            logger.warning(
                f"⚠️ OpenAI streaming image gen failed ({exc}); "
                f"retrying once with 'inspired' emphasis"
            )
            events = _stream_generate(retry_prompt)
            for item in _yield_stream(events, retry_prompt):
                yield item


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


def build_image_announcement(
    question: str,
    welcome_messages: list[str] | None = None,
    chat_history: list[dict] | None = None,
) -> str:
    """Produce a short one-sentence teaser shown to the user while the
    image is being generated.

    Kept intentionally lightweight — no RAG lookup, no image API — so the
    frontend can display it almost immediately while the heavier
    ``generate_image`` flow runs in parallel. Returned string is always a
    single sentence, matches the user's language/script, and describes the
    intended creative angle (e.g. "Generating an image inspired by Harry
    Potter — a magical book-cover-style scene with Hogwarts glow …").
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    system = (
        "You announce, in a single sentence, the image you are about to "
        "generate for the user. Start with 'Generating an image inspired "
        "by ' (or the equivalent opener in the user's language/script) and "
        "follow it with a vivid, specific description of the creative "
        "angle — style, mood, key visual elements. Do not ask questions, "
        "do not offer options, do not mention that you are an AI. Keep it "
        "under 40 words. Output ONLY the sentence, no quotes, no prefix."
    )

    user_content = f"User request: {question}\n"
    if welcome_messages:
        user_content += f"\nDocument summary:\n{chr(10).join(welcome_messages[:2])}\n"
    if chat_history:
        user_content += "\nRecent conversation:\n"
        for msg in chat_history[-4:]:
            role = msg.get("role", "")
            content = (msg.get("content", "") or "")[:200]
            user_content += f"{role}: {content}\n"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    text, _usage = traced_openai_call(
        client=client,
        messages=messages,
        model=settings.openai_chat_model,
        operation="image_announcement",
        max_completion_tokens=120,
        temperature=0.7,
    )
    # Normalise whitespace / stray quotes the model sometimes adds.
    cleaned = (text or "").strip().strip('"').strip("'").strip()
    return cleaned


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
        "You are an expert prompt engineer for gpt-image-2, an AI image generation model. "
        "Given the user's request, document sources, conversation history, and the CREATIVE DIRECTION, produce:\n\n"
        "─────────────────────────────────────────────\n"
        "OUTPUT 1 — IMAGE PROMPT  (max 200 words)\n"
        "─────────────────────────────────────────────\n"
        "Structure the prompt in this fixed order:\n"
        "  [SCENE/BACKGROUND] → [SUBJECT] → [KEY DETAILS] → [COMPOSITION] → [CONSTRAINTS]\n\n"
        "STEP 1 — CLASSIFY the subject and choose a visual register:\n"
        "• People, portraits, real individuals, biographies, interviews, medical/anatomy →\n"
        "  Include the word 'photorealistic' at the start of the prompt. Describe natural skin\n"
        "  texture, hair detail, anatomically correct proportions. Add lighting type: softbox,\n"
        "  natural window light, or cinematic key light. State body framing explicitly\n"
        "  ('waist-up', 'full body visible, feet included', etc.). For gaze, say what the\n"
        "  subject is looking at ('looking slightly off-camera, not directly at viewer').\n"
        "  Avoid cartoon, caricature, or heavy stylization unless explicitly requested.\n"
        "• Books, novels, fiction, screenplays, films →\n"
        "  Cinematic film-still aesthetic. Wide anamorphic framing or medium shot, shallow depth\n"
        "  of field, 35mm film grain, moody color grading (teal-and-orange, desaturated tones,\n"
        "  or high-contrast chiaroscuro). Describe set-dressing materials (worn leather, cracked\n"
        "  plaster, heavy velvet) and atmosphere (smoky haze, rain on glass, candlelight flicker).\n"
        "• Poetry, philosophy, dreams, emotions, abstract ideas →\n"
        "  Abstract or symbolic composition. Describe flowing or geometric forms, a dominant\n"
        "  color palette (two or three specific hues), and the emotional register\n"
        "  (melancholic, euphoric, uncanny). Reference a visual medium: oil impasto,\n"
        "  impressionist brushstrokes, or surrealist digital painting.\n"
        "• Science, cosmos, space, physics, math, biology →\n"
        "  Abstract scientific visualization. Name specific elements: nebulae with specific\n"
        "  color cast, particle field density, luminous geometry on dark background,\n"
        "  macro/micro scale indicator. Add quality lever: macro detail, luminous glows.\n"
        "• History, historical figures, ancient civilizations →\n"
        "  Period-appropriate style with named technique (Renaissance oil on canvas,\n"
        "  sepia daguerreotype with vignette, Dutch Golden Age side-lighting).\n"
        "• Food, recipes, cooking →\n"
        "  Overhead or 45° three-quarter shot. Shallow depth of field, natural diffuse light,\n"
        "  rustic wooden or marble surface. Name textures (glossy glaze, charred crust,\n"
        "  steam wisps).\n"
        "• Nature, landscapes, travel, architecture →\n"
        "  Specify time of day and light quality (golden hour, blue-hour twilight, overcast\n"
        "  diffuse). Name atmosphere cues (mist in the valley, rain-slicked cobblestones,\n"
        "  neon reflections). Include scale reference if scene is wide or cinematic.\n"
        "• Technology, code, UI, diagrams →\n"
        "  Clean isometric illustration or flat minimalist digital art. No readable labels\n"
        "  or text anywhere in the scene. Name color palette (muted pastels, cyberpunk neons).\n"
        "• Children's books, fairy tales, whimsical →\n"
        "  Storybook illustration style. Watercolor wash or soft digital painting, warm palette,\n"
        "  gentle rounded forms.\n\n"
        "STEP 2 — ADD COMPOSITION details:\n"
        "  Framing/viewpoint: close-up | medium shot | wide | top-down | low-angle | eye-level\n"
        "  Perspective: describe camera angle and distance from subject.\n"
        "  Lighting/mood: name the light source and quality (soft diffuse, harsh rim, golden hour).\n"
        "  Layout (if relevant): placement of key element ('subject centered with negative space\n"
        "  on left', 'horizon line at lower third', 'logo top-right').\n\n"
        "STEP 3 — ADD EXPLICIT CONSTRAINTS at the end of the prompt (always include):\n"
        "  'No watermark. No readable text. No logos or trademarks. No extra limbs.\n"
        "  Preserve natural proportions. No signature overlay.'\n\n"
        "Ground the prompt in actual content from the provided sources when relevant. "
        "Do NOT produce the most literal interpretation — find a fresh angle within the chosen register. "
        "The CREATIVE DIRECTION is a suggestion; override it only when the subject-type rules above conflict with it.\n\n"
        "─────────────────────────────────────────────\n"
        "OUTPUT 2 — TITLE  (max 8 words)\n"
        "─────────────────────────────────────────────\n"
        "An evocative title reflecting the specific creative angle — NOT a generic description. "
        "Write in the SAME LANGUAGE AND SCRIPT as the user's request and document sources "
        "(Arabic → Arabic script, Polish → Polish, Chinese → Chinese). Use English only when "
        "source material is in English.\n\n"
        "─────────────────────────────────────────────\n"
        "OUTPUT 3 — SOURCE INDICES\n"
        "─────────────────────────────────────────────\n"
        "A list of 0-based integers from the provided chunks that most directly informed the "
        "image concept. Include 1–5 indices; use [] if none apply.\n\n"
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
        # The structured prompt we generate is concise; 350 tokens is sufficient
        # and cuts prompt-builder latency noticeably vs the old 500-token limit.
        max_completion_tokens=350,
        temperature=0.9,
    )
    try:
        import json

        parsed = json.loads(raw)
        return {
            "prompt": parsed["prompt"],
            "title": parsed.get("title", "Generated Image"),
            "source_indices": parsed.get("source_indices", []),
            "aspect": _DEFAULT_ASPECT,
        }
    except (json.JSONDecodeError, KeyError):
        return {"prompt": raw, "title": "Generated Image", "source_indices": [], "aspect": _DEFAULT_ASPECT}
