"""Run the chatrag-app feedback loops: TypeScript, ESLint, tests.

Each loop returns a ``LoopResult(name, ok, output)``. The Ralph engine prints
the failures back into the next iteration's prompt so the agent self-corrects.
We deliberately treat lint as a soft-fail (warning) per the user's spec.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Truncate captured output so it never blows up the next prompt's context.
_MAX_OUTPUT_CHARS = 6_000


@dataclass
class LoopResult:
    name: str
    ok: bool
    output: str
    soft: bool = False  # soft=True means a failure does NOT block "done"

    def short(self) -> str:
        status = "OK" if self.ok else ("WARN" if self.soft else "FAIL")
        return f"[{status}] {self.name}"


def _run(cmd: list[str], cwd: Path, *, timeout: int = 600) -> tuple[int, str]:
    logger.info("$ %s  (cwd=%s)", " ".join(cmd), cwd)
    try:
        proc = subprocess.run(  # noqa: S603 — explicit args list, not shell
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    out = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, out[-_MAX_OUTPUT_CHARS:]


def _frontend_typecheck(repo: Path) -> LoopResult | None:
    pkg = repo / "frontend" / "package.json"
    if not pkg.exists():
        return None
    code, out = _run(["npm", "run", "-s", "type-check"], repo / "frontend")
    return LoopResult("frontend:type-check", code == 0, out)


def _backend_typecheck(repo: Path) -> LoopResult | None:
    pkg = repo / "backend" / "package.json"
    if not pkg.exists():
        return None
    code, out = _run(["npx", "tsc", "--noEmit"], repo / "backend")
    return LoopResult("backend:tsc", code == 0, out)


def _frontend_test(repo: Path) -> LoopResult | None:
    pkg = repo / "frontend" / "package.json"
    if not pkg.exists():
        return None
    code, out = _run(["npm", "run", "-s", "test:unit", "--", "--run"], repo / "frontend",
                     timeout=900)
    return LoopResult("frontend:test", code == 0, out)


def _backend_test(repo: Path) -> LoopResult | None:
    pkg = repo / "backend" / "package.json"
    if not pkg.exists():
        return None
    code, out = _run(["npm", "run", "-s", "test:unit"], repo / "backend", timeout=900)
    return LoopResult("backend:test", code == 0, out)


def _python_test(repo: Path) -> LoopResult | None:
    if not (repo / "python" / "pytest.ini").exists():
        return None
    code, out = _run(["python3.11", "-m", "pytest", "-q"], repo / "python", timeout=900)
    return LoopResult("python:pytest", code == 0, out)


def _frontend_lint(repo: Path) -> LoopResult | None:
    pkg = repo / "frontend" / "package.json"
    if not pkg.exists():
        return None
    code, out = _run(["npm", "run", "-s", "lint"], repo / "frontend")
    return LoopResult("frontend:lint", code == 0, out, soft=True)


def _backend_lint(repo: Path) -> LoopResult | None:
    pkg = repo / "backend" / "package.json"
    if not pkg.exists():
        return None
    code, out = _run(["npm", "run", "-s", "lint"], repo / "backend")
    return LoopResult("backend:lint", code == 0, out, soft=True)


_RUNNERS = (
    _frontend_typecheck,
    _backend_typecheck,
    _frontend_test,
    _backend_test,
    _python_test,
    _frontend_lint,
    _backend_lint,
)


def run_all(repo: Path, *, only_changed_areas: set[str] | None = None) -> list[LoopResult]:
    """Run all applicable loops for the repo.

    ``only_changed_areas`` is an optional optimisation: a set of top-level
    folder names ({"frontend", "backend", "python"}) that the last commit
    touched. If provided, we skip loops for unrelated areas.
    """
    skip_env = {a.strip() for a in os.getenv("RALPH_SKIP_LOOPS", "").split(",") if a.strip()}
    results: list[LoopResult] = []
    for runner in _RUNNERS:
        name = runner.__name__.lstrip("_")
        if name in skip_env:
            continue
        if only_changed_areas is not None:
            area = name.split("_", 1)[0]
            if area not in only_changed_areas:
                continue
        try:
            r = runner(repo)
        except Exception as exc:  # noqa: BLE001
            logger.exception("loop %s crashed", name)
            r = LoopResult(name, ok=False, output=f"runner crashed: {exc}")
        if r is not None:
            results.append(r)
    return results


def summarise(results: list[LoopResult]) -> str:
    """Compact multi-line summary suitable for the next prompt."""
    if not results:
        return "(no feedback loops ran)"
    lines = [r.short() for r in results]
    failures = [r for r in results if not r.ok and not r.soft]
    if failures:
        lines.append("\n-- failure output --")
        for r in failures:
            lines.append(f"\n## {r.name}\n{r.output}")
    return "\n".join(lines)


def all_blocking_passed(results: list[LoopResult]) -> bool:
    return all(r.ok for r in results if not r.soft)
