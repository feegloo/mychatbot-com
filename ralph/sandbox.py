"""Optional Docker sandbox wrapper for AFK Ralph runs.

Builds a small image once (cached by the Dockerfile content hash) and execs
the loop inside it. The current workspace is mounted read-write, but the host
home directory and SSH keys are NOT exposed.

Used only when ``--sandbox`` is passed to ``run.sh`` or
``agent_ralph_loop.py``. HITL runs skip this for speed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import subprocess
from pathlib import Path
from textwrap import dedent

logger = logging.getLogger(__name__)

_IMAGE_NAME = "ralph-loop-sandbox"
_DOCKERFILE = dedent(
    """
    FROM python:3.11-slim
    RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates jq build-essential nodejs npm \
        && rm -rf /var/lib/apt/lists/*
    RUN npm install -g @anthropic-ai/claude-code @github/copilot 2>/dev/null || true
    WORKDIR /workspace
    """
).strip()


def _dockerfile_digest() -> str:
    return hashlib.sha256(_DOCKERFILE.encode("utf-8")).hexdigest()[:12]


def _ensure_image() -> str:
    tag = f"{_IMAGE_NAME}:{_dockerfile_digest()}"
    inspect = subprocess.run(  # noqa: S603,S607
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode == 0:
        return tag
    logger.info("Building sandbox image %s", tag)
    proc = subprocess.run(  # noqa: S603,S607
        ["docker", "build", "-t", tag, "-f", "-", "."],
        input=_DOCKERFILE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker build failed (exit {proc.returncode})")
    return tag


def run_in_sandbox(repo: Path, argv: list[str]) -> int:
    """Run ``argv`` inside the sandbox with ``repo`` mounted at ``/workspace``."""
    tag = _ensure_image()
    cmd = [
        "docker", "run", "--rm", "-i",
        "-v", f"{repo}:/workspace",
        "-e", "OPENAI_API_KEY",
        "-e", "CLAUDE_API_KEY",
        "-e", "GITHUB_TOKEN",
        "-e", "RALPH_AGENT_PROVIDER",
        "-e", "RALPH_MAX_ITERATIONS",
        "-e", "RALPH_BASE_BRANCH",
        "-w", "/workspace",
        tag,
        *argv,
    ]
    logger.info("$ %s", " ".join(shlex.quote(c) for c in cmd))
    return subprocess.call(cmd)  # noqa: S603


def is_available() -> bool:
    proc = subprocess.run(  # noqa: S603,S607
        ["docker", "version"], capture_output=True, check=False
    )
    return proc.returncode == 0
