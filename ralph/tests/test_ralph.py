"""Smoke / unit tests for the Ralph loop pure helpers.

Run from the repo root:
    python3.11 -m pytest ralph/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``ralph/`` importable as a flat package for these tests.
_RALPH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RALPH))


def test_describe_task_hash_is_stable(tmp_path, monkeypatch):
    import describe_task as dt

    monkeypatch.setattr(dt, "_ralph_root", lambda: tmp_path)
    task_dir = tmp_path / "tasks" / "x"
    task_dir.mkdir(parents=True)
    (task_dir / "goal.md").write_text("hello", encoding="utf-8")
    (task_dir / "spec.txt").write_text("body", encoding="utf-8")

    h1 = dt._task_hash(task_dir)
    h2 = dt._task_hash(task_dir)
    assert h1 == h2
    assert len(h1) == 12

    # Mutating a file should change the hash.
    (task_dir / "goal.md").write_text("hello world", encoding="utf-8")
    assert dt._task_hash(task_dir) != h1


def test_iter_task_files_skips_loop_machinery(tmp_path, monkeypatch):
    import describe_task as dt

    monkeypatch.setattr(dt, "_ralph_root", lambda: tmp_path)
    task_dir = tmp_path / "tasks" / "x"
    task_dir.mkdir(parents=True)
    (task_dir / "goal.md").write_text("g", encoding="utf-8")
    (task_dir / "agent_ralph_loop.py").write_text("# nope", encoding="utf-8")
    (task_dir / "feedback_loops.py").write_text("# nope", encoding="utf-8")
    (task_dir / ".hidden").write_text("nope", encoding="utf-8")

    files = sorted(p.name for p in dt._iter_task_files(task_dir))
    assert files == ["goal.md"]


def test_fallback_prd_includes_goal_and_files():
    import describe_task as dt

    out = dt._fallback_prd(
        task_name="t",
        descriptions={"a.md": "desc-a", "b.png": "desc-b"},
        goal="ship feature X",
    )
    assert "# Goal" in out
    assert "ship feature X" in out
    assert "`a.md`" in out and "`b.png`" in out
    assert "## Acceptance criteria" in out


def test_iteration_prompt_contains_required_sections():
    import agent_ralph_loop as loop

    p = loop.build_iteration_prompt(
        prd="THE-PRD",
        progress="THE-PROGRESS",
        branch="ralph/x",
        sha="deadbeefcafe",
        dirty=False,
        last_feedback="THE-FEEDBACK",
    )
    assert "THE-PRD" in p
    assert "THE-PROGRESS" in p
    assert "THE-FEEDBACK" in p
    assert "ralph/x" in p
    assert "deadbeef" in p
    assert loop._COMPLETE_TOKEN in p


def test_loop_result_short_format():
    import feedback_loops as fl

    assert fl.LoopResult("x", ok=True, output="").short() == "[OK] x"
    assert fl.LoopResult("x", ok=False, output="").short() == "[FAIL] x"
    assert fl.LoopResult("x", ok=False, output="", soft=True).short() == "[WARN] x"


def test_all_blocking_passed_ignores_soft_failures():
    import feedback_loops as fl

    results = [
        fl.LoopResult("typecheck", ok=True, output=""),
        fl.LoopResult("lint", ok=False, output="", soft=True),
    ]
    assert fl.all_blocking_passed(results) is True

    results.append(fl.LoopResult("test", ok=False, output=""))
    assert fl.all_blocking_passed(results) is False


def test_summarise_includes_failure_output():
    import feedback_loops as fl

    summary = fl.summarise([
        fl.LoopResult("a", ok=True, output="ok"),
        fl.LoopResult("b", ok=False, output="boom"),
    ])
    assert "[OK] a" in summary
    assert "[FAIL] b" in summary
    assert "boom" in summary


def test_describe_file_handles_unknown_binary(tmp_path):
    import file_describer as fd

    p = tmp_path / "weird.xyz"
    p.write_bytes(b"\x00\x01")
    assert fd.describe_file(p).startswith("[ralph: skipped unknown file type")


def test_describe_file_text(tmp_path):
    import file_describer as fd

    p = tmp_path / "small.txt"
    p.write_text("hello world", encoding="utf-8")
    # Short text should round-trip without an LLM summarise call.
    assert "hello world" in fd.describe_file(p)


@pytest.mark.parametrize("provider", ["copilot", "claude"])
def test_make_agent_returns_known_providers(provider, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "x/y")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    import agent_ralph_loop as loop

    a = loop.make_agent(provider)
    assert a.name == provider


def test_make_agent_rejects_unknown_provider():
    import agent_ralph_loop as loop

    with pytest.raises(ValueError):
        loop.make_agent("nonsense")
