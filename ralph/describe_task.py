"""Convert a folder of input task files into a single PRD-style markdown.

Drop any number of files into ``ralph/tasks/<task-name>/`` (this script will
NOT touch files that match the loop's own machinery — see ``LOOP_FILE_NAMES``).
Running ``describe_task <task-name>`` produces
``ralph/state/description-<task-hash>.md`` containing:

1. A welcome / overview paragraph (LLM generated from all file descriptions).
2. A list of input files (relative paths).
3. A TODO plan (LLM generated, prioritised: arch → integration → polish).
4. The final goal description (verbatim from ``goal.md`` if present, otherwise
   inferred from the file descriptions).

The hash is a short stable digest of the task folder contents, so the same
inputs always map to the same description file (idempotent re-runs).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

from file_describer import describe_files

logger = logging.getLogger(__name__)

# Files that belong to the loop engine itself — never treat as task input.
LOOP_FILE_NAMES = {
    "agent_ralph_loop.py",
    "describe_task.py",
    "file_describer.py",
    "feedback_loops.py",
    "copilot_agent.py",
    "claude_agent.py",
    "sandbox.py",
    "requirements.txt",
    "run.sh",
    "README.md",
    ".gitignore",
}

PRD_MODEL = os.getenv("RALPH_DESCRIBE_MODEL", "gpt-4o-mini")


def _ralph_root() -> Path:
    return Path(__file__).resolve().parent


def _state_dir() -> Path:
    d = _ralph_root() / "state"
    d.mkdir(exist_ok=True)
    return d


def _task_hash(task_dir: Path) -> str:
    """Stable short hash of the task contents (names + sizes + mtimes).

    Using mtimes keeps it cheap; if a user replaces a file we want a new hash.
    """
    parts: list[str] = []
    for p in sorted(_iter_task_files(task_dir)):
        st = p.stat()
        parts.append(f"{p.relative_to(task_dir)}|{st.st_size}|{int(st.st_mtime)}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _iter_task_files(task_dir: Path):
    for p in sorted(task_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.name in LOOP_FILE_NAMES:
            continue
        if any(part.startswith(".") for part in p.relative_to(task_dir).parts):
            continue
        yield p


def _build_prd_via_llm(
    task_name: str,
    descriptions: dict[str, str],
    explicit_goal: str | None,
) -> str:
    """Ask an LLM to weave the per-file descriptions into a coherent PRD."""
    try:
        from openai import OpenAI

        client = OpenAI()
    except Exception as exc:  # noqa: BLE001
        logger.warning("openai unavailable, returning raw concat: %s", exc)
        return _fallback_prd(task_name, descriptions, explicit_goal)

    files_section = "\n\n".join(
        f"### `{name}`\n{desc.strip()}" for name, desc in descriptions.items()
    )
    goal_section = explicit_goal.strip() if explicit_goal else "(none provided — infer from inputs)"

    system_prompt = (
        "You are the planner for a Ralph Wiggum coding loop running over the "
        "chatrag-app monorepo (Vue 3 frontend, Koa backend, Python AI engine). "
        "Produce a single markdown PRD that the loop will hand to an autonomous "
        "coding agent every iteration. Sections required, in order:\n"
        "  1. # Goal — one paragraph, plain English, copied from the user's "
        "explicit goal if provided.\n"
        "  2. ## Input files — bullet list of `relative/path` (just the paths "
        "from the file descriptions you receive).\n"
        "  3. ## TODO — ordered checklist of small, atomic tasks. Order them: "
        "architecture → integration points → unknowns → standard features → "
        "polish. Each item must be doable in ONE commit.\n"
        "  4. ## Acceptance criteria — explicit, testable. The agent emits "
        "`<promise>COMPLETE</promise>` only when ALL criteria pass.\n"
        "  5. ## Notes for the agent — any constraints (file layout, existing "
        "patterns, gotchas) extracted from the inputs.\n"
        "Be concrete. No fluff. No code unless it appears in the inputs."
    )
    user_prompt = (
        f"Task name: `{task_name}`\n\n"
        f"User-provided goal:\n{goal_section}\n\n"
        f"## Per-file descriptions\n\n{files_section}"
    )
    resp = client.chat.completions.create(
        model=PRD_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2000,
    )
    return resp.choices[0].message.content or _fallback_prd(task_name, descriptions, explicit_goal)


def _fallback_prd(task_name: str, descriptions: dict[str, str], goal: str | None) -> str:
    parts = [f"# Goal\n\n{goal or '(no goal.md found — see inputs)'}", "## Input files\n"]
    parts += [f"- `{n}`" for n in descriptions]
    parts.append("\n## TODO\n\n- [ ] Read all input files and infer plan\n- [ ] Implement\n- [ ] Verify with feedback loops")
    parts.append("\n## Acceptance criteria\n\n- All feedback loops green\n- Goal as stated above is met")
    parts.append("\n## Notes for the agent\n")
    for name, desc in descriptions.items():
        parts.append(f"### `{name}`\n{desc}\n")
    return "\n".join(parts)


def _read_goal(task_dir: Path) -> str | None:
    for candidate in ("goal.md", "GOAL.md", "goal.txt"):
        p = task_dir / candidate
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def build_description(task_name: str, *, force: bool = False) -> Path:
    """Generate (or reuse) ``description-<hash>.md`` for the named task.

    Returns the path to the generated description file.
    """
    task_dir = _ralph_root() / "tasks" / task_name
    if not task_dir.is_dir():
        raise FileNotFoundError(f"Task folder not found: {task_dir}")
    files = list(_iter_task_files(task_dir))
    if not files:
        raise ValueError(f"Task folder {task_dir} contains no input files")

    h = _task_hash(task_dir)
    out = _state_dir() / f"description-{h}.md"
    if out.exists() and not force:
        logger.info("Reusing existing description %s", out)
        return out

    logger.info("Describing %d files in task %s …", len(files), task_name)
    rel_descriptions = {
        str(p.relative_to(task_dir)): d for p, d in describe_files(files).items()
    }
    explicit_goal = _read_goal(task_dir)
    prd = _build_prd_via_llm(task_name, rel_descriptions, explicit_goal)
    header = (
        f"<!-- ralph task=`{task_name}` hash={h} files={len(files)} -->\n\n"
    )
    out.write_text(header + prd, encoding="utf-8")
    logger.info("Wrote %s", out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ralph PRD from a task folder")
    parser.add_argument("task", help="task folder name under ralph/tasks/")
    parser.add_argument("--force", action="store_true", help="regenerate even if description exists")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    out = build_description(args.task, force=args.force)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
