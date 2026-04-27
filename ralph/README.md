# Ralph Wiggum Loop — Autonomous AI Coding Agent

> _"Me fail English? That's unpossible!"_ — Ralph Wiggum

A self-driving AI coding agent harness for **chatrag-app**. You drop a folder of
input files (PDF / PNG / TXT / MD / DOCX / XLSX) describing a feature you want
built; Ralph describes those files into a single PRD, hands it to a code-writing
agent (GitHub Copilot Coding Agent or Claude Code), and runs the
[Ralph Wiggum loop](https://www.aihero.dev/tips-for-ai-coding-with-ralph-wiggum)
until the feature is shipped or the iteration cap is hit.

## Layout

```
ralph/
├── README.md                       # this file
├── agent_ralph_loop.py             # core loop engine (entry point)
├── describe_task.py                # turn input files → description-{hash}.md
├── file_describer.py               # multi-format file → text describer
├── feedback_loops.py               # typecheck / test / lint runners
├── copilot_agent.py                # GitHub Copilot Coding Agent driver
├── claude_agent.py                 # Claude Code CLI driver (alt provider)
├── sandbox.py                      # Docker sandbox wrapper
├── requirements.txt
├── run.sh                          # local runner
├── tasks/                          # YOU put input files here, one folder per task
│   └── example/                    # see `example/` for the layout convention
│       ├── goal.md                 # plain-English what you want built
│       └── ...                     # any number of .pdf .png .txt .docx etc.
└── state/                          # generated, gitignored
    ├── description-<hash>.md       # PRD generated from a task folder
    ├── progress-<hash>.txt         # progress log (one entry per iteration)
    └── commits-<hash>.log          # SHAs committed by ralph this run
```

Files prefixed with `agent_ralph_loop` (anything in this `ralph/` folder
matching `agent_ralph_loop.*`, `describe_task.*`, `feedback_loops.*`,
`copilot_agent.*`, `claude_agent.*`, `sandbox.*`, `file_describer.*`) are the
loop's own machinery and are excluded from "input task files" by convention.

## Quick start (HITL — local, single iteration)

```bash
cd ralph
pip install -r requirements.txt
export OPENAI_API_KEY=...           # for image / file description
export GITHUB_TOKEN=...              # optional — for Copilot Coding Agent

# 1. drop your inputs
mkdir -p tasks/my-feature
cp ~/Downloads/spec.pdf tasks/my-feature/
cp ~/Downloads/mockup.png tasks/my-feature/
echo "Goal: implement full-text search for conversations" \
  > tasks/my-feature/goal.md

# 2. one-shot HITL run (single iteration, no commit)
./run.sh --task my-feature --iterations 1 --hitl

# 3. AFK run — up to 10 iterations, commit per feature, freeze-aborts
./run.sh --task my-feature --iterations 10
```

## How it works

Each iteration of `agent_ralph_loop.py` does:

1. **Describe** input files in `tasks/<task>/` → builds
   `state/description-<hash>.md` (only on first iteration; reused after).
2. **Read repo state**: current branch, last commit SHA, dirty status.
3. **Read progress** from `state/progress-<hash>.txt` (so the agent skips
   exploration).
4. **Invoke the coding agent** (Copilot or Claude) with the description +
   progress + explicit "ONE small commit per iteration" instructions.
5. **Run feedback loops**: TypeScript, ESLint (warning only), tests for any
   touched workspace area (frontend / backend / python).
6. **Commit** the diff with a generated message. Append entry to
   `progress-<hash>.txt`.
7. **Freeze detection**: if the last 2 commits have an identical diff, abort.
8. **Completion check**: ask the LLM whether the current repo state satisfies
   `description-<hash>.md`. If yes → emit `<promise>COMPLETE</promise>` and
   exit. Else → next iteration (up to `--iterations`, default 10).

When the loop completes, Ralph optionally:

- Pushes the working branch (`ralph/<task>`)
- Opens a draft PR via `gh`
- Marks it ready for review
- Waits 10 minutes, then comments
  `@copilot fix all comments and suggestions from AI bots and human reviewers, then merge to main`

## Ralph Wiggum Loop tips applied (from the AIhero article)

| # | Tip                            | Where it lives                                         |
| - | ------------------------------ | ------------------------------------------------------ |
| 1 | Ralph is a loop                | `agent_ralph_loop.py` — same prompt, repeated          |
| 2 | HITL → AFK                     | `--hitl` flag (1 iter, no commit) + `--iterations N`   |
| 3 | Define the scope               | `description-<hash>.md` with explicit goal + acceptance |
| 4 | Track progress                 | `state/progress-<hash>.txt`, committed with each diff   |
| 5 | Use feedback loops             | `feedback_loops.py` (tsc / vitest / pytest / ruff)      |
| 6 | Take small steps               | Prompt forces "ONE feature, ONE commit per iteration"   |
| 7 | Prioritize risky tasks         | Prompt orders: arch → integration → unknowns → polish   |
| 8 | Explicitly define quality      | Inherits `.github/copilot-instructions.md`              |
| 9 | Use Docker sandboxes           | `sandbox.py` (`--sandbox` flag)                        |
| 10 | Pay to play                   | Configurable provider / model via env                   |
| 11 | Make it your own              | Pluggable agent drivers (`copilot_agent`, `claude_agent`) |

## Hosting

Two deployment modes:

- **Local**: `./ralph/run.sh` — what you use day-to-day for HITL iteration.
- **GitHub Actions**: `.github/workflows/ralph.yml` — pushes to a `ralph/<task>`
  branch trigger an AFK loop on the runner, which in turn dispatches
  feature-implementation work to the Copilot Coding Agent. Secrets:
  `OPENAI_API_KEY`, `CLAUDE_API_KEY` (optional).

## Configuration

All env-driven. Defaults shown.

| var                       | default            | meaning                                  |
| ------------------------- | ------------------ | ---------------------------------------- |
| `RALPH_AGENT_PROVIDER`    | `copilot`          | `copilot` \| `claude`                    |
| `RALPH_MAX_ITERATIONS`    | `10`               | hard cap                                 |
| `RALPH_DESCRIBE_MODEL`    | `gpt-4o-mini`      | for file description                    |
| `RALPH_COMPLETION_MODEL`  | `gpt-4o-mini`      | for "is it done?" checker               |
| `RALPH_BASE_BRANCH`       | `main`             | branch loop branches off                 |
| `RALPH_PR_AUTOMERGE`      | `false`            | enable automerge after Copilot fixup     |
| `RALPH_DRY_RUN`           | `false`            | don't commit / push                      |
| `OPENAI_API_KEY`          | —                  | required for describe + completion check |
| `CLAUDE_API_KEY`          | —                  | required if provider=claude              |
| `GITHUB_TOKEN`            | —                  | required for Copilot Coding Agent / PR   |

## What it deliberately does NOT do

- Run against your home directory — use `--sandbox` for real AFK loops.
- Auto-merge by default. PRs land as drafts; you flip ready+merge yourself
  unless `RALPH_PR_AUTOMERGE=true`.
- Modify files outside the workspace root.
- Re-run the file describer if `state/description-<hash>.md` already exists
  (delete it to regenerate).
