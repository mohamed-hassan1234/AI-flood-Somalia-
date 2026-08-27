# Phase 05 — Production Frontend / Operational MVP

**Status:** COMPLETE (frontend), with one inherited upstream dependency documented below.
**Date:** 2026-08-27 · **Branch:** `main` · **HEAD at start:** `4d4faf5` · **Committed:** NO

---

## 1. What was built

A production operational frontend for the Somalia AI Early Warning & Early Action platform,
replacing the previous 25-file scaffold with a feature-organised React/TypeScript application of
51 source files (~14,400 lines).

The application consumes the existing FastAPI service under `/api/v1`. No backend code, ML
artefact, threshold, or Phase 03 intelligence semantic was modified.

---

## 2. Contract verification method

Before any code was written, the API contract was established from three independent sources and
cross-checked:

1. **Source reading** — `backend/app/modules/*/router.py` and `*/schemas.py`.
2. **Generated OpenAPI** — the FastAPI app was imported in an isolated virtualenv and
   `app.openapi()` executed, yielding **66 paths**. This confirmed the source reading exactly.
3. **Live integration** — the backend was run against a SQLite database (migrations + development
   seed) and the finished frontend driven against it in a real browser.

To regenerate the OpenAPI artefact:

```bash
ENVIRONMENT=test DATABASE_URL="sqlite+pysqlite:///:memory:" JWT_SECRET="<32+ chars>" python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=1))"
```

---

## 3. Architecture

```
frontend/src/
├── api/            client.ts · endpoints.ts · queries.ts
├── app/            providers/ · router/ · layouts/
├── components/     ui/ · intelligence/ · maps/
├── features/       auth overview risk-map drought flood food-security
│                   warnings history data-health reports administration profile
├── hooks/          useDomainIntelligence · useUrlFilters
├── lib/            risk.ts · time.ts · format.ts
├── types/          api.ts · react-query.d.ts
└── tests/          9 suites, 137 tests
```

**Single HTTP boundary.** Nothing outside `src/api` calls `fetch`; a test asserts this
structurally. The client centralises base URL, bearer token, silent 401 refresh (single-flight,
concurrent 401s share one refresh), a 20-second client deadline, and normalisation of every
failure into an `ApiError` with a typed `kind` the UI branches on.

**One retry policy.** `shouldRetry` is installed once on the QueryClient rather than repeated per
hook, so a differently-configured client actually takes effect. Access boundaries (401/403) and
validation failures are never retried.

---

## 4. Design system

**Typography** — Inter, loaded from Google Fonts with a system fallback stack. `tabular-nums` is
set globally so probabilities and counts align in tables. Weights: 700 display / 600 titles /
500 labels / 400–500 body. No marketing-scale type inside the application.

**Surface** — light, near-white surfaces on an `#f7f8fa` canvas, restrained 1px borders, shadows
only on transient surfaces (dialogs, drawers, hover lift). No gradients, glass, or blur.

**Semantic risk colour** — five levels defined once in `lib/risk.ts` and used identically on map,
table, badge, card and chart:

| Level | Colour | Glyph | Meaning |
|---|---|---|---|
| NORMAL | green `#17b26a` | ● | No elevated risk signal |
| WATCH | amber `#f5b546` | ◆ | Trending unfavourably |
| WARNING | orange `#ef6820` | ▲ | Threshold exceeded |
| CRITICAL | red `#f04438` | ▲ | Highest modelled severity |
| UNKNOWN | grey `#98a2b3` | — | No prediction issued |

Severity colour is never decorative. A test asserts no component outside `lib/risk.ts`,
`SomaliaMap.tsx` and `styles.css` contains a raw severity hex value. Workflow state, classification
and system health use separate non-severity palettes so an approved CRITICAL warning and a draft
CRITICAL warning are distinguishable at a glance.

**Primitives** — Button, IconButton, Badge, Card, CardHeader, Panel, Divider, Field, Input, Select,
Skeleton, SkeletonText, DataPoint, DataGrid, PageHeader, SectionHeader, MetaBar, MetaItem,
MetricCard, Tabs, TabPanel, Table/Th/Td/TableScroll, Dialog, Drawer, ConfirmDialog, Tooltip,
EmptyState, ErrorState, AccessDenied, Note, QueryBoundary, RiskBadge, StatusBadge, GovernanceBadge,
DataQualityBadge, FreshnessBadge, ClassificationBadge, ConfidenceIndicator, StaleBadge, MetaChip.

---

## 5. Routes

| Route | Page | Capability gate |
|---|---|---|
| `/login` | Sign-in | — |
| `/app/overview` | National Early Warning Overview | `predictions.read` ∪ `alerts.read` ∪ `geography.read` |
| `/app/map` | Somalia National Risk Map | `geography.read` |
| `/app/drought` | Drought Intelligence | `predictions.read` |
| `/app/flood` | River Flood Intelligence | `predictions.read` |
| `/app/food-security` | Food Security Intelligence | `predictions.read` |
| `/app/warnings` | Warning Center | `alerts.read` |
| `/app/warnings/:alertId` | Warning Review Workspace | `alerts.read` |
| `/app/history` | Historical Intelligence | `predictions.read` ∪ `alerts.read` |
| `/app/data-health` | Data Health | `data_sources.read` |
| `/app/models` | Model Operations | `models.read` |
| `/app/reports` | Reports | `reports.read` |
| `/app/admin` | Administration | `users.manage` ∪ `organizations.manage` |
| `/app/profile` | Profile & Access | — |

Every operational page is lazily loaded. Route guards are presentation only — the backend
authorises every request independently.

---

## 6. Scientific honesty — what the UI refuses to imply

This was treated as a correctness requirement, not a copy requirement, and is enforced by tests.

**River flood is gauge-scoped.** The page is headed RIVER FLOOD MONITORING. Counts are counts of
gauges. The map draws discrete station markers, never a filled polygon over the surrounding
district. The legend states "No area flood extent is modelled or implied." The scope statement
reads: *"…supported Jubba and Shabelle gauging stations only… this is not Somalia-wide flood
coverage and does not cover flash or surface flooding."* Station exposure is labelled
**population context**, explicitly not a count of people who would be flooded, because no validated
inundation geometry exists.

**Food security is region-scoped and is not IPC.** The page leads with a caution note:
*"This is a model early-warning signal, not an IPC classification… only the IPC Technical Working
Group can determine [an official phase]."* No district-level food-security output is produced or
inferred.

**Drought is an early-warning signal, not a famine forecast.** Stated on the page.

**No averaged national probability.** The historical trend chart plots *counts of units at Watch+
per day*, never a mean probability, matching the operational contract's prohibition on averaging
heterogeneous per-unit probabilities.

**Absence is not low risk.** Map polygons with no signal use a distinct neutral fill, not NORMAL
green. A withheld probability renders "Withheld", not `0%`. Missing values render `—`, never `0`.
A domain with no evaluated intelligence reports "No evidence", never "NORMAL".

**Chart gaps are real.** `connectNulls={false}` — a missing day means no run, not zero risk.

---

## 7. Human governance is visible

The review workspace renders the governance chain as a progress rail:

```
AI generated › Analyst review › Verification › Authorised approval › Published
```

Model output carries an explicit "AI-generated · not yet authorised" badge until an authorised
human approves it. Section 1 of every warning under review states: *"This is model-generated
intelligence under review. It has **not** been approved as an official warning."*

**Only transitions the backend defines are offered.** The workflow implemented in
`backend/app/modules/alerts/service.py` is:

```
draft → in_review → {verification_required, approved}
verification_required → verified → approved → published → resolved
```

There is **no reject and no hold transition in the platform**. The master specification asked for
APPROVE / HOLD / REJECT; implementing those would have required either fabricating backend
capability or shipping buttons that always fail. Instead the UI offers the real transitions and
includes a disclosure explaining the absence and pointing to *Request Field Verification* as the
mechanism for pausing a decision pending evidence. **This is the one specified item deliberately
not implemented as written, and it is a backend gap, not a frontend omission.**

Approve, Publish and Resolve require explicit confirmation naming the consequence. The confirm
control is deliberately **not** focused on open — a reflexive Enter keypress cannot publish a
warning. (An implementation bug was found and fixed here during testing: a comma-separated
`querySelector` was returning the header close button in document order instead of the nominated
safe control.)

---

## 8. Data health

Each source is judged against **its own declared cadence**, taken from the backend's own
`assess_health` verdict rather than recomputed with a daily assumption. IPC is not late because it
did not publish today; a MODIS composite is not stale at 24 hours. The page states this explicitly
and displays each source's declared cadence next to its freshness verdict so the verdict is
explicable. Health is fetched per source, so one failing endpoint degrades a single row — and that
row shows "Status unavailable", never FRESH.

---

## 9. Time

Operational timezone is **Africa/Mogadishu** (UTC+03:00, no DST). Every rendered timestamp carries
an explicit `EAT` label. Naive backend timestamps are treated as UTC. "Next scheduled run" is
labelled as *scheduled* and paired with actual last-run status, so a stalled pipeline is never
masked by a healthy-looking schedule.

Verified live: the API returned `2026-08-26T23:48:00Z` and the UI displayed `27 Aug 2026, 02:47
EAT` — correct +3 offset including date rollover.

---

## 10. Accessibility

- Severity is never colour alone: glyph + uppercase label + colour on every indicator.
- Skip link to `#main-content`; named `Primary` navigation landmark; one `<h1>` per page.
- ARIA tab pattern with roving tabindex and arrow/Home/End key navigation.
- Dialogs and drawers trap focus, close on Escape, lock body scroll, and restore focus on close.
- All filter controls labelled; empty states announced via `role="status"`; errors via `role="alert"`.
- Single consistent `:focus-visible` treatment; `prefers-reduced-motion` respected.
- Confidence meter exposes its value as text and an accessible name, not only filled bars.

**Fixed during verification:** three interactive targets measured below the WCAG 2.5.8 24px minimum
("Technical attribution", the reject/hold disclosure, the map legend "Hide", and "Back to Warning
Center") were given `min-h-6` tap targets.

---

## 11. Responsive

Desktop ≥1024px: persistent 236px sidebar. Below that: header menu button opens a focus-trapped
navigation drawer. Tables become severity-led card lists below `md` rather than horizontally
scrolling. Map detail opens in a right-hand drawer on desktop and a bottom sheet on mobile.

Measured in a real browser — `scrollWidth` vs `clientWidth`, plus a sweep for any element
extending past the viewport:

| Width | Horizontal overflow | Offending elements |
|---|---|---|
| 375px | none | 0 |
| 430px | none | 0 |
| 768px | none | 0 |
| 1024px | none | 0 |
| 1280px | none | 0 |
| 1440px | none | 0 |

---

## 12. Performance

Route-level code splitting; MapLibre (1.05 MB) and Recharts load only on the routes that use them,
via dynamic import and named manual chunks. Initial shell bundle is 336 kB (105 kB gzipped).
Query caching with per-domain `staleTime`; `refetchOnWindowFocus` disabled because operational data
changes on a scheduled cadence, not continuously.

---

## 13. Testing

**9 suites · 137 tests · 137 passing.**

| Suite | Tests | Covers |
|---|---|---|
| `risk-semantics` | 21 | Severity normalisation (incl. `SEVERE`→`critical`), domain scope statements, transition table mirroring the backend, capability gating |
| `time-and-format` | 21 | Mogadishu conversion, date rollover, naive-timestamp handling, zero vs absent, cadence |
| `api-client` | 19 | Every status→kind mapping, 422 flattening, retry policy, token attachment, 401 refresh + replay, session expiry |
| `auth-and-access` | 12 | Login success/failure/network, protected routes, access boundary, role-aware navigation, landing route |
| `overview-and-resilience` | 13 | Dashboard render, GOOD/PARTIAL/STALE/INSUFFICIENT derivation, partial API failure isolation, data-health cadence |
| `warning-workflow` | 21 | Queue filtering, URL state, transition offering by capability, confirmation before approve/publish, conflict handling, suppression display |
| `scientific-honesty` | 12 | Gauge framing, region framing, IPC separation, no fabricated values |
| `accessibility-and-responsive` | 14 | Colour-independence, semantics, keyboard, focus, drawer, skip link |
| `no-production-fixture-fallback` | 5 | Structural: no fixture import, no sample-data fallback, no stray `fetch`, no raw severity hex |

Tests stub `fetch`, not the API module, so the real client runs in every component test.

**Defects found and fixed by the tests:** cadence rounding rendering "3.0 mo"; hooks overriding the
QueryClient retry policy; `data-autofocus` losing to document order in overlays; a corrupted regex
literal; three sub-minimum tap targets.

---

## 14. Quality gates

| Gate | Command | Result |
|---|---|---|
| Typecheck | `npm run check` | **PASS** — 0 errors |
| Lint | `npm run lint` | **PASS** — 0 errors, 5 warnings |
| Tests | `npm run test` | **PASS** — 137/137 |
| Production build | `npm run build` | **PASS** — built in ~11s |

`npm run verify` runs all four in sequence.

The 5 warnings are `react-refresh/only-export-components` on five files that intentionally
co-export a component with a related helper. They affect hot-reload granularity in development
only, never the production build.

---

## 15. Live integration verification

The backend was run for real (SQLite + `alembic upgrade head` + development seed) and the frontend
driven against it in a browser.

| Check | Result |
|---|---|
| Sign-in as National Analyst | PASS — landed on Overview |
| Real intelligence rendered | PASS — drought WARNING 70%, correct district and parent region |
| Honest degraded status | PASS — "PARTIAL · 3 of 4 domains are stale. 3 domains hold no evaluated intelligence." |
| Empty domains | PASS — "No evidence" + STALE, **not** NORMAL |
| Timezone | PASS — `23:48Z` → `02:47 EAT` next day |
| Warning review workspace | PASS — all six sections, governance rail, real recommended action from `/early-actions/items` |
| Missing model metadata | PASS — rendered `—` and "NOT REPORTED", not invented |
| Transition offering | PASS — only `Resolve` offered from `published` |
| Role-aware nav (Partner Viewer) | PASS — 5 destinations only; drought/flood/food-security/data-health/admin hidden |
| Read-only decision panel | PASS — read-only notice, zero decision buttons |
| Console errors | PASS — none |

---

## 16. Known limitations

1. **No reject/hold transition** — the backend workflow defines none. See §7. Closing this needs a
   backend change, which was out of scope for Phase 05.
2. **`/alerts` has no server-side filtering** — the endpoint returns every readable alert. Filtering
   and pagination are client-side. This is correct at current volumes but will need a server-side
   filter as the corpus grows.
3. **Flood station coordinates** — `/risks` does not return station longitude/latitude. Stations are
   mapped only where provenance supplies coordinates; the page states how many could not be placed
   and lists all of them in the table regardless. Nothing is positioned by guesswork.
4. **Administration is read-only** — the backend exposes create endpoints, but account creation
   involves credential issuance, geographic scope and classification ceiling. Rather than ship a
   half-safe form, the page presents the access model accurately and states where changes are made.
5. **Basemap** — no raster basemap is bundled. Governed boundaries render on a plain ground unless
   `VITE_MAP_STYLE_URL` is configured, rather than pulling an unlicensed tile source.
6. **i18n scope** — navigation, session flow and common status vocabulary are English/Somali.
   Domain-technical and methodological text stays English, the working language of the scientific
   contract; a mistranslated scope caveat is a safety problem, not a cosmetic one.
7. **Recharts in the history bundle** — 385 kB, lazily loaded on that route only.

---

## 17. Phase 04 dependency — the material finding

**No Phase 04 adapter exists in the backend.** `grep -rn "operational" backend/app` returns
nothing, and there are no Phase 04 documents in the repository.

The Phase 03 contract states plainly that `backend/app/modules/{exposure,risks,early_actions,
ml_registry}` define a separate UUID-keyed domain model *"not yet wired to real Phase 01/02 data"*,
and that Phase 04's job is to write the adapter mapping
`data/operational/intelligence/<track>/<date>.json` onto that schema. That adapter has not been
built.

Consequently:

- Real Phase 03 intelligence exists on disk (87 drought districts, 5 flood stations, 18
  food-security regions) but **is not reachable through any API endpoint**.
- The API currently serves only records written into its own database — in development, the
  explicitly `SYNTHETIC / DEVELOPMENT DATA`-labelled seed.

**Phase 05 does not conceal this, and could not fix it from the frontend.** The dashboard reports
PARTIAL/STALE truthfully, empty domains say "No evidence", and no green "Operational" indicator is
forced. The frontend is built against the API contract, so when the Phase 04 adapter lands and
begins populating `/risks`, `/alerts` and `/exposure/assessments` from the operational records,
these pages will populate with no frontend change required.

Two frontend details are ready for that moment: `toSeverity` already accepts the contract's `SEVERE`
spelling alongside the API's `critical`, and driver rendering already understands the contract's
`reason_code` vocabulary.

---

## 18. Files

### Created (39)

```
frontend/eslint.config.js
frontend/src/types/api.ts
frontend/src/types/react-query.d.ts
frontend/src/lib/risk.ts
frontend/src/lib/time.ts
frontend/src/lib/format.ts
frontend/src/api/client.ts
frontend/src/api/endpoints.ts
frontend/src/api/queries.ts
frontend/src/app/providers/AppProviders.tsx
frontend/src/app/providers/AuthProvider.tsx
frontend/src/app/router/AppRouter.tsx
frontend/src/app/layouts/AppLayout.tsx
frontend/src/app/layouts/navigation.ts
frontend/src/components/ui/primitives.tsx
frontend/src/components/ui/layout.tsx
frontend/src/components/ui/states.tsx
frontend/src/components/intelligence/badges.tsx
frontend/src/components/intelligence/IntelligenceDetail.tsx
frontend/src/components/intelligence/RiskTable.tsx
frontend/src/components/maps/SomaliaMap.tsx
frontend/src/hooks/useDomainIntelligence.ts
frontend/src/hooks/useUrlFilters.ts
frontend/src/features/overview/OverviewPage.tsx
frontend/src/features/risk-map/RiskMapPage.tsx
frontend/src/features/drought/DroughtPage.tsx
frontend/src/features/flood/FloodPage.tsx
frontend/src/features/food-security/FoodSecurityPage.tsx
frontend/src/features/warnings/WarningCenterPage.tsx
frontend/src/features/warnings/WarningReviewPage.tsx
frontend/src/features/history/HistoryPage.tsx
frontend/src/features/data-health/ModelOperationsPage.tsx
frontend/src/features/profile/ProfilePage.tsx
frontend/src/tests/{fixtures.ts, harness.tsx, and 7 test suites}
docs/phase-05-frontend-report.md
data/metadata/phase05_completion_report.json
```

### Modified (10)

```
frontend/index.html                                   full document, Inter, meta
frontend/package.json                                 scripts, lucide-react, eslint toolchain
frontend/tsconfig.app.json                            node types
frontend/vite.config.ts                               PORT env, manual chunks
frontend/src/main.tsx                                 provider composition
frontend/src/styles.css                               design tokens (Tailwind v4 @theme)
frontend/src/i18n/index.tsx                           rewritten dictionary + LanguageToggle
frontend/src/features/auth/LoginPage.tsx              rewritten
frontend/src/features/data-health/DataHealthPage.tsx  rewritten
frontend/src/features/reports/ReportsPage.tsx         rewritten
frontend/src/features/administration/AdministrationPage.tsx  rewritten
```

### Removed (18)

Superseded scaffold: `src/app/App.tsx`, `App.test.tsx`, `components/StatusPage.tsx`,
`services/api.ts`, `features.css`, and the `alerts`, `dashboard`, `map-explorer`,
`district-profile`, `early-actions`, `exposure`, `field-verification`, `ml-operations`,
`notifications`, `partner`, `public`, `scenarios` feature directories.

Removed with `git rm`, so every deletion is staged and reversible.

### Incidental

`.mcp.json`, root `package.json`/`package-lock.json` — created by an earlier
`npx shadcn@latest mcp init` in this session, unrelated to Phase 05. shadcn/ui is **not** used by
this frontend. Safe to delete.

---

## 19. Not touched

Phase 01 source data and historical datasets · Phase 02 model artefacts, thresholds and training ·
Phase 03 intelligence semantics and warning policy · all backend Python. Zero backend changes were
required.

---

## 20. Running it

```bash
cd frontend && npm install && npm run dev
```

Configure `VITE_API_URL` (default `http://localhost:8000/api/v1`) and optionally
`VITE_MAP_STYLE_URL` for a basemap.
