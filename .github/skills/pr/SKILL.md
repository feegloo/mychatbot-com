---
name: pr
description: 'Address all unresolved AI review comments (Qodo Merge and GitHub Copilot) on a GitHub pull request. Use when: a PR has Qodo or Copilot review comments you want to fix automatically; you want to apply every Qodo "Agent Prompt" fix without copy-pasting manually; you want to resolve Copilot inline review suggestions; you want a commit + PR comment confirming all AI issues were addressed.'
argument-hint: 'GitHub PR URL, e.g. https://github.com/owner/repo/pull/123'
---

# Address AI Review Comments (Qodo + Copilot)

**Trigger:** `/pr {URL}` — pass a GitHub PR URL as the argument.

Reads every unresolved **Qodo** and **GitHub Copilot** reviewer comment on the
given pull request, applies each fix, runs lint and tests, commits the result,
replies to each thread with the short commit hash, and posts a summary resolution
comment in the PR.

---

## Prerequisites

- GitHub MCP tools (`pull_request_read`, `issue_read`, etc.) must be available.
- The local working tree must be checked out to the PR branch (or you must
  be able to check it out with `git fetch origin <branch> && git checkout <branch>`).
- The repository's usual build / test toolchain must be available (Node, Python,
  etc.) to validate fixes before committing.

---

## Procedure

### Step 1 — Parse the PR URL

Extract `owner`, `repo`, and `pull_number` from the argument:

```
https://github.com/<owner>/<repo>/pull/<pull_number>
```

### Step 2 — Check out the PR branch

Use the GitHub MCP `get` method to fetch PR details and find the head branch name,
then check it out locally:

```bash
git fetch origin <head-branch>
git checkout <head-branch>
```

### Step 3 — Collect AI review threads

Use the `mcp_gitkraken_pull_request_get_comments` tool to retrieve all review
comments and threads on the PR. This returns both `prComments` (inline code
review comments) and `reviewComments` (PR-level review summaries).

**Sources to process:**

1. **Qodo threads** — filter `reviewComments` (or inline threads) where the first
   comment's author matches `"qodo-code-review"`. These contain a structured
   Agent Prompt block (see Step 5).

2. **Copilot inline comments** — filter `prComments` where `author` is
   `"Copilot"` or `"copilot-pull-request-reviewer[bot]"`. These are plain-text
   suggestions without an Agent Prompt block; treat the full comment body as the
   fix instruction.

**Filter criteria — keep a comment/thread if ALL of the following are true:**

| Criterion | Value |
|-----------|-------|
| `author` | `"qodo-code-review"`, `"Copilot"`, or `"copilot-pull-request-reviewer[bot]"` |
| `is_resolved` | `false` (skip already-resolved threads) |
| `is_outdated` | `false` — skip outdated threads; include them under **"Skipped (outdated thread)"** in the resolution comment |

### Step 4 — Announce intent on each thread

Before applying any fix, post a reply comment on **each** qualifying thread
(using the GitHub MCP comment tool):

```
@copilot apply changes based on the comments in this thread
```

This mirrors what GitHub's "Fix batch with Copilot" button does and creates an
audit trail showing the agent is processing the thread.

### Step 5 — Extract fix instructions from each comment

**For Qodo comments** — each body follows this HTML structure:

```
<details>
  <summary><strong>Agent Prompt</strong></summary>

  ```
  ## Issue description
  …

  ## Fix Focus Areas
  - path/to/file.ts[L1-L2]
  …
  ```
</details>
```

Extraction rules:
1. Find the `<details>` block whose `<summary>` contains the text `Agent Prompt`.
2. Within that block, locate the triple-backtick fenced code block and extract
   everything between the opening and closing ` ``` ` delimiters.
3. That extracted text is the **Agent Prompt** — treat it as a complete,
   self-contained instruction for fixing the issue.
4. Also record the comment's `url` and derive an issue title from the bolded
   first line of the comment body (e.g. `"No tests for paste upload"`).

**For Copilot comments** — the full comment `content` field is the fix
instruction. There is no Agent Prompt block. Use the comment `url` and derive a
title from the first sentence or the file/line context. The comment body describes
both the problem and the required fix in plain English — apply it literally.

### Step 6 — Apply every fix

Work through all collected fix instructions **one at a time** (Qodo Agent Prompts
first, then Copilot comments):

1. **Qodo:** Read "Fix Focus Areas" to find the target files. Apply the minimum
   change that resolves the issue.
2. **Copilot:** The comment body directly describes the problem and what to
   change. Read the referenced file and line range, then apply the described fix.
3. Follow all conventions from `.github/copilot-instructions.md`.
4. Stage the changed files: `git add <changed-files>`.

> **Important:** Do **not** commit after each individual fix. Accumulate all
> staged changes and commit once in Step 7.

### Step 7 — Lint and test

After all fixes have been applied, run lint then the test suite and fix any
failures before committing.

**Frontend / backend (Node):**

```bash
# lint — auto-fix what can be fixed, then fail fast on remaining errors
cd frontend && npm run lint -- --fix
cd backend && npm run lint -- --fix

# tests
cd frontend && npm run test
cd backend && npm run test
```

**Python:**

```bash
cd python && python3.11 -m ruff check --fix .
cd python && python3.11 -m pytest
```

- If `npm run lint` reports unfixable errors after `--fix`, address them in the
  same staged changes before continuing.
- If tests fail, revise the relevant fix(es) until the suite is green. If a fix is
  irresolvable, revert it and move it to the **"Not addressed (test failure)"**
  section of the resolution comment.

Re-run lint and tests after every revision to confirm green status.

### Step 8 — Commit and push

Once lint and tests are fully green, commit **all** staged changes in a single
commit:

```bash
git commit -m "fix: address AI review comments on PR #<pull_number>"
```

Record the short SHA (first 7 characters) as `COMMIT_HASH`.

Push the branch to origin so the fixes are visible on GitHub:

```bash
git push origin <head-branch>
```

(Alternatively, use the `report_progress` tool to push and update the PR
description simultaneously.)

### Step 9 — Reply to each resolved thread with the commit hash

For every thread (Qodo or Copilot) that was **resolved** in Step 6, post a
follow-up reply containing only the short commit hash:

```
<COMMIT_HASH>
```

This links each review thread directly to the commit that fixed it, matching
GitHub's convention when you click "Mark as resolved with commit".

### Step 10 — Post a summary resolution comment

Use the GitHub MCP comment tool to post a single PR-level comment summarising all
outcomes.

**Comment format:**

```markdown
## AI review comments addressed

All actionable unresolved AI review comments (Qodo + Copilot) have been processed in commit <COMMIT_HASH>.

### Issues resolved

| # | Source | Issue | Comment |
|---|--------|-------|---------|
| 1 | Qodo | <issue-title-1> | <html_url-1> |
| 2 | Copilot | <issue-title-2> | <html_url-2> |

Qodo fixes follow the embedded Agent Prompt. Copilot fixes address the inline suggestion as described in each comment.

<!-- only include sections below when they contain entries -->

### Skipped (outdated thread)

| # | Issue | Comment |
|---|-------|---------|
| 1 | <issue-title> | <html_url> |

### Skipped (no Agent Prompt)

| # | Issue | Comment |
|---|-------|---------|
| 1 | <issue-title> | <html_url> |

### Not addressed (test failure)

| # | Issue | Comment | Reason |
|---|-------|---------|--------|
| 1 | <issue-title> | <html_url> | <brief description of blocking failure> |
```

Omit any section that has no entries (remove the heading and table entirely).

---

## Handling Edge Cases

| Situation | Action |
|-----------|--------|
| A thread has `is_outdated: true` | Skip it — the underlying code has changed; the fix would be speculative. Include it under **"Skipped (outdated thread)"**. |
| A thread is already `is_resolved: true` | Skip it silently. |
| A Qodo comment has **no** Agent Prompt block | Skip it and include it under **"Skipped (no Agent Prompt)"**. |
| A Copilot comment body is ambiguous or references a line that no longer exists | Skip it and include it under **"Skipped (outdated thread)"**. |
| `npm run lint` reports errors that `--fix` cannot resolve automatically | Fix them manually as part of the staged changes, then re-run lint to confirm green. |
| Applying a fix breaks existing tests | Debug and revise until tests pass. If irresolvable, revert that fix and list it under **"Not addressed (test failure)"** with a brief reason. |
| The PR branch cannot be fetched (e.g., merged/deleted) | Inform the user and stop. |
| No unresolved AI comments found | Reply: *"No unresolved AI review comments (Qodo or Copilot) found on this PR."* and stop. |

---

## Notes

- Always follow project conventions from `.github/copilot-instructions.md` when
  generating fixes.
- Prefer minimal, surgical changes — fix exactly what the Agent Prompt or Copilot
  comment describes; do not refactor unrelated code.
- If multiple comments touch the same file, apply them together so the file is
  only edited once, reducing conflicts.
- Copilot inline comments describe the problem in plain text; read the referenced
  file and line context before applying the fix to avoid misinterpretation.
- The `report_progress` tool can be used instead of a bare `git push` to push the
  commit and update the PR description simultaneously.
