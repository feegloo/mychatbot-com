---
name: import-next-ui-component
description: 'Import another frontend Vue component into the standalone ui app. Use when: embedding the next component from frontend/src into ui/src/App.vue or another ui host component; wiring router/runtime support for imported frontend components; adding unit and Playwright coverage for ui component imports; fixing cross-root Vite, asset, or duplicated vue/vue-router runtime issues during ui imports.'
argument-hint: 'Component path and target host area, e.g. "frontend/src/pages/HomePage.vue into ui right column"'
---

# Import Next Component Into ui

Use this workflow when the `ui/` app needs to host another component that lives under `frontend/src/`.

## Goals

- Keep the imported component working inside `ui/`
- Avoid breaking the main `frontend/` app
- Validate with `ui` unit tests, `ui` e2e tests, and a build check

## Procedure

1. Import the component into the target `ui` host file, usually `ui/src/App.vue`.
2. If the imported component depends on router injection, create a lightweight router in `ui/src/main.ts` and add a catch-all placeholder route.
3. In `ui/vite.config.ts` and `ui/vitest.config.ts`, add a dedicated alias for the imported external component and allow parent-directory filesystem access.
4. Deduplicate `vue` and `vue-router` in both Vite configs so the imported component and the `ui` host share the same runtime instance.
5. If the imported component expects public assets like `/logo.svg`, mirror the needed assets into `ui/public/` or update the asset path intentionally.
6. Add or update `ui` unit tests to assert the imported component actually renders in the target area.
7. Add or update `ui` Playwright coverage to verify the imported component renders in the browser.
8. Validate with:
   ```bash
   cd ui && npm test
   cd ui && npm run build
   cd ui && npm run e2e
   ```
9. If the user asked to keep the main frontend safe too, run a narrow frontend validation such as:
   ```bash
   cd frontend && npm run build
   ```

## Common Pitfalls

- Importing directly from `frontend/src` without deduping `vue` and `vue-router` can create duplicate runtime instances and break router injection.
- Letting `ui` TypeScript config include the whole frontend tree can surface unrelated frontend errors. Prefer a dedicated alias plus a local `.d.ts` module declaration for the imported component.
- Imported frontend components may assume assets exist in `/public`; the standalone `ui` app needs its own copy if it serves those paths.
- Passing unit tests is not enough here. Always include a browser-level Playwright check because cross-root Vite imports can fail differently at runtime.
