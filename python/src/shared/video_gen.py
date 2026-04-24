"""Short video generation via Replicate (LTX-Video).

Generates 3–10 second videos from text prompts and saves them to the
conversation's storage directory so they can be served via the existing
/api/storage/ route — mirroring the pattern used by ``image_gen.py``.

The Replicate HTTP API is called directly (no SDK dependency) to keep
requirements lean. LTX-Video was chosen as the default model because it
is the fastest generally-available text-to-video model on Replicate
(typically <30 s wall-clock for a 5 s clip).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

import requests

from shared.config import get_settings
from shared.otel import get_tracer

logger = logging.getLogger(__name__)


REPLICATE_API_BASE = "https://api.replicate.com/v1"
# "lightricks/ltx-video" — fast text-to-video (~5 s clips, ~15–30 s to generate).
# Pinned to the latest owner/model form; Replicate resolves the newest version.
DEFAULT_VIDEO_MODEL = os.getenv("REPLICATE_VIDEO_MODEL", "lightricks/ltx-video")
# Min/max clip durations (seconds) the frontend/LLM may request.
MIN_DURATION_S = 3
MAX_DURATION_S = 10
DEFAULT_DURATION_S = 5
# How long we will wait for Replicate to finish before giving up.
POLL_TIMEOUT_S = 180
POLL_INTERVAL_S = 2.0


def _api_token() -> str:
    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "REPLICATE_API_TOKEN is not set — required for video/music generation"
        )
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_token()}",
        "Content-Type": "application/json",
    }


def _create_prediction(model: str, input_payload: dict) -> dict:
    """POST /v1/models/<owner>/<name>/predictions — start a new run."""
    url = f"{REPLICATE_API_BASE}/models/{model}/predictions"
    resp = requests.post(url, headers=_headers(), data=json.dumps({"input": input_payload}), timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Replicate create failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def _poll_prediction(prediction_id: str, timeout_s: int = POLL_TIMEOUT_S) -> dict:
    """Poll /v1/predictions/<id> until it succeeds/fails/times out."""
    deadline = time.monotonic() + timeout_s
    url = f"{REPLICATE_API_BASE}/predictions/{prediction_id}"
    while True:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status in ("succeeded", "failed", "canceled"):
            return data
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Replicate prediction {prediction_id} did not complete within {timeout_s}s"
            )
        time.sleep(POLL_INTERVAL_S)


def _extract_output_url(output) -> str:
    """LTX-Video returns a single URL string; other models may return a list."""
    if isinstance(output, str):
        return output
    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, str):
            return first
    raise ValueError(f"Unexpected Replicate output shape: {output!r}")


def _clamp_duration(seconds: float | int | None) -> int:
    if seconds is None:
        return DEFAULT_DURATION_S
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return DEFAULT_DURATION_S
    return max(MIN_DURATION_S, min(MAX_DURATION_S, s))


def generate_video(
    prompt: str,
    storage_dir: str,
    duration_seconds: int | None = None,
    model: str = DEFAULT_VIDEO_MODEL,
) -> dict:
    """Generate a short video from a text prompt using Replicate.

    Args:
        prompt: The visual description for the video.
        storage_dir: Directory to save the resulting .mp4.
        duration_seconds: Requested clip length, clamped to [3, 10]. Models
            typically snap this to the nearest supported value internally.
        model: Replicate model slug in ``owner/name`` form.

    Returns:
        dict with 'file_name' (saved .mp4) and 'duration_seconds' (requested).
    """
    duration = _clamp_duration(duration_seconds)

    logger.info(
        f"🎬 Generating video: prompt='{prompt[:100]}...' duration={duration}s model={model}"
    )

    tracer = get_tracer("chatrag.video_gen")
    with tracer.start_as_current_span(
        "video.generate", attributes={"model": model, "duration_seconds": duration}
    ):
        # LTX-Video accepts: prompt, (optional) negative_prompt, num_frames,
        # frame_rate. We ask for `duration * fps` frames at 24 fps.
        fps = 24
        payload = {
            "prompt": prompt,
            "num_frames": duration * fps,
            "frame_rate": fps,
        }
        prediction = _create_prediction(model, payload)
        final = _poll_prediction(prediction["id"])

        if final.get("status") != "succeeded":
            err = final.get("error") or "unknown error"
            raise RuntimeError(f"Replicate video generation failed: {err}")

        video_url = _extract_output_url(final.get("output"))

    # Download the rendered .mp4 so it's served from our own storage.
    logger.info(f"⬇️  Downloading video from {video_url}")
    resp = requests.get(video_url, timeout=180)
    resp.raise_for_status()
    video_bytes = resp.content

    file_name = f"generated-video-{uuid.uuid4().hex[:12]}.mp4"
    os.makedirs(storage_dir, exist_ok=True)
    file_path = Path(storage_dir) / file_name
    file_path.write_bytes(video_bytes)

    logger.info(f"🎞️ Video saved: {file_path} ({len(video_bytes)} bytes)")

    return {
        "file_name": file_name,
        "duration_seconds": duration,
    }


def build_video_prompt(
    question: str,
    welcome_messages: list[str] | None = None,
    rag_chunks: list[dict] | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """Build a cinematic video prompt + title from the user's request.

    Mirrors ``image_gen.build_image_prompt`` but tailored for short video
    clips: emphasizes camera motion, subject action, and a single unified
    shot — not a storyboard of cuts (LTX-Video and similar models produce
    one continuous take).
    """
    from openai import OpenAI  # local import keeps cold-start cheap

    from shared.llm_instrument import traced_openai_call

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    system = (
        "You are an expert prompt engineer for short AI-generated video clips "
        "(3–10 seconds, ONE continuous shot — no cuts, no scene changes). "
        "Given the user's request, document sources, and conversation history, produce:\n"
        "1. A vivid video generation prompt (max 120 words). Describe: subject, "
        "subject action/motion, camera motion (e.g. slow dolly-in, static, pan right), "
        "setting, lighting, mood, visual style. Avoid instructions that imply cuts.\n"
        "2. A short evocative title (max 8 words) in the SAME LANGUAGE as the user's "
        "request and source material.\n"
        "3. A list of 0-based source indices (0–5 entries) from the provided chunks "
        "that most informed the clip concept. Use [] if none apply.\n\n"
        "Never render readable text, logos, or watermarks. Reframe copyrighted "
        "character/scene references as 'inspired by …' so content filters pass.\n\n"
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
        operation="video_prompt_build",
        max_completion_tokens=400,
        temperature=1.0,
    )
    try:
        parsed = json.loads(raw)
        return {
            "prompt": parsed["prompt"],
            "title": parsed.get("title", "Generated Video"),
            "source_indices": parsed.get("source_indices", []),
        }
    except (json.JSONDecodeError, KeyError):
        return {"prompt": raw, "title": "Generated Video", "source_indices": []}
