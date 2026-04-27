"""GitHub Copilot Coding Agent driver.

Two modes:
  1. ``copilot`` CLI is on PATH — we shell out to ``copilot --prompt …``,
     which uses the local Copilot subscription and edits files in place.
  2. CLI not present — fall back to dispatching a remote Coding Agent session
     via the GitHub API (``POST /repos/{owner}/{repo}/copilot/agents``-style
     endpoint, currently delivered through the Issues `@copilot` mention).
     Sessions then show up at github.com/<owner>/<repo>/agents.

The first mode is what makes Ralph work locally. The second mode is used when
we run on GitHub Actions — see ``.github/workflows/ralph.yml`` — there the
loop creates the issue, mentions @copilot, polls the resulting agent session
until it commits, then continues.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import requests  # type: ignore

from agent_base import CodingResult, CodingTask

logger = logging.getLogger(__name__)

_COPILOT_BIN = os.getenv("RALPH_COPILOT_BIN", "copilot")
_GITHUB_API = "https://api.github.com"
_POLL_TIMEOUT_SEC = 30 * 60
_POLL_INTERVAL_SEC = 30


class CopilotAgent:
    name = "copilot"

    def __init__(self, github_repo: str | None = None, github_token: str | None = None) -> None:
        # github_repo like "feegloo/chatrag-app", needed only for remote mode.
        self.github_repo = github_repo or os.getenv("GITHUB_REPOSITORY")
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")

    # ------------------------------------------------------------------ run

    def run(self, task: CodingTask) -> CodingResult:
        if shutil.which(_COPILOT_BIN):
            return self._run_local_cli(task)
        if self.github_repo and self.github_token:
            return self._run_remote_agent(task)
        return CodingResult(
            output="[ralph] copilot CLI not on PATH and GITHUB_TOKEN/REPO not set",
            succeeded=False,
        )

    # -------------------------------------------------------------- local CLI

    def _run_local_cli(self, task: CodingTask) -> CodingResult:
        prompt = self._build_prompt(task)
        cmd = [_COPILOT_BIN, "--prompt", prompt, "--allow-all-tools"]
        for att in task.attachments:
            cmd.extend(["--attach", str(att)])
        logger.info("invoking copilot cli (%d attachments)", len(task.attachments))
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
            return CodingResult(output="[ralph] copilot cli timed out", succeeded=False)
        out = (proc.stdout + "\n" + proc.stderr).strip()
        return CodingResult(output=out, succeeded=proc.returncode == 0)

    # ----------------------------------------------------------- remote agent

    def _run_remote_agent(self, task: CodingTask) -> CodingResult:
        """Dispatch a remote Copilot Coding Agent session via an issue mention.

        This mirrors the manual flow at
        https://github.com/{owner}/{repo}/agents — Copilot picks up the issue,
        opens a PR, commits to a branch. We poll the issue's timeline until
        Copilot reports done (or times out).
        """
        assert self.github_repo and self.github_token  # checked by run()
        issue_url = self._create_issue(task)
        logger.info("created tracking issue %s for ralph iteration", issue_url)
        return self._poll_session(issue_url, task)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _create_issue(self, task: CodingTask) -> str:
        body = (
            "@copilot Please implement the task below. Commit small, atomic "
            "changes. Run feedback loops before each commit.\n\n"
            f"{task.prompt}"
        )
        resp = requests.post(
            f"{_GITHUB_API}/repos/{self.github_repo}/issues",
            json={
                "title": f"[ralph] iteration {task.iteration}/{task.max_iterations}",
                "body": body,
                "labels": ["ralph"],
            },
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["html_url"]

    def _poll_session(self, issue_url: str, task: CodingTask) -> CodingResult:
        # Poll the issue events; once a referenced PR is merged or the agent
        # closes the issue we treat the iteration as complete.
        issue_number = int(issue_url.rsplit("/", 1)[-1])
        deadline = time.time() + _POLL_TIMEOUT_SEC
        last_log = ""
        while time.time() < deadline:
            time.sleep(_POLL_INTERVAL_SEC)
            r = requests.get(
                f"{_GITHUB_API}/repos/{self.github_repo}/issues/{issue_number}",
                headers=self._headers(),
                timeout=30,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            last_log = data.get("body") or ""
            if data.get("state") == "closed":
                return CodingResult(output=f"copilot session closed: {issue_url}\n{last_log}")
        return CodingResult(
            output=f"copilot session timed out after {_POLL_TIMEOUT_SEC}s: {issue_url}\n{last_log}",
            succeeded=False,
        )

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _build_prompt(task: CodingTask) -> str:
        attachments_section = ""
        if task.attachments:
            rels = "\n".join(f"- {p}" for p in task.attachments)
            attachments_section = f"\n\nReference files (attached):\n{rels}\n"
        return (
            f"# Ralph iteration {task.iteration}/{task.max_iterations}\n\n"
            f"{task.prompt}{attachments_section}"
        )


def open_pr(repo: Path, head_branch: str, base_branch: str, title: str, body: str,
            github_repo: str, github_token: str, *, draft: bool = True) -> str:
    """Open (or update) a PR for ``head_branch`` and return the html_url."""
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.post(
        f"{_GITHUB_API}/repos/{github_repo}/pulls",
        json={
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body,
            "draft": draft,
        },
        headers=headers,
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return resp.json()["html_url"]
    # Already exists — find it.
    listing = requests.get(
        f"{_GITHUB_API}/repos/{github_repo}/pulls",
        params={"head": f"{github_repo.split('/')[0]}:{head_branch}", "state": "open"},
        headers=headers,
        timeout=30,
    )
    listing.raise_for_status()
    items = listing.json()
    if items:
        return items[0]["html_url"]
    raise RuntimeError(f"could not open or find PR: {resp.status_code} {resp.text}")


def comment_on_pr(pr_url: str, body: str, github_token: str) -> None:
    # pr_url like https://github.com/owner/repo/pull/N  →  issues comment endpoint
    parts = pr_url.rstrip("/").split("/")
    owner, repo, _, number = parts[-4], parts[-3], parts[-2], parts[-1]
    requests.post(
        f"{_GITHUB_API}/repos/{owner}/{repo}/issues/{number}/comments",
        json={"body": body},
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    ).raise_for_status()


def mark_pr_ready(pr_url: str, github_token: str) -> None:
    """Use ``gh`` if available (cheapest); fall back to GraphQL."""
    if shutil.which("gh"):
        subprocess.run(  # noqa: S603,S607
            ["gh", "pr", "ready", pr_url],
            check=False,
            env={**os.environ, "GH_TOKEN": github_token},
        )
        return
    # GraphQL fallback — needs the PR node id.
    parts = pr_url.rstrip("/").split("/")
    owner, repo, number = parts[-4], parts[-3], parts[-1]
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    pr = requests.get(
        f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{number}",
        headers=headers,
        timeout=30,
    ).json()
    node_id = pr["node_id"]
    requests.post(
        f"{_GITHUB_API}/graphql",
        json={
            "query": "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){clientMutationId}}",
            "variables": {"id": node_id},
        },
        headers=headers,
        timeout=30,
    )
