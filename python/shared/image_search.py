"""Reverse image search via Google Cloud Vision API (Web Detection).

Uses the official google-cloud-vision client library with Application
Default Credentials (ADC).  Set GOOGLE_APPLICATION_CREDENTIALS in .env
pointing to the JSON credentials file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .llm_instrument import traced_openai_call

logger = logging.getLogger(__name__)


def _credentials_available() -> bool:
    """Check if GOOGLE_APPLICATION_CREDENTIALS points to an existing file."""
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not creds:
        return False
    # Resolve relative paths from the python/ directory
    p = Path(creds)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / creds
    return p.exists()


def reverse_image_search(image_path: str) -> dict | None:
    """Send an image to Google Cloud Vision API Web Detection.

    Returns a dict with:
      - web_entities: [{description, score}]
      - pages_with_matching_images: [{url, page_title}]
      - full_matching_images: [{url}]
      - visually_similar_images: [{url}]
      - best_guess_labels: [str]

    Returns None if credentials are not configured or the call fails.
    """
    logger.info(f"🔍 reverse_image_search called for: {image_path}")
    if not _credentials_available():
        creds_env = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        logger.info(
            f"⏭️  GOOGLE_APPLICATION_CREDENTIALS not set "
            f"or file missing (env='{creds_env}'), "
            f"skipping reverse image search"
        )
        return None

    p = Path(image_path)
    if not p.exists():
        logger.warning(f"Image file not found: {image_path}")
        return None
    logger.info(f"📁 Image file exists, size={p.stat().st_size} bytes")

    try:
        from google.cloud import vision
    except ImportError:
        logger.warning("⚠️  google-cloud-vision not installed, skipping reverse image search")
        return None

    try:
        logger.info("📡 Calling Google Vision API web_detection...")
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=p.read_bytes())
        response = client.web_detection(image=image, timeout=5.0)
        logger.info("✅ Google Vision API call completed")
    except Exception as e:
        logger.warning(f"⚠️  Google Vision API call failed: {type(e).__name__}: {e}")
        return None

    if response.error.message:
        logger.warning(f"⚠️  Vision API error: {response.error.message}")
        return None

    web = response.web_detection
    if not web:
        logger.info("⚠️  Vision API returned no web_detection data")
        return None

    result: dict[str, Any] = {}

    # Web entities (people, places, things identified)
    result["web_entities"] = [
        {"description": e.description, "score": round(e.score, 3)}
        for e in web.web_entities
        if e.description
    ]

    # Pages containing this image
    result["pages_with_matching_images"] = [
        {"url": pg.url, "page_title": pg.page_title or ""}
        for pg in web.pages_with_matching_images[:5]
    ]

    # Full matching images
    result["full_matching_images"] = [{"url": m.url} for m in web.full_matching_images[:5]]

    # Visually similar images
    result["visually_similar_images"] = [{"url": s.url} for s in web.visually_similar_images[:5]]

    # Best guess labels
    result["best_guess_labels"] = [lb.label for lb in web.best_guess_labels if lb.label]

    logger.info(
        f"🔍 Web detection: {len(result['web_entities'])} entities, "
        f"{len(result['pages_with_matching_images'])} pages, "
        f"labels={result['best_guess_labels']}"
    )

    return result


def identify_from_web_results(
    web_results: dict,
    image_description: str = "",
    exif_metadata: dict | None = None,
) -> dict | None:
    """Use LLM to identify a person/subject from combined context.

    Combines:
    - Google Vision web detection results
    - AI-generated image description (welcome message)
    - EXIF metadata (camera, date, GPS, etc.)

    Returns a dict with identified_name, confidence, and reasoning.
    Returns None if no meaningful identification could be made.
    """
    from openai import OpenAI

    from .config import get_settings

    logger.info(
        f"🧠 identify_from_web_results called: "
        f"web_results={'present' if web_results else 'None'}, "
        f"image_description={len(image_description or '')} chars, "
        f"exif_metadata={'present' if exif_metadata else 'None'}"
    )
    if not web_results and not image_description and not exif_metadata:
        logger.info("⚠️  No context available for identification, returning None")
        return None

    # Build context sections
    context_parts = []

    # 1. EXIF metadata context
    if exif_metadata:
        exif_lines = []
        for key in (
            "camera_make",
            "camera_model",
            "date_taken",
            "gps_latitude",
            "gps_longitude",
            "gps_altitude",
            "artist",
            "copyright",
            "description",
            "software",
            "lens_model",
        ):
            if key in exif_metadata:
                exif_lines.append(f"- {key}: {exif_metadata[key]}")
        if exif_lines:
            context_parts.append("EXIF metadata from image file:\n" + "\n".join(exif_lines))

    # 2. AI-generated description of the image
    if image_description:
        context_parts.append(f"AI description of the image: {image_description}")

    # 3. Google Vision web detection results
    if web_results:
        labels = web_results.get("best_guess_labels", [])
        entities = web_results.get("web_entities", [])
        pages = web_results.get("pages_with_matching_images", [])

        if labels:
            context_parts.append(f"Best guess labels: {', '.join(labels)}")
        if entities:
            entity_strs = [f"- {e['description']} (score: {e['score']})" for e in entities[:8]]
            context_parts.append("Web entities found:\n" + "\n".join(entity_strs))
        if pages:
            page_strs = [
                f"- {pg['page_title']} ({pg['url']})" for pg in pages[:5] if pg["page_title"]
            ]
            if page_strs:
                context_parts.append("Pages with matching image:\n" + "\n".join(page_strs))

    if not context_parts:
        return None

    combined_context = "\n\n".join(context_parts)

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    prompt = f"""Based on all available evidence about this image, identify the person or subject.

Available context:
{combined_context}

Respond with ONLY valid JSON (no markdown). Format:
{{"identified_name": "Full Name or Subject",
"confidence": "high/medium/low",
"category": "person/place/artwork/product/other",
"reasoning": "brief explanation"}}

If the results are too ambiguous or there's not enough evidence, respond with:
{{"identified_name": null, "confidence": "low",
"category": "unknown", "reasoning": "explanation"}}"""

    try:
        logger.info(f"🤖 Calling OpenAI {settings.openai_chat_model} for identification...")
        logger.info(f"📝 LLM prompt context length: {len(combined_context)} chars")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an image identification assistant. "
                    "Analyze web search results to identify "
                    "people, places, or subjects. Be precise "
                    "and honest about confidence levels."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        text, _usage = traced_openai_call(
            client=client,
            messages=messages,
            model=settings.openai_chat_model,
            operation="image_identify",
            max_completion_tokens=200,
        )
        logger.info(f"🤖 LLM raw response: {text[:500]}")
        result = json.loads(text)
        if result.get("identified_name"):
            logger.info(
                f"🎯 Identified: {result['identified_name']} ({result.get('confidence', '?')})"
            )
        else:
            logger.info(
                f"🎯 No identification - "
                f"confidence={result.get('confidence')}, "
                f"reasoning={result.get('reasoning', '')}"
            )
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️  LLM returned invalid JSON: {e}. Raw text: {text[:500]}")
        return None
    except Exception as e:
        logger.warning(f"⚠️  LLM identification failed: {type(e).__name__}: {e}")
        return None
