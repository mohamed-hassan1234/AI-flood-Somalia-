# Testing strategy

The repository uses layered evidence rather than treating one green suite as proof of the whole
system.

## Backend

From `backend/`:

```text
..\.venv\Scripts\python.exe -m ruff check app
..\.venv\Scripts\python.exe -m mypy app
..\.venv\Scripts\python.exe -m pytest -q
```

Pytest covers authorization and IDOR controls, ingestion/quarantine, geography, migrations,
domain baselines, human warning/verification/action workflows, notification retry/escalation,
model governance, public projections, reports, observability, restore verification, and the
complete synthetic operational scenario.

## Frontend component integration

From `frontend/`:

```text
npm run check
npm test -- --run
npm run build
```

Vitest and Testing Library verify governed loading, empty, error/unauthorized, stale/missing-data,
workflow, dashboard, and public states. The production Vite build is a separate gate.

## Browser E2E

Install the browser once, then execute Playwright:

```text
npx playwright install chromium
npm run test:e2e
```

The browser suite starts a real Vite server. Its API boundary is deterministically intercepted
with records labeled `SYNTHETIC / DEVELOPMENT DATA`; it does not claim production data or network
integration. Current scenarios verify that the public warning projection sends no bearer token,
that authenticated executive requests carry a bearer token while switching from national to
an authorized regional projection, and that Somali preference persists across reloads with the
correct document language. The backend synthetic operational E2E test separately covers
signal → warning → verification → exposure → action → notification → outcome behavior.

CI installs Chromium, runs all three frontend gates, executes the backend suite, checks a MySQL
migration/seed/dump/restore cycle, runs dependency scans, and enforces the synthetic HTTP/database
performance regression threshold.
