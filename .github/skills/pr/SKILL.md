---
name: pr
description: 'Address all unresolved Qodo Merge AI review comments on a GitHub pull request. Use when: a PR has Qodo review comments you want to fix automatically; you want to apply every Qodo "Agent Prompt" fix without copy-pasting manually; you want a commit + PR comment confirming all Qodo issues were addressed.'
argument-hint: 'GitHub PR URL, e.g. https://github.com/owner/repo/pull/123'
---

# Address Qodo Review Comments

Reads every unresolved **Qodo** reviewer comment on the given pull request, applies
the embedded "Agent Prompt" fix for each issue, commits the result, and posts a
resolution comment in the PR.

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

Extract `owner`, `repo`, and `pull_number` from the provided URL:

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

### Step 4 — Extract the Agent Prompt from each thread

Each Qodo comment body follows this HTML structure (angle-bracket entities written
literally here for clarity):

```
<details>
  <summary><strong>Agent Prompt</strong></summary>

  [triple-backtick code fence]
  ## Issue description
  …

  ## Fix Focus Areas
  - path/to/file.ts[L1-L2]
  …
  [closing triple-backtick]
</details>
```

**Extraction rules:**

1. Find the `<details>` block whose `<summary>` contains the text `Agent Prompt`.
2. Within that `<details>` block, locate the **triple-backtick fenced code block**
   (i.e. the region delimited by ` ``` ` on its own line) and extract everything
   between the opening and closing ` ``` ` delimiters.
3. That extracted text is the **Agent Prompt** — treat it as a complete,
   self-contained instruction for fixing the issue.
4. Also record the comment's `html_url` (needed for the resolution comment) and
   the issue title from the comment body (the bolded first line, e.g.
   `"No tests for paste upload"`).

### Step 5 — Apply every fix

Work through each extracted Agent Prompt **one at a time**:

1. Read the "Fix Focus Areas" to understand which files need changes.
2. Apply the minimum code change that resolves the issue described in the prompt.
   Follow all conventions from `.github/copilot-instructions.md`.
3. After applying each fix, run the narrowest relevant validation:
   - For frontend changes: `cd frontend && npm test`
   - For backend changes: `cd backend && npm test`
   - For python changes: `cd python && python3.11 -m pytest`
4. If a fix causes a test failure, revise until tests pass before moving on.
5. Stage the changed files: `git add <changed-files>`.

> **Important:** Do **not** commit after each individual fix. Accumulate all
> staged changes and commit once in Step 6.

### Step 6 — Commit all fixes

After all Agent Prompts have been applied and tested, commit:

```bash
git commit -m "fix: address Qodo review comments on PR #<pull_number>"
```

Record the resulting commit hash (`COMMIT_HASH`).

Push the branch:

```bash
git push origin <head-branch>
# (or use report_progress to push)
```

### Step 7 — Post a resolution comment on the PR

Use the GitHub MCP tool or the `issue_comment` action to post a single PR-level
comment summarising all addressed issues.

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

Replace `<COMMIT_HASH>` with the short SHA (first 7 characters is fine).

---

## Handling Edge Cases

| Situation | Action |
|-----------|--------|
| A thread has `is_outdated: true` | Skip it — the underlying code has changed; the fix would be speculative. Include it in the resolution comment under **"Skipped (outdated thread)"**. |
| A thread is already `is_resolved: true` | Skip it silently. |
| A Qodo comment has **no** triple-backtick Agent Prompt block | Skip it and include it under **"Skipped (no Agent Prompt)"** in the resolution comment. |
| Applying a fix breaks existing tests | Debug and fix until tests pass. If irresolvable, skip that item and include it under **"Not addressed (test failure)"** with a brief reason. |
| The PR branch cannot be fetched (e.g., merged/deleted) | Inform the user and stop. |
| No unresolved Qodo comments found | Reply: *"No unresolved Qodo review comments found on this PR."* and stop. |

---

## Example Agent Prompt (for reference)

Below is a representative Agent Prompt extracted from a real Qodo comment. This is
**only an example** — the actual prompts come from the PR at runtime.

```
## Issue description
New paste-to-upload behavior was added without accompanying automated tests.

## Issue Context
The PR introduces `extractPastedFiles()` (MIME filtering + auto-naming) and new
`@paste` handlers in both chat input pages. These behaviors should be covered by
unit tests (for extraction logic) and/or e2e tests (for paste-upload UX) so
regressions are caught.

## Fix Focus Areas
- frontend/src/composables/useFilePaste.ts[10-33]
- frontend/src/pages/ConversationPage.vue[1015-1020]
- frontend/src/pages/HomePage.vue[361-367]
```

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
