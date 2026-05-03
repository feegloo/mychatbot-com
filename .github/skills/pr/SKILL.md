---
name: pr
description: 'Address all unresolved Qodo Merge AI review comments on a GitHub pull request. Use when: a PR has Qodo review comments you want to fix automatically; you want to apply every Qodo "Agent Prompt" fix without copy-pasting manually; you want a commit + PR comment confirming all Qodo issues were addressed.'
argument-hint: 'GitHub PR URL, e.g. https://github.com/owner/repo/pull/123'
---

# Address Qodo Review Comments

**Trigger:** `/pr {URL}` — pass a GitHub PR URL as the argument.

Reads every unresolved **Qodo** reviewer comment on the given pull request, applies
the embedded "Agent Prompt" fix for each issue, runs lint and tests, commits the
result, replies to each Qodo thread with the short commit hash, and posts a
summary resolution comment in the PR.

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

### Step 3 — Collect Qodo review threads

Use the `pull_request_read` tool with `method: "get_review_comments"` to retrieve
all review threads on the PR.

**Filter criteria — keep a thread if ALL of the following are true:**

| Criterion | Value |
|-----------|-------|
| `thread.comments[0].author` | `"qodo-code-review"` |
| `thread.is_resolved` | `false` |
| `thread.is_outdated` | `false` — skip outdated threads; the code they reference no longer exists at the same location. Include them in the resolution comment under **"Skipped (outdated thread)"**. |

### Step 4 — Announce intent on each thread

Before applying any fix, post a reply comment on **each** qualifying Qodo review
thread (using the GitHub MCP comment tool):

```
@copilot apply changes based on the comments in this thread
```

This mirrors what GitHub's "Fix batch with Copilot" button does and creates an
audit trail showing the agent is processing the thread.

### Step 5 — Extract the Agent Prompt from each thread

Each Qodo comment body follows this HTML structure:

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

**Extraction rules:**

1. Find the `<details>` block whose `<summary>` contains the text `Agent Prompt`.
2. Within that `<details>` block, locate the triple-backtick fenced code block and
   extract everything between the opening and closing ` ``` ` delimiters.
3. That extracted text is the **Agent Prompt** — treat it as a complete,
   self-contained instruction for fixing the issue.
4. Also record the comment's `html_url` and the issue title from the comment body
   (the bolded first line, e.g. `"No tests for paste upload"`).

### Step 6 — Apply every fix

Work through each extracted Agent Prompt **one at a time**:

1. Read the "Fix Focus Areas" to understand which files need changes.
2. Apply the minimum code change that resolves the issue described in the prompt.
   Follow all conventions from `.github/copilot-instructions.md`.
3. Stage the changed files: `git add <changed-files>`.

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
git commit -m "fix: address Qodo review comments on PR #<pull_number>"
```

Record the short SHA (first 7 characters) as `COMMIT_HASH`.

Push the branch to origin so the fixes are visible on GitHub:

```bash
git push origin <head-branch>
```

(Alternatively, use the `report_progress` tool to push and update the PR
description simultaneously.)

### Step 9 — Reply to each Qodo thread with the commit hash

For every thread that was **resolved** in Step 6, post a follow-up reply
containing only the short commit hash:

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
## Qodo review comments addressed

All actionable unresolved Qodo review comments have been processed in commit <COMMIT_HASH>.

### Issues resolved

| # | Issue | Comment |
|---|-------|---------|
| 1 | <issue-title-1> | <html_url-1> |
| 2 | <issue-title-2> | <html_url-2> |

Each fix follows the corresponding Agent Prompt provided by Qodo.

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
| `npm run lint` reports errors that `--fix` cannot resolve automatically | Fix them manually as part of the staged changes, then re-run lint to confirm green. |
| Applying a fix breaks existing tests | Debug and revise until tests pass. If irresolvable, revert that fix and list it under **"Not addressed (test failure)"** with a brief reason. |
| The PR branch cannot be fetched (e.g., merged/deleted) | Inform the user and stop. |
| No unresolved Qodo comments found | Reply: *"No unresolved Qodo review comments found on this PR."* and stop. |

---

## Notes

- Always follow project conventions from `.github/copilot-instructions.md` when
  generating fixes.
- Prefer minimal, surgical changes — fix exactly what the Agent Prompt describes;
  do not refactor unrelated code.
- If multiple Agent Prompts touch the same file, apply them together so the file
  is only edited once, reducing conflicts.
- The `report_progress` tool can be used instead of a bare `git push` to push the
  commit and update the PR description simultaneously.
