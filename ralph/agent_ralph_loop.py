"""Ralph Wiggum loop — autonomous AFK coding agent for chatrag-app.

Run ``python3.11 agent_ralph_loop.py --task my-feature`` from inside ``ralph/``.
Each iteration:
  1. Reads the PRD (description-{hash}.md) + progress-{hash}.txt + repo state.
  2. Hands an iteration-prompt to the configured agent (copilot | claude).
  3. Runs feedback loops (typecheck / test / lint).
  4. Commits whatever changed, with a message generated from the diff.
  5. Aborts if the last 2 commits have an identical diff (freeze detection).
  6. Asks an LLM whether the PRD's acceptance criteria are met. If yes, exits.

Implements the 11 Ralph Wiggum tips from the AIhero article:
https://www.aihero.dev/tips-for-ai-coding-with-ralph-wiggum
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

from agent_base import CodingAgent, CodingTask
from describe_task import build_description, _iter_task_files, _ralph_root, _state_dir
from feedback_loops import LoopResult, all_blocking_passed, run_all, summarise

logger = logging.getLogger("ralph")

_COMPLETE_TOKEN = "<promise>COMPLETE</promise>"
_DEFAULT_MAX_ITERATIONS = int(os.getenv("RALPH_MAX_ITERATIONS", "10"))
_COMPLETION_MODEL = os.getenv("RALPH_COMPLETION_MODEL", "gpt-4o-mini")


# ============================================================ pure helpers ==

def repo_root() -> Path:
    """Workspace root = parent of ``ralph/``."""
    return _ralph_root().parent


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(  # noqa: S603,S607
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def current_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def diff_digest(repo: Path, ref: str = "HEAD~1..HEAD") -> str | None:
    """Stable digest of the last commit's diff (None if no parent)."""
    try:
        diff = git(repo, "diff", ref, check=False)
    except RuntimeError:
        return None
    if not diff:
        return None
    return hashlib.sha256(diff.encode("utf-8", errors="replace")).hexdigest()[:16]


def changed_areas_since(repo: Path, base_sha: str) -> set[str]:
    """Top-level folders touched between ``base_sha`` and HEAD."""
    out = git(repo, "diff", "--name-only", f"{base_sha}..HEAD", check=False)
    areas = {line.split("/", 1)[0] for line in out.splitlines() if line}
    return areas & {"frontend", "backend", "python", "ralph", "infra", "cloud-function"}


def working_tree_dirty(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain", check=False))


def has_new_commits(repo: Path, since_sha: str) -> bool:
    out = git(repo, "rev-list", f"{since_sha}..HEAD", check=False)
    return bool(out.strip())


# ========================================================= progress tracking ==


@dataclass
class IterationLog:
    iteration: int
    commit_sha: str | None
    feedback_summary: str
    notes: str

    def to_text(self) -> str:
        return textwrap.dedent(
            f"""
            ## Iteration {self.iteration} — {time.strftime('%Y-%m-%d %H:%M:%S')}
            commit: {self.commit_sha or '(no commit)'}
            feedback:
            {textwrap.indent(self.feedback_summary, '  ')}
            notes: {self.notes}
            """
        ).strip() + "\n\n"


def append_progress(progress_file: Path, entry: IterationLog) -> None:
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    with progress_file.open("a", encoding="utf-8") as fh:
        fh.write(entry.to_text())


def read_progress(progress_file: Path) -> str:
    if not progress_file.exists():
        return "(no prior iterations)"
    return progress_file.read_text(encoding="utf-8")


# =================================================================== prompt ==

_ITERATION_PROMPT_TEMPLATE = """\
You are running ONE iteration of a Ralph Wiggum loop on the chatrag-app
monorepo. Read the PRD, decide on the SINGLE most valuable next task, and
implement it. Keep code quality high — see `.github/copilot-instructions.md`.

## PRD (the goal — same every iteration)

{prd}

## Progress so far

{progress}

## Repo state

- branch: `{branch}`
- last commit: `{sha}`
- working tree dirty: {dirty}

## Last iteration's feedback loops

{last_feedback}

## Rules

1. Pick the highest-priority unchecked TODO from the PRD. Prioritise
   architecture > integration > unknowns > standard features > polish.
2. Make the SMALLEST atomic change that moves it forward. ONE feature per
   iteration.
3. Before finishing, run the relevant feedback loops yourself (typecheck,
   tests). Fix anything you broke. Do not commit on red.
4. If — after looking at the repo and progress — every acceptance criterion
   in the PRD is satisfied, write exactly the marker `{complete}` somewhere
   in your output and stop.
5. Do NOT touch files inside `ralph/` (this folder), `.github/workflows/`,
   `data/`, `logs/`, or `node_modules/`.

Now: implement the next task.
"""


def build_iteration_prompt(
    *,
    prd: str,
    progress: str,
    branch: str,
    sha: str,
    dirty: bool,
    last_feedback: str,
) -> str:
    return _ITERATION_PROMPT_TEMPLATE.format(
        prd=prd,
        progress=progress,
        branch=branch,
        sha=sha[:12],
        dirty="yes" if dirty else "no",
        last_feedback=last_feedback or "(first iteration — no feedback yet)",
        complete=_COMPLETE_TOKEN,
    )


# ============================================================ completion check ==


def is_prd_complete(prd: str, repo: Path, last_progress: str) -> tuple[bool, str]:
    """Ask an LLM whether the repo state satisfies the PRD acceptance criteria.

    Returns ``(done, reason)``. Failure of the LLM call is treated as
    'not done' to avoid premature termination.
    """
    try:
        from openai import OpenAI

        client = OpenAI()
    except Exception as exc:  # noqa: BLE001
        return False, f"openai unavailable for completion check: {exc}"

    # Cheap signal: list of recent commit subjects since the loop started.
    recent_log = git(repo, "log", "--oneline", "-n", "20", check=False)
    prompt = (
        "You are a strict reviewer. Given a PRD and the latest repo signals, "
        "decide whether ALL acceptance criteria are demonstrably met. Reply "
        "in the first line with exactly `YES` or `NO`, then a one-sentence "
        "reason on the second line.\n\n"
        f"## PRD\n{prd}\n\n## Progress log\n{last_progress[-4000:]}\n\n"
        f"## Recent commits\n{recent_log}\n"
    )
    try:
        resp = client.chat.completions.create(
            model=_COMPLETION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"completion-check LLM error: {exc}"

    text = (resp.choices[0].message.content or "").strip()
    first_line = text.splitlines()[0].strip().upper() if text else ""
    return first_line.startswith("YES"), text


# ============================================================== loop driver ==


def make_agent(provider: str) -> CodingAgent:
    if provider == "claude":
        from claude_agent import ClaudeAgent

        return ClaudeAgent()
    if provider == "copilot":
        from copilot_agent import CopilotAgent

        return CopilotAgent()
    raise ValueError(f"unknown RALPH_AGENT_PROVIDER: {provider!r}")


def commit_changes(repo: Path, message: str, dry_run: bool) -> str | None:
    if not working_tree_dirty(repo):
        return None
    if dry_run:
        logger.info("[dry-run] would commit: %s", message)
        return None
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message, "--no-verify")
    return current_sha(repo)


def generate_commit_message(repo: Path, agent_output: str) -> str:
    """Short subject from the diff + a co-authored trailer for traceability."""
    diff_stat = git(repo, "diff", "--cached", "--stat", check=False) or git(
        repo, "diff", "--stat", check=False
    )
    head = "ralph: iteration commit"
    first_summary_line = next(
        (ln.strip() for ln in agent_output.splitlines()
         if ln.strip() and not ln.startswith(("$", "#", ">"))),
        "",
    )
    if first_summary_line:
        head = f"ralph: {first_summary_line[:60]}"
    body = f"\n{diff_stat[:1200]}\n\nCo-Authored-By: ralph-loop <ralph@chatrag.app>"
    return head + body


@dataclass
class LoopConfig:
    task: str
    max_iterations: int = _DEFAULT_MAX_ITERATIONS
    provider: str = os.getenv("RALPH_AGENT_PROVIDER", "copilot")
    base_branch: str = os.getenv("RALPH_BASE_BRANCH", "main")
    branch: str | None = None  # default: ralph/<task>
    hitl: bool = False
    dry_run: bool = False
    open_pr: bool = False
    auto_review_after_min: int = 10


def ensure_branch(repo: Path, branch: str, base_branch: str) -> None:
    branches = git(repo, "branch", "--list", branch)
    if branches.strip():
        git(repo, "checkout", branch)
    else:
        git(repo, "checkout", "-B", branch, base_branch)


def loop(cfg: LoopConfig) -> int:
    repo = repo_root()
    branch = cfg.branch or f"ralph/{cfg.task}"
    if not cfg.hitl and not cfg.dry_run:
        ensure_branch(repo, branch, cfg.base_branch)
    description_file = build_description(cfg.task)
    prd = description_file.read_text(encoding="utf-8")
    task_hash = description_file.stem.removeprefix("description-")
    progress_file = _state_dir() / f"progress-{task_hash}.txt"
    commits_log = _state_dir() / f"commits-{task_hash}.log"

    agent = make_agent(cfg.provider)
    attachments = list(_iter_task_files(_ralph_root() / "tasks" / cfg.task))
    start_sha = current_sha(repo)
    last_diff_digest: str | None = None
    last_feedback_text = ""

    for i in range(1, cfg.max_iterations + 1):
        logger.info("=== ralph iteration %d / %d (branch=%s) ===", i, cfg.max_iterations, branch)
        prompt = build_iteration_prompt(
            prd=prd,
            progress=read_progress(progress_file),
            branch=branch,
            sha=current_sha(repo),
            dirty=working_tree_dirty(repo),
            last_feedback=last_feedback_text,
        )
        result = agent.run(CodingTask(
            prompt=prompt,
            repo=repo,
            attachments=attachments,
            iteration=i,
            max_iterations=cfg.max_iterations,
        ))
        logger.info("agent output (truncated): %s", result.output[:500])

        # If the agent decided we're done, trust it but also verify.
        agent_says_done = _COMPLETE_TOKEN in (result.output or "")

        results = run_all(repo, only_changed_areas=changed_areas_since(repo, start_sha) or None)
        last_feedback_text = summarise(results)
        feedback_ok = all_blocking_passed(results)

        commit_sha: str | None = None
        if feedback_ok and not cfg.hitl:
            commit_sha = commit_changes(
                repo,
                generate_commit_message(repo, result.output),
                cfg.dry_run,
            )
            if commit_sha:
                commits_log.parent.mkdir(parents=True, exist_ok=True)
                with commits_log.open("a") as fh:
                    fh.write(commit_sha + "\n")

        notes_parts: list[str] = []
        if not feedback_ok:
            notes_parts.append("blocking feedback failed; skipped commit")
        if agent_says_done:
            notes_parts.append("agent emitted COMPLETE marker")
        append_progress(progress_file, IterationLog(
            iteration=i,
            commit_sha=commit_sha,
            feedback_summary=last_feedback_text,
            notes="; ".join(notes_parts) or "ok",
        ))

        # Freeze detection — two consecutive identical commit diffs.
        if commit_sha:
            digest = diff_digest(repo)
            if digest and digest == last_diff_digest:
                logger.error("freeze detected (identical diff twice in a row); aborting")
                append_progress(progress_file, IterationLog(
                    iteration=i, commit_sha=commit_sha,
                    feedback_summary="(freeze)", notes="aborted: identical diff twice",
                ))
                return 2
            last_diff_digest = digest

        # Completion check.
        if agent_says_done or i == cfg.max_iterations:
            done, reason = is_prd_complete(prd, repo, read_progress(progress_file))
            logger.info("completion check: %s — %s", "DONE" if done else "NOT DONE",
                        reason.replace("\n", " "))
            if done:
                _maybe_open_pr_flow(cfg, repo, branch, task_hash)
                return 0

        if cfg.hitl:
            logger.info("HITL mode — stopping after one iteration")
            return 0

    logger.warning("hit max iterations (%d) without COMPLETE", cfg.max_iterations)
    if has_new_commits(repo, start_sha):
        _maybe_open_pr_flow(cfg, repo, branch, task_hash)
    return 1


def _maybe_open_pr_flow(cfg: LoopConfig, repo: Path, branch: str, task_hash: str) -> None:
    if not cfg.open_pr or cfg.dry_run:
        return
    github_repo = os.getenv("GITHUB_REPOSITORY")
    github_token = os.getenv("GITHUB_TOKEN")
    if not (github_repo and github_token):
        logger.info("skipping PR flow: GITHUB_REPOSITORY / GITHUB_TOKEN not set")
        return
    from copilot_agent import comment_on_pr, mark_pr_ready, open_pr

    git(repo, "push", "-u", "origin", branch)
    pr_url = open_pr(
        repo, branch, cfg.base_branch,
        title=f"ralph: {cfg.task}",
        body=f"Automated by ralph loop. Task hash: `{task_hash}`.",
        github_repo=github_repo, github_token=github_token, draft=True,
    )
    logger.info("opened draft PR %s", pr_url)
    mark_pr_ready(pr_url, github_token)
    if cfg.auto_review_after_min > 0:
        logger.info("waiting %d min before requesting AI review fixup", cfg.auto_review_after_min)
        time.sleep(cfg.auto_review_after_min * 60)
        comment_on_pr(
            pr_url,
            "@copilot fix all comments and suggestions from AI bots and human "
            "reviewers, then merge to main.",
            github_token,
        )


# ===================================================================== cli ==


def _parse_args(argv: list[str] | None) -> LoopConfig:
    p = argparse.ArgumentParser(description="Ralph Wiggum loop driver")
    p.add_argument("--task", required=True, help="task folder under ralph/tasks/")
    p.add_argument("--iterations", type=int, default=_DEFAULT_MAX_ITERATIONS)
    p.add_argument("--provider", default=os.getenv("RALPH_AGENT_PROVIDER", "copilot"),
                   choices=["copilot", "claude"])
    p.add_argument("--base-branch", default=os.getenv("RALPH_BASE_BRANCH", "main"))
    p.add_argument("--branch", default=None)
    p.add_argument("--hitl", action="store_true",
                   help="single iteration, no commit (human-in-the-loop)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--open-pr", action="store_true",
                   help="push branch + open PR + mark ready + ask copilot for review fixes")
    p.add_argument("--auto-review-after-min", type=int, default=10)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return LoopConfig(
        task=args.task,
        max_iterations=args.iterations,
        provider=args.provider,
        base_branch=args.base_branch,
        branch=args.branch,
        hitl=args.hitl,
        dry_run=args.dry_run,
        open_pr=args.open_pr,
        auto_review_after_min=args.auto_review_after_min,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = _parse_args(argv)
    return loop(cfg)


if __name__ == "__main__":
    sys.exit(main())
