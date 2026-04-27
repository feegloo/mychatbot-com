"""Claude Code CLI driver — the original Ralph backend.

We invoke ``claude -p "<prompt>" --dangerously-skip-permissions`` (or the
sandbox equivalent) and capture the output. Set ``CLAUDE_API_KEY`` in the env
or rely on the user's ``claude login``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from agent_base import CodingResult, CodingTask

logger = logging.getLogger(__name__)

_CLAUDE_BIN = os.getenv("RALPH_CLAUDE_BIN", "claude")


class ClaudeAgent:
    name = "claude"

    def run(self, task: CodingTask) -> CodingResult:
        if not shutil.which(_CLAUDE_BIN):
            return CodingResult(
                output=f"[ralph] {_CLAUDE_BIN} not found on PATH", succeeded=False
            )
        prompt = self._build_prompt(task)
        cmd = [_CLAUDE_BIN, "-p", prompt, "--dangerously-skip-permissions"]
        logger.info("invoking claude code (iter %d)", task.iteration)
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(task.repo),
                capture_output=True,
                text=True,
                timeout=60 * 30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CodingResult(output="[ralph] claude code timed out", succeeded=False)
        out = (proc.stdout + "\n" + proc.stderr).strip()
        return CodingResult(output=out, succeeded=proc.returncode == 0)

    @staticmethod
    def _build_prompt(task: CodingTask) -> str:
        attachments_section = ""
        if task.attachments:
            attachments_section = "\n\n" + "\n".join(f"@{p}" for p in task.attachments)
        return (
            f"# Ralph iteration {task.iteration}/{task.max_iterations}\n\n"
            f"{task.prompt}{attachments_section}"
        )
