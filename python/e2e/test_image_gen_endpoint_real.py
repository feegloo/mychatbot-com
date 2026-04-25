"""Live OpenAI image generation test for the FastAPI endpoint.

This file lives outside python/tests on purpose, so it is excluded from the
default pytest discovery configured in python/pytest.ini and only runs via the
dedicated `make e2e` command.

Run locally:
    cd python && RUN_REAL_OPENAI_TEST=1 OPENAI_API_KEY=... make e2e

Artifacts (partial frames + final image) are written to e2e/output/ which is
gitignored, so you can inspect them after a run without committing them.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from pathlib import Path

import pytest
from PIL import Image

from src import server

RUN_REAL_IMAGE_TEST = os.environ.get("RUN_REAL_OPENAI_TEST") == "1"

# Persistent folder for visual inspection — gitignored, created on demand.
OUTPUT_DIR = Path(__file__).parent / "output"

pytestmark = [
    pytest.mark.skipif(
        not RUN_REAL_IMAGE_TEST,
        reason="Set RUN_REAL_OPENAI_TEST=1 to run live OpenAI image endpoint test",
    ),
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set; skipping live OpenAI image endpoint test",
    ),
]




def _log(msg: str) -> None:
    """Print a timestamped line — visible because pytest runs with -s."""
    print(f"\n[e2e {time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def _stream_events(req: server.GenerateImageRequest) -> list[dict]:
    """Consume the streaming endpoint, log each event, and return them all."""
    response = await server.generate_image_stream_endpoint(req)
    events: list[dict] = []
    async for chunk in response.body_iterator:
        line = chunk if isinstance(chunk, str) else chunk.decode()
        if not line.strip():
            continue
        event = json.loads(line)
        events.append(event)

        event_type = event.get("event")
        data = event.get("data", {})

        if event_type == "prompt_ready":
            _log(f"→ prompt_ready")
            _log(f"  image_title : {data.get('image_title', '—')}")
            _log(f"  image_prompt: {data.get('image_prompt', '—')[:300]}")
        elif event_type == "partial":
            b64_len = len(data.get("b64", ""))
            _log(f"→ partial  index={data.get('index')}  b64_bytes≈{b64_len}")
        elif event_type == "complete":
            _log(f"→ complete")
            _log(f"  file_name     : {data.get('file_name', '—')}")
            _log(f"  revised_prompt: {str(data.get('revised_prompt', '—'))[:300]}")
        elif event_type == "error":
            _log(f"→ ERROR: {data.get('error', '—')}")
        else:
            _log(f"→ {event_type}: {str(data)[:200]}")

    return events


def test_generate_image_stream_saves_artifacts(tmp_path: Path):
    """Stream image generation, save every partial frame and the final image.

    After a successful run, inspect e2e/output/ to see progressive quality
    improvements across partial_{0,1,2}.jpg → final.jpg.
    """
    requested_size = os.environ.get("REAL_OPENAI_IMAGE_TEST_SIZE", "1024x1536")
    prompt = os.environ.get(
        "REAL_OPENAI_IMAGE_TEST_PROMPT",
        "Generate image inspired by a quiet dermatology clinic portrait with black side mattes",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _log(f"Starting e2e image stream test")
    _log(f"  size  : {requested_size}")
    _log(f"  prompt: {prompt}")
    _log(f"  output: {OUTPUT_DIR}")

    req = server.GenerateImageRequest(
        question=prompt,
        storage_dir=str(tmp_path),
        size=requested_size,
        quality="low",
    )

    t0 = time.monotonic()
    events = asyncio.run(_stream_events(req))
    elapsed = time.monotonic() - t0
    _log(f"Stream finished in {elapsed:.1f}s  ({len(events)} events total)")

    partial_count = 0
    final_file: Path | None = None

    for event in events:
        event_type = event.get("event")
        data = event.get("data", {})

        if event_type == "partial":
            frame_path = OUTPUT_DIR / f"partial_{partial_count}.jpg"
            frame_path.write_bytes(base64.b64decode(data["b64"]))
            _log(f"  Saved partial frame [{partial_count}]: {frame_path.name}")
            partial_count += 1

        elif event_type == "complete":
            src = tmp_path / data["file_name"]
            if src.is_file():
                dest = OUTPUT_DIR / "final.jpg"
                dest.write_bytes(src.read_bytes())
                final_file = dest
                _log(f"  Saved final image: {dest.name}  ({dest.stat().st_size // 1024} KB)")

    _log(f"Artifacts → {OUTPUT_DIR}  (partials: {partial_count})")

    assert final_file is not None and final_file.is_file(), (
        f"Final image not found in output folder "
        f"(events received: {[e.get('event') for e in events]})"
    )

    expected_width, expected_height = map(int, requested_size.split("x", 1))
    with Image.open(final_file) as generated:
        actual = generated.size
    _log(f"Dimension check: expected {requested_size}, got {actual[0]}x{actual[1]}")
    assert actual == (expected_width, expected_height), (
        f"Expected {requested_size}, got {actual[0]}x{actual[1]}"
    )