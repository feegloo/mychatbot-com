"""Short instrumental music generation via Replicate (Meta MusicGen).

Generates 3–10 second music clips from a text prompt and saves them to
the conversation's storage directory. Mirrors the pattern used by
``video_gen.py`` and ``image_gen.py``.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

import requests

from shared.config import get_settings
from shared.otel import get_tracer
from shared.video_gen import _create_prediction, _poll_prediction, _extract_output_url

logger = logging.getLogger(__name__)


# MusicGen melody-large has the best quality/speed balance for short clips.
DEFAULT_MUSIC_MODEL = os.getenv("REPLICATE_MUSIC_MODEL", "meta/musicgen")
MIN_DURATION_S = 3
MAX_DURATION_S = 10
DEFAULT_DURATION_S = 6


def _clamp_duration(seconds: float | int | None) -> int:
    if seconds is None:
        return DEFAULT_DURATION_S
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return DEFAULT_DURATION_S
    return max(MIN_DURATION_S, min(MAX_DURATION_S, s))


def generate_music(
    prompt: str,
    storage_dir: str,
    duration_seconds: int | None = None,
    model: str = DEFAULT_MUSIC_MODEL,
) -> dict:
    """Generate a short music clip from a text prompt using Replicate MusicGen.

    Args:
        prompt: Musical description (genre, mood, instruments, tempo).
        storage_dir: Directory to save the resulting audio file.
        duration_seconds: Requested clip length, clamped to [3, 10].
        model: Replicate model slug.

    Returns:
        dict with 'file_name' (saved file) and 'duration_seconds' (requested).
    """
    duration = _clamp_duration(duration_seconds)

    logger.info(
        f"🎵 Generating music: prompt='{prompt[:100]}...' duration={duration}s model={model}"
    )

    tracer = get_tracer("chatrag.music_gen")
    with tracer.start_as_current_span(
        "music.generate", attributes={"model": model, "duration_seconds": duration}
    ):
        # MusicGen canonical inputs: prompt (aka "text"), duration,
        # output_format (mp3 recommended for web playback).
        payload = {
            "prompt": prompt,
            "duration": duration,
            "output_format": "mp3",
            "normalization_strategy": "peak",
        }
        prediction = _create_prediction(model, payload)
        final = _poll_prediction(prediction["id"])

        if final.get("status") != "succeeded":
            err = final.get("error") or "unknown error"
            raise RuntimeError(f"Replicate music generation failed: {err}")

        audio_url = _extract_output_url(final.get("output"))

    logger.info(f"⬇️  Downloading music from {audio_url}")
    resp = requests.get(audio_url, timeout=120)
    resp.raise_for_status()
    audio_bytes = resp.content

    # Respect the upstream extension so the frontend's <audio> tag picks the
    # right mime. MusicGen returns .mp3 when output_format=mp3.
    ext = ".mp3"
    if ".wav" in audio_url.lower():
        ext = ".wav"
    file_name = f"generated-music-{uuid.uuid4().hex[:12]}{ext}"
    os.makedirs(storage_dir, exist_ok=True)
    file_path = Path(storage_dir) / file_name
    file_path.write_bytes(audio_bytes)

    logger.info(f"🎶 Music saved: {file_path} ({len(audio_bytes)} bytes)")

    return {
        "file_name": file_name,
        "duration_seconds": duration,
    }


def build_music_prompt(
    question: str,
    welcome_messages: list[str] | None = None,
    rag_chunks: list[dict] | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """Build a MusicGen-friendly prompt + title from the user's request."""
    from openai import OpenAI

    from shared.llm_instrument import traced_openai_call

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    system = (
        "You are an expert prompt engineer for AI music generation (MusicGen). "
        "MusicGen responds best to short, musically-descriptive English prompts "
        "that name: genre, instrumentation, tempo (bpm), mood, key/tonality, "
        "and any notable production qualities. It does NOT render lyrics — "
        "keep clips instrumental.\n\n"
        "Given the user's request plus document context, produce:\n"
        "1. A prompt (max 60 words) suitable for MusicGen. ALWAYS in English, "
        "even if the user's request is in another language — MusicGen is "
        "English-only.\n"
        "2. A short evocative title (max 8 words) in the user's language.\n"
        "3. 0-based source_indices (0–5 entries) pointing to chunks that "
        "most informed the musical choice. Use [] if none apply.\n\n"
        'Output ONLY valid JSON: {"prompt": "...", "title": "...", "source_indices": [0]}'
    )

    user_content = f"User request: {question}\n"
    if welcome_messages:
        user_content += f"\nDocument summary:\n{chr(10).join(welcome_messages[:3])}\n"
    if rag_chunks:
        user_content += "\nRelevant passages:\n"
        for i, chunk in enumerate(rag_chunks[:8]):
            user_content += f"\n[{i}] {chunk.get('file_name', '')}:\n{chunk.get('text', '')[:500]}\n"
    if chat_history:
        user_content += "\nRecent conversation:\n"
        for msg in chat_history[-4:]:
            user_content += f"{msg.get('role', '')}: {msg.get('content', '')[:300]}\n"

    raw, _usage = traced_openai_call(
        client=client,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        model=settings.openai_chat_model,
        operation="music_prompt_build",
        max_completion_tokens=300,
        temperature=1.0,
    )
    try:
        parsed = json.loads(raw)
        return {
            "prompt": parsed["prompt"],
            "title": parsed.get("title", "Generated Music"),
            "source_indices": parsed.get("source_indices", []),
        }
    except (json.JSONDecodeError, KeyError):
        return {"prompt": raw, "title": "Generated Music", "source_indices": []}
