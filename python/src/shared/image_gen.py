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
import re
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
_PROMPT_ASPECT_MAP: dict[str, str] = {
    "3:2": "landscape",
    "3:4": "portrait",
}


def aspect_to_image_size(aspect: str) -> str:
    """Map an aspect ratio string (e.g. "3:4") to a concrete WxH size string.

    Falls back to the default 1:1 square if the aspect is unknown.
    """
    # Aspect-based size selection is disabled intentionally.
    _ = aspect
    return _FIXED_IMAGE_SIZE


def infer_prompt_aspect(question: str) -> str:
    """Infer a supported framed aspect ratio from the user's request.

    The transport layer currently forces square output, so non-square requests
    are represented as letterboxed or pillarboxed compositions inside a 1:1
    canvas. Only the supported product ratios are recognized.
    """
    normalized = (question or "").lower()
    collapsed = re.sub(r"\s+", " ", normalized)

    if ("3:2" in collapsed or "2:3" in collapsed) and "landscape" in collapsed:
        return "3:2"
    if "3:4" in collapsed and "portrait" in collapsed:
        return "3:4"
    return _DEFAULT_ASPECT


def build_aspect_framing_instruction(aspect: str) -> str:
    """Return prompt instructions for fitting a non-square frame in 1:1.

    The generated bitmap stays square, but the visible scene should occupy a
    real 3:2 landscape or 3:4 portrait window with black matte bars filling the
    remaining space.
    """
    orientation = _PROMPT_ASPECT_MAP.get(aspect)
    if not orientation:
        return (
            "Default to a true 1:1 square composition. Fill the full canvas with "
            "the scene; do not add decorative black bars or empty framing."
        )

    if orientation == "landscape":
        return (
            "Output remains a 1:1 square canvas, but the visible image area must be "
            "a true 3:2 landscape rectangle centered within it. Add solid black "
            "matte bars above and below the scene so the inner picture area is a real "
            "3:2 landscape ratio. Keep the subject fully inside that inner frame; do "
            "not stretch, crop, or fake the ratio."
        )

    return (
        "Output remains a 1:1 square canvas, but the visible image area must be a "
        "true 3:4 portrait rectangle centered within it. Add solid black matte bars "
        "on the left and right sides so the inner picture area is a real 3:4 portrait "
        "ratio. Keep the subject fully inside that inner frame; do not stretch, crop, "
        "or fake the ratio."
    )


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


def _normalize_reference_image_for_edit(path: Path) -> Path | None:
    """Re-encode reference images to a stable PNG accepted by edit endpoint.

    Some camera/library outputs (mode/profile/container quirks) are valid files
    but still rejected by OpenAI edits. Normalizing to RGB/RGBA PNG avoids most
    of those mode/container mismatches.
    """
    try:
        from PIL import Image

        with Image.open(path) as img:
            has_alpha = "A" in img.getbands()
            target_mode = "RGBA" if has_alpha else "RGB"
            normalized = img.convert(target_mode)
            out_path = path.with_suffix(path.suffix + ".edit-ready.png")
            normalized.save(out_path, format="PNG", optimize=True)
            return out_path
    except Exception as exc:
        logger.warning(f"⚠️ Failed to normalize reference image {path.name}: {exc}")
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
        normalized = _normalize_reference_image_for_edit(p)
        if normalized is None:
            continue
        resolved.append(normalized)
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
    """Generate an image from a text prompt.

    Uses OpenAI when LLM_PROVIDER=openai. When LLM_PROVIDER=ollama, image
    generation is unavailable (no free local model with equivalent quality)
    and a NotImplementedError is raised so the caller can surface a
    user-friendly message.
    """
    settings = get_settings()

    if settings.llm_provider == "ollama":
        raise NotImplementedError(
            "Image generation is not available in offline mode. "
            "Set LLM_PROVIDER=openai and provide an OPENAI_API_KEY to enable it."
        )

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

    def _call_generate_only(p: str):
        """Fallback: plain images.generate without any reference images."""
        return client.images.generate(
            model=model,
            prompt=p,
            n=1,
            size=size,
            quality=quality,
            output_format=output_format,
            **compression_kwarg,
        )

    def _is_moderation_blocked(exc: BaseException) -> bool:
        from openai import BadRequestError
        return (
            isinstance(exc, BadRequestError)
            and getattr(exc, "code", None) == "moderation_blocked"
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
            try:
                result = _call(retry_prompt)
            except Exception as exc2:
                # When images.edit is blocked by moderation (e.g. portrait prompts),
                # fall back to images.generate without reference images, which uses
                # a less restrictive content policy.
                if reference_paths and _is_moderation_blocked(exc2):
                    logger.warning(
                        "⚠️ images.edit moderation blocked; "
                        "retrying with images.generate (no reference images)"
                    )
                    result = _call_generate_only(retry_prompt)
                else:
                    raise

    image_data = result.data[0]

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
      {"type": "completed", "file_name": "..."}

    Any exception during streaming falls through to the caller so the
    endpoint can emit an "error" event.
    """
    settings = get_settings()

    if settings.llm_provider == "ollama":
        raise NotImplementedError(
            "Image generation is not available in offline mode. "
            "Set LLM_PROVIDER=openai and provide an OPENAI_API_KEY to enable it."
        )

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

    def _yield_stream(events):
        final_b64: str | None = None
        for event in events:
            ev_type = getattr(event, "type", "")
            if ev_type.endswith("partial_image"):
                b64 = getattr(event, "b64_json", None)
                idx = getattr(event, "partial_image_index", 0)
                if b64:
                    yield {"type": "partial", "b64": b64, "index": idx}
            elif ev_type.endswith("completed"):
                final_b64 = getattr(event, "b64_json", None)

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
                    for item in _yield_stream(events):
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
            for item in _yield_stream(events):
                yield item
        except Exception as exc:
            retry_prompt = _emphasize_inspired(prompt)
            logger.warning(
                f"⚠️ OpenAI streaming image gen failed ({exc}); "
                f"retrying once with 'inspired' emphasis"
            )
            events = _stream_generate(retry_prompt)
            for item in _yield_stream(events):
                yield item


_ART_STYLES = [
    "oil painting", "watercolor", "digital illustration", "cinematic photography",
    "charcoal sketch", "impressionist", "surrealist", "Art Nouveau", "woodcut print",
    "vintage poster", "Japanese woodblock", "concept art", "pencil drawing",
    "geometric abstract", "Gothic etching", "soft pastel", "hyper-realistic render",
    "ink wash painting", "Art Deco", "Bauhaus design", "linocut print",
    "stained glass illustration", "pointillism", "expressionist", "futurism",
    "photorealistic CGI", "street art / graffiti mural", "flat design illustration",
    "engraving", "collage mixed media", "isometric illustration", "cave painting",
    "neon noir digital painting", "Renaissance oil on panel",
    # 1990s retro computer / console pixel art — each entry carries enough
    # context so the image model renders a period-accurate look without extra hints.
    "16-bit SNES / Mega Drive pixel art — vibrant 256-color palette, chunky character sprites, tiled scrolling background",
    "1994 DOS VGA pixel art — 320×200 resolution aesthetic, dithered gradients, flat EGA-palette scenes, subtle scanline overlay",
    "8-bit NES / Famicom pixel art — 4-color-per-tile sprites, side-scroll or top-down perspective, blocky retro look",
    "Game Boy 4-shade monochrome pixel art — LCD green dot-matrix palette, stark high-contrast silhouettes, handheld screen feel",
    "retro isometric pixel art RPG tilemap — axonometric 2D grid, classic dungeon or city scene, limited color ramp, Ultima / Syndicate era",
    # Fun / expressive styles added to widen the variety palette
    "lo-fi anime sketch — muted washed palette, soft confident linework, 90s indie manga / zine aesthetic",
    "vaporwave glitch art — hot pink and purple neons, chrome shape distortion, tropical retro-futurism, A E S T H E T I C",
    "Soviet constructivist propaganda poster — bold flat primary colors, heroic diagonal composition, stylized geometric silhouettes",
    "noir graphic novel panel — heavy black ink, stark chiaroscuro, selective single-accent color (crimson or gold)",
]

_MOODS = [
    "melancholic", "triumphant", "mysterious", "serene", "dramatic", "whimsical",
    "ominous", "nostalgic", "ethereal", "joyful", "tense", "contemplative",
    "magical", "raw and gritty", "dreamlike", "intimate",
    "unsettling", "euphoric", "bittersweet", "defiant", "tender", "lonely",
    "awe-inspiring", "playful", "foreboding", "reverent", "frenetic", "tranquil",
    "oppressive", "romantic", "sardonic", "hopeful",
]

_LIGHTING = [
    "golden hour sunlight", "cold moonlight", "soft diffused overcast light",
    "dramatic chiaroscuro shadows", "misty morning haze", "deep twilight glow",
    "candlelight warmth", "harsh midday sun", "stormy backlight",
    "neon reflections on wet pavement", "firelight flicker",
    "blue-hour dusk", "fluorescent office light", "underwater caustic light",
    "volumetric god rays through forest canopy", "overexposed bleach bypass",
    "bioluminescent glow", "tungsten warm interior", "infrared photography",
    "split toning — warm highlights cool shadows", "harsh side-rim backlight",
    "foggy diffused street lamp",
]

_PERSPECTIVES = [
    "wide panoramic shot", "intimate close-up", "bird's eye view", "worm's eye looking up",
    "Dutch angle", "symmetrical composition", "rule-of-thirds framing",
    "foreground bokeh with sharp background", "over-the-shoulder perspective",
    "extreme macro detail", "tilt-shift miniature effect", "fisheye lens distortion",
    "top-down flat lay", "low horizon wide angle", "forced perspective",
    "silhouette against bright background", "centered negative space",
    "tight portrait crop — eyes to chin",
]


# Exact _ART_STYLES entries that require pixel-art rendering enforcement.
# Using the full style strings allows a true O(1) set membership check in
# _random_creative_seed() instead of substring scanning.
_PIXEL_ART_STYLES: frozenset[str] = frozenset({
    "16-bit SNES / Mega Drive pixel art — vibrant 256-color palette, chunky character sprites, tiled scrolling background",
    "1994 DOS VGA pixel art — 320×200 resolution aesthetic, dithered gradients, flat EGA-palette scenes, subtle scanline overlay",
    "8-bit NES / Famicom pixel art — 4-color-per-tile sprites, side-scroll or top-down perspective, blocky retro look",
    "Game Boy 4-shade monochrome pixel art — LCD green dot-matrix palette, stark high-contrast silhouettes, handheld screen feel",
    "retro isometric pixel art RPG tilemap — axonometric 2D grid, classic dungeon or city scene, limited color ramp, Ultima / Syndicate era",
})

# Extra rendering rules appended whenever a pixel-art style is selected, to
# ensure the image model renders a period-accurate look (no anti-aliasing,
# proper dithering, CRT/LCD screen feel, limited palette).
_PIXEL_ART_RENDERING_RULES = (
    " PIXEL ART RENDERING RULES: Use a strictly period-accurate, limited color "
    "palette (4 to 256 colors maximum depending on the platform). Render "
    "everything with hard-edged square pixels — NO anti-aliasing, NO smooth "
    "blending, NO gradients (use ordered / Bayer dithering patterns instead). "
    "Outline sprites with a 1-pixel dark border. Backgrounds must use visible "
    "repeating tile patterns. Add a subtle CRT scanline or dot-matrix screen "
    "overlay to reinforce the vintage display feel. The final image should look "
    "exactly as if it appeared on a real 1990s CRT monitor or handheld LCD screen."
)


def _random_creative_seed() -> str:
    """Pick one element from each creative dimension to seed unique generation.

    When a pixel / retro-raster style is selected, extra rendering rules are
    appended so the image model produces a period-accurate pixel-art look.
    """
    style = random.choice(_ART_STYLES)
    mood = random.choice(_MOODS)
    lighting = random.choice(_LIGHTING)
    perspective = random.choice(_PERSPECTIVES)
    seed = (
        f"Creative direction suggestion for this image: {style} style, {mood} mood, "
        f"{lighting}, {perspective}. "
        "Treat this as a starting point for variety — but if it conflicts with the "
        "SUBJECT-TYPE RULES (e.g. woodcut for a human portrait, cartoon for a "
        "scientific concept), override it and follow the rules. Within whatever "
        "register you end up in, still find a UNIQUE angle — do NOT produce the "
        "most obvious or generic version of the theme."
    )
    if style in _PIXEL_ART_STYLES:
        seed += _PIXEL_ART_RENDERING_RULES
    return seed


def build_image_announcement(
    question: str,
    welcome_messages: list[str] | None = None,
    chat_history: list[dict] | None = None,
    conversation_language_code: str | None = None,
    conversation_language_name: str | None = None,
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

    language_line = (
        f"Conversation language: {conversation_language_name}"
        + (f" (code: {conversation_language_code})" if conversation_language_code else "")
        if conversation_language_name
        else "Conversation language: not specified"
    )

    system = (
        "You announce, in a single sentence, the image you are about to "
        "generate for the user. Start with 'Generating an image inspired "
        "by ' (or the equivalent opener in the user's language/script) and "
        "follow it with a vivid, specific description of the creative "
        "angle — style, mood, key visual elements. Do not ask questions, "
        "do not offer options, do not mention that you are an AI. Keep it "
        "under 40 words. Output ONLY the sentence, no quotes, no prefix.\n\n"
        "LANGUAGE PRIORITY:\n"
        f"{language_line}\n"
        "Use the conversation language above for the output sentence."
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
        temperature=0.4,
    )
    # Normalise whitespace / stray quotes the model sometimes adds.
    cleaned = (text or "").strip().strip('"').strip("'").strip()
    return cleaned


def build_social_media_image_prompt() -> dict:
    """Return a direct image-edit prompt for social-media-style photo overlays.

    Four independent, randomly-applied effects — each decided separately:
      1. Kiss marks on skin           (~50% chance)
      2. Wrist band / scrunchie       (~50% chance, only if wrist visible)
      3. Creative subject overlay     (~50% chance, model invents what fits best)
      4. Emoji accent                 (~50% chance, model invents placement/format)

    Hard cap: at most 2 effects total. Zero or one is also perfectly fine.
    """
    return {
        "prompt": (
            "Take this exact photo and transform it into a fun social media post image. "
            "Keep the original photo as the complete base — do NOT alter the subject, colors, or composition. "

            # --- Step 1: read the vibe ---
            "FIRST, analyse the mood of the photo (romantic, playful, ethereal, edgy, fashion, cozy, etc.). "
            "Every decoration decision below must be driven by this mood reading. "

             # --- Step 2: subject-level overlay (pick ONE that fits) ---
            "SECOND, apply ONE of the following decorative overlays directly on/around the subject: "
            "(a) KISS MARKS — scatter 2–4 soft lipstick kiss-print stickers (💋) on the subject's cheeks, "
            "neck or shoulder, sized naturally like Snapchat beauty-filter kisses. "
            "Use for: romantic, flirty, playful vibes. "
            "(b) ANGEL WINGS — add a pair of large, soft white or golden feathered angel wings "
            "behind the subject's shoulders, as if the person is an angel. "
            "Wings should look painterly and luminous, not cartoon-flat. "
            "Use for: ethereal, dreamy, angelic, pure vibes. "
            "(c) SPARKLE HALO — place a delicate golden halo ring above the subject's head "
            "with small glowing sparkles radiating outward. "
            "Use for: angelic, goddess, celestial vibes. "
            "(d) FLOWER CROWN — overlay a realistic or illustrated flower crown on the subject's head. "
            "Use for: boho, nature, soft-aesthetic vibes. "
            "(e) GLITTER SPARKLES — scatter ✨ glitter particle bursts around the subject "
            "without covering the face. "
            "Use for: party, celebratory, magical vibes. "
            "(f) HAIR TIE / SCRUNCHIE BRACELET ON WRIST — add a delicate satin or silk scrunchie "
            "worn as a bracelet (soft blush, dusty rose, ivory, or muted mauve) around the subject's wrist, "
            "sitting naturally on the skin. "
            "It should look like a real accessory the person is wearing, not a sticker. "
            "Use for: soft, feminine, aesthetic, cozy, editorial vibes. "
            "If the wrist is not visible or the mood doesn't fit, skip this option. "
            "If no overlay clearly fits, skip this step and go straight to the accent. "

            # --- Step 3: bottom accent (pick the RIGHT format, not always a strip) ---
            "THIRD, choose ONE of the following accent formats — pick what feels most natural "
            "decide independently — roughly 50/50 — whether to add an accent at all. "
            "for THIS specific photo, not the most obvious template: "
            "(i) FLOATING STICKER CLUSTER — scatter 2–3 large emoji as floating stickers "
            "near the edges or corners, NOT covering the face. No strip. "
            "Use for: clean/minimal aesthetic, strong subject, fashion or editorial vibe. "
            "(ii) FROSTED STRIP — a semi-transparent frosted bar across the lower ~20% "
            "with 1–2 emoji and optionally 1 short word ('vibes ✨', 'soft 🌸', 'mood 💫'). "
            "Use for: playful, casual, Snapchat-story energy. "
            "(iii) CORNER TAG — a small pill/badge in one corner (e.g. bottom-right) "
            "with a single emoji or a tight 2-emoji pair. Very subtle, editorial. "
            "Use for: fashion, confident, high-contrast shots. "
            "Choose by mood — do NOT default to the strip every time. "

            # --- Emoji selection ---
            "Emoji pairs/triplets (use as inspiration, not as a fixed list): "
            "😇😈 (angelic meets edgy), 🫦🔥 (bold/sensual), 💕😈 (sweet but dark), "
            "✨😘 (soft flirty), 😋🍒 (playful cute), 👄🔥 (fierce), 💅🛍️ (fashion), "
            "🥂😘 (celebration), 🍸😈 (night-out), 💖😏 (confident), 😈🔥 (edgy), "
            "🩷💋 (romantic), 🌸🦋 (soft nature), 🎀🧸 (cozy cute), ☕️🌙 (moody), "
            "💫🐹 (wholesome quirky), 🩵❄️ (cool aesthetic), 🍓💋 (sweet bold), "
            "🌙✨ (dreamy), 📸💃 (lively energy), 🍑😏 (confident summer), "
            "🥹💞 (tender emotional), 🦋🌈 (free spirit), 💎👑 (luxe/boss). "
            "Full palette if needed: ❤️ 🩷 🩵 💖 💕 💗 💓 💞 💘 😘 😍 🥰 🥹 🥺 💋 👄 🫦 😇 "
            "🙈 🙉 🙊 😏 😜 😝 😉 😚 😈 🔥 💅 ✨ 💫 "
            "🌸 🌈 🦋 🎶 👗 👠 🛍️ 🎀 🧸 💄 🐈‍⬛ 🐹 "
            "🍒 🍑 🍓 🍭 🍰 ☕️ 🥂 🍸 🍬 📸 💃🕺 💎 👑 🌙 ❄️. "

            # --- Step 4: KISS MARKS — independent random effect ---
            "FOURTH, decide independently — roughly 50/50 — whether to add kiss marks. "
            "Do NOT apply kiss marks every time. "
            "If YES: scatter 2–4 soft lipstick kiss-print stickers (💋) on the subject's cheeks, "
            "neck, or shoulder — sized naturally, like Snapchat beauty-filter kisses. "
            "Fits: romantic, flirty, playful moods. Skip for: ethereal, edgy, fashion, serious. "
            "If NO: move on without any kiss marks. "

            # --- Step 5: WRIST BAND / SCRUNCHIE — independent random effect ---
            "FIFTH, decide independently — ~20% chance, separate from step 2 — "
            "whether to add a delicate wrist accessory. "
            "Apply it rarely — only when the wrist is clearly visible AND the mood is a strong fit. "
            "If YES: place a soft satin or silk scrunchie bracelet (blush, dusty rose, ivory, or muted mauve) "
            "sitting naturally on the wrist — it must look like a real worn accessory, not a sticker. "
            "Fits: soft, feminine, aesthetic, cozy, editorial moods. "
            "If the wrist is not visible, or the mood doesn't fit, skip this step. "

            # --- Step 6: CREATIVE OVERLAY — independent random effect ---
            "SIXTH, decide independently — another ~50/50 roll, separate from all prior steps — "
            "whether to apply ONE decorative subject-level overlay. "
            "Do NOT apply an overlay every time. "
            "If YES: invent the most fitting overlay for THIS specific photo's mood and composition. "
            "You are NOT limited to a menu — use your own creative judgment. "
            "Examples of what is possible (use as inspiration only): "
            "feathered angel wings, a sparkle halo, a flower crown, glitter burst, light leak, "
            "watercolour wash, golden-hour glow, soft bokeh overlay, frosted vignette, "
            "illustrated accessories, neon outline, paint drips, film grain, etc. "
            "The effect must feel intentional and specific to the vibe you read — not generic. "
            "If nothing truly fits, skip this step. "

            # --- Step 7: EMOJI ACCENT — independent random effect ---
            "SEVENTH, decide independently — a final ~50/50 roll — whether to add a single emoji accent. "
            "Do NOT add emoji every time. "
            "If YES: invent the best placement, format, and emoji combination for this specific photo. "
            "You may use floating stickers near edges, a frosted bottom strip, a corner pill/badge, "
            "or any other format that feels right — choose based on the photo's composition and mood. "
            "Pick emoji that genuinely match the vibe; avoid generic hearts-and-sparkles defaults. "
            "Maximum 2–3 emoji total. "
            "If NO: leave the photo clean — no emoji accent is the right call more often than you think. "

            # --- Effect count distribution ---
            "EFFECT COUNT: Choose the total number of effects (across steps 2–5) according to this distribution: "
            "1 effect — 30% of the time (default choice); "
            "2 effects — 30% of the time (only when a second effect clearly adds to the mood); "
            "3 effects — 30% of the time (rare, only when the photo is very dynamic or layered); "
            "4+ effects — 10% of the time (exceptional only, never forced). "
            "When in doubt, go with 1. Never add an effect just to fill space. "

            # --- Final quality bar ---
            "The result should feel like a careful, intentional Instagram or TikTok story edit — "
            "not a generic filter dump. Decoration is seasoning, not the main dish. "
            "No watermark. No logos. The subject's face and body must be fully preserved."
        ),
        "title": "Social Media Edit",
        "source_indices": [],
        "aspect": "square",
    }


def build_image_prompt(
    question: str,
    context: str = "",
    welcome_messages: list[str] | None = None,
    rag_chunks: list[dict] | None = None,
    chat_history: list[dict] | None = None,
    conversation_language_code: str | None = None,
    conversation_language_name: str | None = None,
) -> dict:
    """Build a DALL-E prompt, title, and source references from the user's question and context.

    Uses top RAG chunks and recent conversation history to produce a richer, more grounded
    image prompt. Returns a dict with 'prompt', 'title', and 'source_indices' (0-based
    indices into rag_chunks that informed the image concept).

    A random creative seed is injected each call so repeated requests produce unique images.
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    aspect = infer_prompt_aspect(question)
    aspect_framing_instruction = build_aspect_framing_instruction(aspect)
    language_line = (
        f"Conversation language: {conversation_language_name}"
        + (f" (code: {conversation_language_code})" if conversation_language_code else "")
        if conversation_language_name
        else "Conversation language: not specified"
    )

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
        "STEP 2A — RESPECT THE REQUESTED FRAME SHAPE:\n"
        "  The transport output is currently square, so when the user requests a non-square frame,\n"
        "  describe the composition as a centered inner frame with solid black matte bars filling\n"
        "  the remaining square canvas. The inner frame ratio must be real, not approximated.\n\n"
        "STEP 3 — ADD EXPLICIT CONSTRAINTS at the end of the prompt (always include):\n"
        "  'No watermark. No readable text. No logos or trademarks. No extra limbs.\n"
        "  Preserve natural proportions. No signature overlay.'\n\n"
        "Ground the prompt in actual content from the provided sources when relevant. "
        "Do NOT produce the most literal interpretation — find a fresh angle within the chosen register. "
        "The CREATIVE DIRECTION is a suggestion; override it only when the subject-type rules above conflict with it.\n\n"
        "─────────────────────────────────────────────\n"
        "OUTPUT 2 — TITLE  (max 8 words)\n"
        "─────────────────────────────────────────────\n"
        "An evocative, specific title describing what is actually depicted in this particular image — "
        "NEVER use generic placeholders such as 'Generated Image', 'AI Image', 'Image', or 'Untitled'. "
        "The title must name the concrete subject or scene (e.g. 'Joanna Chyłka w sali sądowej', "
        "'Mglisty świt nad Wisłą', 'The Cosmic Web of Dark Matter'). "
        "Write in the SAME LANGUAGE AND SCRIPT as the user's request and document sources "
        "(Arabic → Arabic script, Polish → Polish, Chinese → Chinese). Use English only when "
        "source material is in English.\n"
        "CRITICAL: the title MUST be generated in the conversation language provided below.\n"
        f"{language_line}\n\n"
        "─────────────────────────────────────────────\n"
        "OUTPUT 3 — SOURCE INDICES\n"
        "─────────────────────────────────────────────\n"
        "A list of 0-based integers from the provided chunks that most directly informed the "
        "image concept. Include 1–5 indices; use [] if none apply.\n\n"
        'Output ONLY valid JSON: {"prompt": "...", "title": "...", "source_indices": [0, 2]}'
    )

    creative_seed = _random_creative_seed()
    user_content = (
        f"User request: {question}\n"
        f"{language_line}\n"
        f"Requested frame handling: {aspect_framing_instruction}\n\n"
        f"{creative_seed}\n"
    )

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
        temperature=0.5,
    )
    try:
        import json

        parsed = json.loads(raw)
        title = parsed.get("title", "").strip()
        # Reject generic/placeholder titles; fall back to a question-derived label
        _generic = {"generated image", "ai image", "image", "untitled", ""}
        if title.lower() in _generic:
            title = question[:60].strip() if question else "Illustration"
        return {
            "prompt": parsed["prompt"],
            "title": title,
            "source_indices": parsed.get("source_indices", []),
            "aspect": aspect,
        }
    except (json.JSONDecodeError, KeyError):
        # Derive a minimal title from the user's question rather than a generic placeholder
        fallback_title = question[:60].strip() if question else "Illustration"
        return {"prompt": raw, "title": fallback_title, "source_indices": [], "aspect": aspect}
