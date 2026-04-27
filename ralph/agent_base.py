"""Shared protocol for Ralph agent drivers.

A driver is anything that turns a ``CodingTask`` (prompt + repo path + file
attachments) into actual file changes on disk. Each iteration of the Ralph
loop calls ``driver.run(task)``; the loop then commits whatever the driver
left in the working tree.

We support two providers:
  - ``copilot`` (default) — invokes the GitHub Copilot CLI / Coding Agent,
    so sessions show up at github.com/<owner>/<repo>/agents.
  - ``claude``  — invokes the Claude Code CLI in non-interactive mode.

Both drivers return a ``CodingResult`` with the agent's textual output (used
for ``<promise>COMPLETE</promise>`` detection in the loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class CodingTask:
    """One iteration's worth of work for the agent."""

    prompt: str
    repo: Path
    attachments: list[Path] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10


@dataclass
class CodingResult:
    output: str
    succeeded: bool = True


class CodingAgent(Protocol):
    name: str

    def run(self, task: CodingTask) -> CodingResult: ...
