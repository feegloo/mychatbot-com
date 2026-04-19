---
name: refactor
description: 'Perform a multi-step deep refactor across frontend, backend, python, and infra. Use when: codebase cleanup, dead code removal, unused dependency audit, module extraction, code simplification, adding debug logs, test coverage improvement, or tooling/linter/formatter setup. Covers Vue 3, Node/Koa, Python/LangChain projects.'
argument-hint: 'Which area(s) to refactor: frontend, backend, python, infra, or all'
---

# Deep Multi-Step Refactor

Perform a thorough, phased refactoring across one or more project areas (`frontend/`, `backend/`, `python/`, `infra/`). Each phase builds on the previous. Run phases in order — skipping ahead risks breaking changes.

## Scope Selection

If the user specifies an area (e.g., "just backend"), only run phases for that area. Default: **all areas**.

| Area | Stack | Root |
|------|-------|------|
| frontend | Vue 3 + TypeScript + Vite | `frontend/` |
| backend | Node + Koa + TypeScript | `backend/` |
| python | Python 3 + LangChain + FastAPI | `python/` |
| infra | Docker, Cloud Run, shell scripts | `infra/` |

## Pre-Flight

Before starting any phase:

1. **Check for uncommitted changes** — warn user if working tree is dirty.
2. **Run existing tests** to establish baseline:
   - `cd frontend && npm test`
   - `cd backend && npm test`
   - `cd python && python -m pytest`
3. **Record baseline** — note which tests pass/fail before any changes.
4. **Create a working branch** — suggest `refactor/<area>-<date>` naming.

## Commit Strategy

Work freely across phases, then **squash all changes into a single commit** at the end (or per area if refactoring multiple areas). Keep the working tree messy during refactoring — clean it up at the end.

## Phase 1: Tooling & Configuration

**Goal:** Set up linting, formatting, type checking, and developer ergonomics **first** so tooling catches issues during later phases.

See [tooling-configs.md](./references/tooling-configs.md) for ready-to-use configs.

### Frontend

1. **ESLint** — install `eslint` + `@vue/eslint-config-typescript` + `eslint-plugin-vue`:
   ```bash
   cd frontend && npm install -D eslint @eslint/js eslint-plugin-vue typescript-eslint
   ```
   Create `eslint.config.js` with Vue 3 + TypeScript recommended rules.

2. **Prettier** — install and configure:
   ```bash
   npm install -D prettier eslint-config-prettier
   ```
   Create `.prettierrc`: `{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }`

3. **Type checking** — ensure `vue-tsc --noEmit` passes clean in build script.

4. **Add lint/format scripts** to `package.json`:
   ```json
   "lint": "eslint src/",
   "lint:fix": "eslint src/ --fix",
   "format": "prettier --write src/"
   ```

### Backend

1. **ESLint** — install `eslint` + `typescript-eslint`:
   ```bash
   cd backend && npm install -D eslint @eslint/js typescript-eslint
   ```
   Create `eslint.config.js` with TypeScript recommended rules.

2. **Prettier** — same config as frontend for consistency.

3. **pino logger** — install `pino`:
   ```bash
   npm install pino
   ```
   Create `src/logger.ts` exporting a configured pino instance. Set level from `LOG_LEVEL` env var (default: `info`).

4. **Add lint/format scripts** to `package.json`.

### Python

1. **Ruff** — install as linter + formatter:
   ```bash
   pip install ruff
   ```
   Create `ruff.toml` (see [tooling-configs.md](./references/tooling-configs.md)).

2. **Add to Makefile** (python/Makefile):
   ```makefile
   lint:
   	ruff check .
   format:
   	ruff format .
   ```

### Infra

1. **ShellCheck** for shell scripts — `shellcheck infra/*.sh infra/**/*.sh`.
2. **Hadolint** for Dockerfiles — `hadolint Dockerfile backend/Dockerfile python/Dockerfile.worker`.

### CI Integration (optional)

Suggest a `.github/workflows/lint.yml` that runs lint + typecheck + tests on PR. See [tooling-configs.md](./references/tooling-configs.md).

## Phase 2: Dead Code Removal

**Goal:** Remove unreachable code, unused exports, and orphan files.

### Procedure

For each area:

1. **Find unused exports** — search for exported symbols that are never imported elsewhere.
2. **Find orphan files** — files not imported by any other file (excluding entry points, test files, and config files).
3. **Find dead branches** — unreachable `if`/`else` blocks, commented-out code blocks (>5 lines), and `TODO`/`FIXME` code that is clearly stale.
4. **Remove** — delete identified dead code. Commit after each area.
5. **Verify** — re-run tests to confirm nothing broke.

### Area-specific guidance

- **Frontend:** Check for unused Vue components (not referenced in any template or router), unused composables, unused util functions. Use `grep -r` on component names across `src/`.
- **Backend:** Check for unused route handlers, unused middleware, unused repository methods. Trace from `app.ts` → routes → handlers.
- **Python:** Check for unused `shared/` modules not imported by any script, server, or worker. Check for experimental/scratch files (e.g., `_test_*.py` at root).
- **Infra:** Check for unused shell scripts, orphan config files, unused Docker stages.

## Phase 3: Unused Dependency Audit

**Goal:** Remove packages that are installed but never imported.

### Procedure

For each area:

1. **List all dependencies** from `package.json` (frontend/backend) or `requirements.txt` (python).
2. **Search codebase** for each dependency's import/require.
3. **Flag unused** — any dependency not imported anywhere in `src/` (or `shared/` for python).
4. **Flag duplicates** — packages that overlap in functionality.
5. **Uninstall unused** — `npm uninstall <pkg>` or remove from `requirements.txt` + `pip uninstall`.
6. **Verify** — rebuild and re-run tests.

### Caution

- Some deps are used indirectly (e.g., `@sentry/profiling-node` loaded by Sentry config, `koa-bodyparser` as middleware). **Check middleware registration and plugin configs** before removing.
- Python deps may be used inside Jupyter notebooks — check `.ipynb` files too.
- `devDependencies` used only in build/test pipelines (vitest, playwright, tsx) are valid — don't remove those.

## Phase 4: Module Extraction & Code Organization

**Goal:** Extract shared logic, break up large files, establish consistent module boundaries.

### Procedure

For each area, review and restructure:

#### Frontend (`frontend/src/`)

| Target | Extract to | Criteria |
|--------|-----------|----------|
| Reusable logic in components | `composables/use<Name>.ts` | Logic used by ≥2 components, or >30 lines of non-template JS |
| Constants / magic strings | `constants/index.ts` | Hardcoded strings, config values, enum-like objects |
| Type definitions scattered in components | `types/index.ts` or `types/<domain>.ts` | Interfaces/types used by ≥2 files |
| API call logic mixed into components | `api/` or `api.ts` (already exists — consolidate) | HTTP calls should go through api layer |
| Large components (>200 lines of `<script>`) | Smaller components + composable | Single Responsibility Principle |

#### Backend (`backend/src/`)

| Target | Extract to | Criteria |
|--------|-----------|----------|
| Business logic in route handlers | `services/<domain>.ts` | Route handler >50 lines or logic reused across routes |
| Shared constants | `constants.ts` | Hardcoded values, status codes, messages |
| Middleware logic | `middleware/<name>.ts` | Custom middleware not in its own file |
| Type definitions | `types.ts` (already exists — review) | Keep domain types consolidated |
| Utility functions in routes | `utils/<name>.ts` | Generic helpers not specific to one route |

#### Python (`python/`)

| Target | Extract to | Criteria |
|--------|-----------|----------|
| Shared config / constants | `shared/config.py` (exists — review) + `shared/constants.py` | Magic strings, model names, defaults |
| Duplicate logic across scripts | `shared/` modules | Code repeated in ≥2 entry points |
| Large modules (>300 lines) | Split into focused modules | Single Responsibility Principle |
| Test utilities | `tests/conftest.py` | Shared fixtures, mocks, helpers |

#### Infra (`infra/`)

| Target | Action | Criteria |
|--------|--------|----------|
| Repeated env vars | Centralize in `.env.gcp` template | Same var defined in multiple places |
| Long shell scripts | Extract functions, add error handling | Scripts >100 lines |
| Docker stages | Optimize layer caching, reduce image size | Review multi-stage build |

### Guidelines

- **Move, don't copy.** Update all imports after moving code.
- **One commit per extraction.** Makes rollback granular.
- **Keep backward compatibility** — if something is exported from the old location, re-export from new location temporarily if other code depends on it.

## Phase 5: Code Simplification

**Goal:** Reduce complexity, improve readability, remove unnecessary abstractions.

### Procedure

For each area:

1. **Reduce nesting** — flatten deeply nested `if/else`, use early returns and guard clauses.
2. **Simplify async patterns** — replace `.then()` chains with `async/await` where mixed.
3. **Remove unnecessary abstractions** — single-implementation interfaces, wrapper functions that just forward calls, classes with one method.
4. **Consolidate similar code** — merge near-duplicate functions that differ by 1-2 lines.
5. **Simplify conditionals** — extract complex boolean expressions into named variables.
6. **Use modern syntax** — optional chaining (`?.`), nullish coalescing (`??`), destructuring where it aids clarity.

### Area-specific

- **Frontend:** Simplify component props/emits, use `defineModel()` where applicable, leverage Vue 3.4+ features.
- **Backend:** Simplify Koa middleware chains, use Zod `.parse()` consistently for validation.
- **Python:** Use f-strings consistently, replace manual dict building with dataclasses/Pydantic models where appropriate, simplify LangChain chain construction.

## Phase 6: Debug Logging

**Goal:** Add structured, production-safe debug logs at key decision points.

### Conventions

| Area | Logger | Level |
|------|--------|-------|
| Frontend | `console.debug()` | Stripped in production build (configure in Vite) |
| Backend | `pino` (installed in Phase 1) | `debug` level — silent unless `LOG_LEVEL=debug` |
| Python | `logging.getLogger(__name__)` | `DEBUG` level — controlled by `LOG_LEVEL` env var |

### Where to Add Logs

- **Entry points:** Log incoming request params (sanitized — no PII, no secrets).
- **Decision branches:** Log which branch was taken and why (e.g., "using cached result", "falling back to default model").
- **External calls:** Log before/after calls to databases, APIs, vector stores, LLM providers (log duration, not payloads).
- **Error recovery:** Log caught exceptions with context before re-throwing or returning error responses.
- **Configuration:** Log resolved config values at startup (mask secrets).

### Anti-patterns

- Do NOT log request/response bodies (PII risk).
- Do NOT log secrets, tokens, or API keys.
- Do NOT add logs inside tight loops (performance).
- Do NOT use `console.log` in backend — use `pino` logger.

## Phase 7: Test Refactoring & Coverage

**Goal:** Improve test organization, add missing tests, ensure each module has corresponding tests.

### Procedure

1. **Audit existing tests** — map each test file to the module it covers.
2. **Identify gaps** — modules with no corresponding test file.
3. **Prioritize** — test critical paths first:
   - Frontend: API layer, composables, key components (ChatMessage, ConversationPage)
   - Backend: Route handlers, services, storage abstraction, security module
   - Python: Chunkers, extractors, RAG pipeline, config resolution
4. **Refactor existing tests:**
   - Extract shared fixtures/mocks to setup files
   - Use descriptive test names: `it('returns 404 when conversation not found')`
   - Group related tests with `describe` blocks
   - Remove test duplication
5. **Add unit tests** for uncovered modules.
6. **Add/improve e2e tests:**
   - Frontend: Playwright tests for core user flows (upload → ask → answer)
   - Backend: Supertest integration tests for API routes
   - Python: Integration tests for indexing → querying pipeline
7. **Verify coverage** — run with coverage reporters and review.

## Phase 7: Performance Profiling & Optimization

**Goal:** Identify and optimize any new performance bottlenecks introduced during refactoring.

1. **Profile** — use browser dev tools for frontend, Node.js profiler for backend, and cProfile for Python.
2. **Identify bottlenecks** — look for slow functions, excessive re-renders,
database query hotspots, or inefficient algorithms.
3. **Optimize** — refactor slow code paths, add caching, optimize database queries,or adjust indexing strategies.
4. **Verify** — re-profile after optimizations to confirm improvements.
5. **Add performance tests** — if applicable, add tests that assert certain operations complete within a time threshold.
6. **Monitor in production** — ensure logging includes performance metrics for key operations to catch regressions.
7. **Document** — note any significant optimizations in code comments or documentation for future reference.
8. **CI Performance Checks** (optional) — consider adding performance regression checks in CI for critical paths.
9. **Communicate** — if optimizations involve trade-offs (e.g., increased memory usage for faster response), document and communicate these decisions to the team.
10. **Iterate** — performance optimization is an ongoing process. Regularly review and profile the application as new features are added.
11. **Stay informed** — keep up with best practices and new tools for performance optimization in your tech stack.
12. **Balance** — remember that readability and maintainability are also important. Avoid over-optimizing at the cost of code clarity.
13. **Celebrate** — acknowledge the hard work that goes into performance optimization and the benefits it brings to users!
14. **Plan for future** — consider how future features might impact performance and design with scalability in mind.


### Commands

```bash
# Frontend
cd frontend && npm test -- --coverage

# Backend
cd backend && npm test -- --coverage

# Python
cd python && python -m pytest --cov=shared --cov-report=html
```

## Completion Checklist

After all phases, verify:

- [ ] All existing tests still pass (no regressions)
- [ ] No unused dependencies remain
- [ ] No orphan files or dead exports
- [ ] Each area has consistent module structure
- [ ] Debug logs present at key decision points
- [ ] Test coverage improved (compare to baseline)
- [ ] Linters and formatters configured and passing
- [ ] All changes committed with descriptive messages per phase
- [ ] README or ARCHITECTURE.md updated if structure changed significantly
