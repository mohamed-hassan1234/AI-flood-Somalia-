# Somalia AI Platform — System Documentation Report

**Report date:** 25 August 2026  
**System:** Somalia AI National Early Warning & Early Action Platform  
**Repository version described:** current workspace implementation

## 1. Purpose and scope

This platform supports human-governed monitoring and early action for four risk domains:

- drought;
- river flood;
- flash flood; and
- food-security deterioration.

It combines governed observations, transparent risk calculations, optional governed machine-learning
predictions, field verification, exposure assessments, alerts, early-action plans, notifications,
reports, and outcome feedback.

The system is decision support. It does **not** produce an official IPC/FSNAU classification, and it
does **not** automatically publish a warning. A person with the correct permission must review,
approve, and publish every warning.

## 2. What is implemented now

The repository contains:

- a React 19 and TypeScript web application;
- a FastAPI modular backend under `/api/v1`;
- MySQL 8.4 for the containerized operational database;
- SQLite as the default native-development database when no `DATABASE_URL` is supplied;
- Redis for Celery messaging and production rate limiting;
- Celery worker and scheduler services;
- MinIO/S3-compatible object storage;
- Alembic database migrations;
- role-, geography-, and classification-based authorization;
- English and Somali interface localization;
- unit, integration, browser E2E, migration, restore, security, and performance tests.

## 3. High-level architecture

```text
User's browser
    |
    | HTTPS/HTTP + JSON, bearer access token
    v
React web application (Nginx in Docker)
    |
    | /api/v1 requests
    v
FastAPI modular application
    |--------------------|---------------------|
    v                    v                     v
MySQL / SQLite       Redis + Celery        S3 / MinIO
operational data     jobs + rate limits    governed objects
    |                    |
    |                    v
    |               notification provider
    |               development sink or HTTPS gateway
    v
Scoped dashboards, warning workflow, reports, and public projections
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| React frontend | Login, dashboards, maps, district evidence, alert center, field verification, exposure, early actions, notifications, ML operations, scenarios, reports, partner portal, administration, and public warnings. |
| FastAPI backend | Validation, authorization, use-case logic, persistence, public projections, health, readiness, metrics, and API documentation. |
| MySQL | Production/container persistence for users, governance metadata, observations, risk signals, alerts, actions, reports, ML records, and audit events. |
| SQLite | Local fallback database configured by the backend's development defaults. |
| Redis | Celery broker/result backend and required distributed production rate limiter. |
| Celery worker/beat | The implemented scheduled workload is notification selection and dispatch every 30 seconds. Queue names also exist for ingestion and ML, but this repository contains no ingestion or ML Celery task implementation yet. |
| MinIO/S3 | Stores governed connector files and is accessed using server-side credentials. |
| Nginx | Serves the built single-page frontend and sends unknown routes to `index.html`. |

## 4. Where the system gets its data

### The short answer

The repository contains a separate, reproducible Phase 01 source-data foundation. Its production
historical layer includes CHIRPS v3 rainfall and MOD13Q1 V061 vegetation for 2015–2025; NASA POWER
temperature and relative antecedent-wetness series for 2000–2025; FAO SWALIM/SNRFA river histories;
IPC outcomes; WFP markets; OCHA administrative boundaries; and WorldPop exposure. The scripts use
yearly recovery checkpoints, bounded concurrency, source manifests, checksums, QA masks, canonical
geography, and machine-readable acceptance tests. SMAP remains a separately named satellite
validation source rather than being silently substituted into the long historical series.

These source files and district derivatives are validated under `data/`; they are **not**
automatically inserted into the operational database. The production application continues to
accept governed CSV/object-store imports only. Full provenance, actual coverage, limitations,
reproduction commands, and the Phase 02 data-readiness decision are in
[`phase-01-data-foundation-report.md`](phase-01-data-foundation-report.md).

Today, data enters through these implemented paths:

| Data type | Implemented entry path | Where it is stored |
|---|---|---|
| Synthetic demonstration data | Opt-in development seed | Database |
| Observation data | Small UTF-8 CSV upload, up to 256 KiB | Valid rows in `observations`; rejected rows in quarantine tables |
| Larger observation batches | CSV placed in MinIO/S3, up to 10 MiB, then imported using its key and SHA-256 checksum | Source object in MinIO/S3; normalized records in the database |
| Administrative boundaries | Authorized GeoJSON `FeatureCollection` import | Versioned boundary records and current admin-unit projection in the database |
| Indicator definitions | Authorized API creation | Database registry |
| Season definitions | Authorized draft creation followed by separate approval | Database registry |
| Field verification | Authorized users submit and review task answers/evidence references | Database; evidence is represented by object metadata |
| Exposure assessments | Authorized API creation using source-lineage metadata | Database |
| ML snapshots, features, models, predictions, and outcomes | Governed API records created by authorized ML users | Database; model artifacts are referenced by URI |
| Scenarios | Authorized simulation request based on a snapshot and district | Database, always labeled `SIMULATION` |

An `access_method` value of `api` can be registered for an operational source, but the Phase 01
connectors do not bypass source registration, governance, validation, or ingestion controls. The
operational connector paths remain file upload and object storage.

### Required observation CSV format

The header must contain all six columns:

```csv
source_record_id,admin_unit_code,indicator_code,value,unit,reference_time
provider-row-001,SO-BN-BUR,drought.rainfall_deficit,0.72,index_0_1,2026-08-20T00:00:00Z
provider-row-002,SO-BN-BUR,drought.vegetation_stress,,index_0_1,2026-08-20T00:00:00Z
```

An empty `value` means missing data; it is not converted to zero. `source_record_id` must be unique
inside the file and is also idempotent per registered source in the database.

### Observation validation and quarantine

For every import, the backend:

1. checks the file type, size, encoding, and required columns;
2. parses `reference_time` as an ISO date/time;
3. rejects a duplicate or missing source record ID inside the batch;
4. checks that the administrative `stable_code` exists;
5. checks the indicator registry for verified sources;
6. enforces the registered unit and minimum/maximum value range;
7. ignores a record already stored for the same source and source record ID;
8. stores accepted rows as observations;
9. records rejected rows as quarantine records using reason codes and a safe payload; and
10. stores run totals for received, accepted, and quarantined rows.

Observations from a verified source enter the `NORMALIZED` stage. Observations from an unverified
source enter the `RAW` stage with quality flags. Risk evaluation uses only verified sources and
`NORMALIZED` observations.

### Object-storage import controls

For a source with ID `{source_id}`, the CSV object must be under:

```text
sources/{source_id}/batch-name.csv
```

The caller submits that key and a lowercase 64-character SHA-256 digest to
`POST /api/v1/data-sources/{source_id}/imports/object-storage`. The backend rejects an object outside
the source prefix, a checksum mismatch, invalid UTF-8, or an object larger than 10 MiB. The request
cannot supply storage credentials or change the storage endpoint.

The current endpoint reads and imports the object synchronously. The architecture allows a future
scheduled ingestion worker, but that worker is not implemented in the present code.

## 5. End-to-end system workflow

### Phase A — Platform preparation

1. An administrator creates organizations, users, roles/memberships, classification ceilings, and
   national or administrative-unit geographic scopes.
2. An authorized geography manager imports a complete versioned GeoJSON hierarchy. Each feature
   needs `stable_code`, `name`, `level`, optional `parent_code`, optional `aliases`, and valid Polygon
   or MultiPolygon geometry. Region and district features require an explicit parent in the same
   import.
3. An authorized administrator registers indicator definitions, including code, unit, value kind,
   allowed range, aggregation method, version, definition source, and verification state.
4. An authorized administrator registers every data source with its owner, license, attribution,
   terms URL, access method, expected frequency, resolution, schedule, classification, and verified
   state. A verified source cannot be registered without the required governance metadata.
5. Season windows may be created as drafts and approved separately. Only approved, active,
   non-overlapping windows annotate evidence.

### Phase B — Ingestion and data health

1. An authorized operator uploads a bounded CSV or places a batch in the source-specific MinIO/S3
   prefix and submits its checksum.
2. The ingestion service validates every row, quarantines invalid records, prevents duplicates, and
   writes accepted observations.
3. The Data Health view reads the latest ingestion run for each source.
4. A source is `fresh` within one expected interval, `delayed` within two intervals, `stale` after
   two intervals, `failed` after a failed latest run, or `unknown` before any successful run.
5. District evidence is shown directly. Region/country evidence is calculated over descendant leaf
   units as an unweighted mean, preserving missing values and reporting coverage and lineage.

### Phase C — Risk evaluation

1. An authorized analyst requests `POST /api/v1/risks/{domain}/evaluations` with an administrative
   unit, target period, optional evaluation time, and a 1–365 day lookback.
2. The backend selects the newest observation per required feature inside the time window.
3. Only normalized evidence from verified sources is eligible.
4. The transparent baseline calculates a weighted score from 0 to 1. At least 50% of the configured
   weight must be present; missing evidence is never treated as zero.
5. Levels are: Normal below 0.4, Watch from 0.4, Warning from 0.6, and Critical from 0.8.
6. The saved signal includes its score, completeness-based confidence, observation/source drivers,
   window, weights, thresholds, quality flags, missing indicators, and boundary versions.

Configured evidence weights are:

| Domain | Indicators and weights |
|---|---|
| Drought | rainfall deficit 0.40; vegetation stress 0.35; dry spell 0.25 |
| River flood | level threshold ratio 0.50; rate of rise 0.30; rainfall forecast 0.20 |
| Flash flood | rainfall intensity 0.50; susceptibility 0.30; rainfall forecast 0.20 |
| Food security | price stress 0.30; nutrition stress 0.25; displacement stress 0.20; agriculture stress 0.25 |

These are application baseline values, not a claim that Somalia's competent institutions have
approved them for operational use.

### Phase D — Human warning workflow

1. A user with `alerts.create` creates a **draft** alert from a saved risk signal.
2. The only valid state path is:

```text
draft -> in_review -> approved -> published -> resolved
                   \
                    -> verification_required -> verified -> approved
```

3. Each transition requires its own capability. Approval records the approving user; publication
   records the publication time; actions are written to the audit log.
4. Only a `published` alert classified `PUBLIC` appears in the unauthenticated public-warning API.
5. The partner warning API also requires authentication and filters published alerts by one
   effective membership's geography and classification ceiling.

There is no code path from a risk calculation or ML prediction directly to publication.

### Phase E — Verification, exposure, and early action

1. An authorized analyst creates a verification task for an alert and assigns a scope, deadline,
   priority, and form schema.
2. A field reporter submits answers and evidence references.
3. A reviewer verifies, rejects, or requests more evidence. Valid task states are `open`,
   `submitted`, `more_evidence`, `verified`, and `rejected`.
4. An exposure assessment can record population, settlements, cropland, infrastructure,
   confidence, and source lineage for the alert and geography.
5. Approved domain playbooks are used to create action plans. Plans require separate approval.
6. Action items move through planned, assigned, in-progress, blocked, completed, or cancelled
   states. Completion requires at least one evidence object.

### Phase F — Notifications and reports

1. Notification creation validates the published-alert or action-item context, scope,
   classification, channel, and deduplication key.
2. Celery Beat selects due notifications every 30 seconds; the notification worker dispatches
   them using `in_app`, `email`, `sms`, `push`, or `webhook`.
3. Development mode uses an inert external-channel sink and sends no recipient or message content.
   Production requires a fixed-origin HTTPS gateway and secret token.
4. Delivery attempts, safe error codes, retry time, acknowledgement, escalation, provider ID, and
   dead-letter status are recorded. Recipient keys and message bodies are excluded from list APIs.
5. Reports can be drafted only from a published alert, then published by a separately authorized
   user. Published, authorized reports can be listed and exported as allowlisted CSV or inert,
   escaped HTML.

### Phase G — Outcome and model feedback

1. Authorized users link an observed binary outcome to a prediction with observation time, source
   lineage, and optional analyst override metadata.
2. Model metrics include precision, recall, F1, macro-F1, PR-AUC, ROC-AUC, Brier score,
   calibration error, high-risk recall, and useful lead time.
3. A model progresses from `candidate` to `validated` to `production`, or to `retired`.
4. Production promotion requires the complete metric set plus chronological, geographic, seasonal,
   horizon, calibration, lead-time, and limitation evidence.
5. Scenario results are bounded to 0–1, labeled `SIMULATION`, and cannot publish warnings.

## 6. User access and security model

Authentication uses email/password login, Argon2 password hashing, short-lived signed access
tokens, rotating/revocable refresh tokens, and bearer authorization. The browser stores access and
refresh tokens in `sessionStorage`; closing the browser session clears them.

Authorization is enforced by the backend, not by whether a frontend menu is visible. Every grant
combines:

- user and active organization membership;
- role capabilities;
- a classification ceiling: Public, Partner, or Internal; and
- national or explicit administrative-unit geography.

The eight seeded role types are Platform Super Admin, National Analyst, Regional Analyst, District
Officer/Field Reporter, Early Action/Response Coordinator, Decision Maker, Data/ML Scientist, and
Partner/Read-only Viewer. Detailed capabilities are declared in
`backend/app/modules/auth/roles.py`.

Additional controls include CORS allowlisting, security response headers, authentication/public
rate limits, scoped not-found behavior to reduce ID disclosure, upload limits, safe public
projections, append-only audit events, protected Prometheus metrics, and production configuration
validation.

## 7. Main API groups

All routes use the `/api/v1` prefix. Interactive OpenAPI documentation is available at
`http://localhost:8000/docs` after startup.

| Area | Important routes |
|---|---|
| Operations | `GET /health`, `GET /readiness`, `GET /metrics`, `GET /meta` |
| Authentication | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` |
| Administration | organizations, users, roles, and memberships under `/administration` |
| Geography | boundary import/list, admin-unit list/detail, point resolution, zonal statistics under `/geography` |
| Data governance | `/data-sources`, `/indicators`, `/seasons` |
| Evidence | `GET /observations`, `GET /observations/aggregate` |
| Risk | `GET /risks`, `POST /risks/{domain}/evaluations` |
| Alerts | create/list/detail/transition and partner warnings under `/alerts` |
| Verification | tasks, reports, and reviews under `/field-verification` |
| Exposure | assessments under `/exposure` |
| Early action | playbooks, plans, items, approvals, assignment, and transitions under `/early-actions` |
| Notifications | deliveries, acknowledgement, and escalation under `/notifications` |
| ML governance | snapshots, features, models, transitions, predictions, and operations under `/ml` |
| Outcomes/scenarios | `/outcomes`, `/scenarios` |
| Reports | create, publish, list, detail, and export under `/reports` |
| Dashboards | `/dashboard/scopes`, `/dashboard/national-summary` |
| Public | unauthenticated published warnings/reports under `/public` |

## 8. Database organization

The core data groups are:

- identity and access: `organizations`, `users`, `roles`, `memberships`, `geographic_scopes`,
  `refresh_tokens`;
- geography: `admin_units`, `boundary_revisions`;
- data governance and ingestion: `data_sources`, `indicator_definitions`, `season_definitions`,
  `ingestion_runs`, `quarantine_records`, `observations`;
- decision support: `risk_signals`, `alerts`, `verification_tasks`, `field_reports`,
  `exposure_assessments`;
- response: `playbooks`, `action_plans`, `action_items`, `notification_deliveries`;
- ML governance: `dataset_snapshots`, `feature_versions`, `model_versions`, `predictions`,
  `outcomes`, `scenarios`;
- reporting and accountability: `reports`, `audit_events`.

Schema changes are managed by Alembic. In Docker, the one-shot migration service must finish before
the API and workers start.

## 9. Step-by-step local startup

### Prerequisites

- Docker Desktop or Docker Engine with Compose v2;
- available host ports 5173 and 8000;
- enough memory for MySQL, Redis, MinIO, API, worker, scheduler, and frontend.

### Start the complete stack

1. From the repository root, copy `.env.example` to `.env`.
2. Replace **every** `replace-*` value. Use at least 32 random characters for `SECRET_KEY` and at
   least 12 characters for `SEED_PASSWORD`.
3. Keep the username/password in `DATABASE_URL` identical to `MYSQL_USER` and `MYSQL_PASSWORD`.
4. Start the services:

   ```shell
   docker compose up --build
   ```

5. Confirm the migration service exits successfully.
6. Check API liveness at `http://localhost:8000/api/v1/health`.
7. Check database readiness at `http://localhost:8000/api/v1/readiness`.
8. Open the web application at `http://localhost:5173`.
9. Open API documentation at `http://localhost:8000/docs`.
10. MinIO is available to the other Compose services at `http://minio:9000`. The current Compose
    file does not publish MinIO's API or console ports to the host. To use the console from the host,
    an operator must deliberately add an appropriate port mapping (normally 9001 for the console)
    or use an approved client inside the Compose network.

### Load optional development data

Run only in `development` or `test`:

```shell
docker compose --profile seed run --rm seed
```

This creates one account per role and a complete synthetic workflow. All generated records are
labeled `SYNTHETIC / DEVELOPMENT DATA`. All accounts use the `SEED_PASSWORD` supplied by the local
operator. The seed is idempotent and does not reset existing passwords.

### Stop the application

```shell
docker compose down
```

This preserves named database and object-storage volumes. Removing volumes deletes local data and
should be done only when a deliberate clean reset is required.

## 10. Correct production data-onboarding sequence

1. Obtain institutional approval for each provider, dataset, license, classification, retention
   rule, delivery method, and refresh schedule.
2. Review and institutionally approve the matched OCHA Somalia COD-AB v03 boundary reference and
   its CC BY IGO terms for the intended deployment.
3. Import the approved boundary hierarchy with a version, source, and effective date.
4. Register and verify indicator definitions, units, ranges, versions, and aggregation rules.
5. Register the data source with complete owner/license/terms/attribution/frequency/resolution
   metadata; keep it unverified until governance review is complete.
6. Build a provider adapter outside or inside the ingestion port, or deliver approved UTF-8 CSV to
   the source-isolated object-storage prefix.
7. Test a small controlled batch and examine accepted/quarantined totals.
8. Confirm source health, geographic mapping, units, missingness, boundary version, source lineage,
   and classification visibility.
9. Validate risk weights and thresholds with national domain experts using historical backtests.
10. Run the complete human workflow in a non-production pilot.
11. Configure managed MySQL, Redis, S3, HTTPS notification gateway, monitoring, encrypted backup,
    retention, secret rotation, and ingress controls.
12. Complete security review, representative load testing, and a witnessed restore exercise.
13. Obtain formal release approval before production use.

## 11. Monitoring, backup, and recovery

- `/api/v1/health` is a liveness check and does not test dependencies.
- `/api/v1/readiness` runs `SELECT 1` and returns HTTP 503 when the database is unavailable.
- `/api/v1/metrics` emits Prometheus text only with the dedicated metrics bearer token; it is
  unavailable when the token is not configured.
- Structured request logs include a safe request ID, method, route template, status, and duration,
  but exclude secrets and evidence payloads.
- Recommended alerts cover readiness failures, elevated 5xx rates, high p95 latency, sustained
  authentication throttling, stale ingestion sources, and dead-letter growth.
- Production backups require managed encryption, retention, schema and object manifests, restore
  into an isolated database, integrity checks, row/hash comparisons, and recorded evidence. A
  backup is not considered valid until restore succeeds.

## 12. Testing and verification commands

Backend, from `backend/`:

```shell
python -m pip install -e ".[test]"
ruff check .
mypy app scripts
pytest
```

Frontend, from `frontend/`:

```shell
npm install
npm run check
npm test -- --run
npm run build
```

Browser E2E, after installing Chromium with Playwright:

```shell
npx playwright install chromium
npm run test:e2e
```

Core and HTTP performance exercises, from `backend/`:

```shell
python -m scripts.benchmark_core
python -m scripts.benchmark_http --requests 90 --concurrency 6
```

## 13. Current limitations and production gaps

The following must not be misunderstood as completed production capability:

- public Phase 01 acquisition connectors exist, but they are not scheduled operational ingestion
  workers and have not received institutional production approval;
- the bundled Somalia boundary archive is matched to OCHA Somalia COD-AB v03, valid on 2025-01-08,
  under CC BY IGO; its original local download transaction is unrecorded, and no approved seasonal
  calendar is bundled;
- Phase 01 historical environmental archives and current FAO SWALIM moderate/high/bankfull levels
  for five gauges support model-development readiness, but they are not operational endorsements;
  SWALIM does not publish effective dates or revision history for those threshold values, and
  deployment still requires national governance approval;
- the object-storage import endpoint is synchronous despite the future worker-oriented architecture;
- the current Compose file does not expose MinIO's API or console ports to the host, even though
  older project instructions mention `localhost:9001`;
- Celery currently implements notification tasks only, not ingestion or ML training/inference jobs;
- external notification channels are inert in development and require a production HTTPS gateway;
- external identity provider and MFA integration are deployment-specific;
- production raster decoding, reprojection, and resampling are not included; the API accepts a
  bounded preprocessed JSON grid for zonal statistics;
- model artifacts are registered by URI, but this repository is a governance/API foundation rather
  than a complete automated model-training pipeline;
- the Docker frontend defaults API calls to `http://localhost:8000/api/v1` unless the Vite build is
  given an appropriate `VITE_API_URL` for the deployment;
- a real production backup/restore, security approval, load test, and institutional workflow
  acceptance cannot be proven by repository tests.

## 14. Important source files and supporting documents

- System entry point: `backend/app/main.py`
- API composition: `backend/app/api/router.py`
- Configuration: `backend/app/core/config.py` and `.env.example`
- Database entities: `backend/app/db/models/core.py`
- Ingestion: `backend/app/modules/ingestion/`
- Risk evaluation: `backend/app/modules/risks/`
- Alert state machine: `backend/app/modules/alerts/service.py`
- Authorization roles: `backend/app/modules/auth/roles.py`
- Worker configuration: `backend/app/workers/celery_app.py`
- Frontend routing: `frontend/src/app/App.tsx`
- Browser API client: `frontend/src/services/api.ts`
- Container topology: `docker-compose.yml`
- Existing detailed topics: `docs/api/`, `docs/data/`, `docs/ml/`, `docs/runbooks/`, and
  `docs/security/`

## 15. Final operating rule

The safe operational chain is:

```text
approved source and boundary
-> validated and traceable observations
-> explicit missingness and data-health review
-> transparent signal or governed prediction
-> human review and optional field verification
-> separate approval
-> deliberate publication
-> early action and controlled notification
-> outcome recording and evaluation
```

If source approval, lineage, geographic scope, classification, evidence completeness, or human
authorization is missing, the correct response is to stop the workflow and resolve the gap—not to
invent data, assume Normal conditions, or publish automatically.
