# Governed reports API

Reports are authenticated partner/internal products derived from an alert that has already passed
the human warning workflow and reached `published`. They are not model output and they cannot
publish themselves.

## Lifecycle

1. `POST /api/v1/reports` creates a draft and requires `reports.generate` within the caller's
   geographic and classification scope.
2. `POST /api/v1/reports/{id}/publish` requires the separate `reports.publish` capability and
   records the publisher and publication timestamp.
3. `GET /api/v1/reports` returns only published reports visible through a single effective
   membership grant. Drafts are never listed.
4. `GET /api/v1/reports/{id}/export?format=csv` exports an explicit metadata allowlist. Narrative
   sections and source lineage are deliberately excluded from CSV.
5. `GET /api/v1/reports/{id}/export?format=html` downloads an inert, print-ready situation report
   containing the authorized narrative, findings, recommendations, classification, period, scope,
   and boundary version. User-authored content is escaped, scripts and external resources are
   blocked by a sandboxed Content Security Policy, and source lineage is not embedded.

Creation records the source alert, stable administrative-unit ID, boundary version, reporting
period, structured sections, findings, recommendations, and source lineage. A report may preserve
or increase the source alert's restriction, but it cannot reclassify partner/internal information
as public. Creation and publication are audit events.

Public warnings remain a separate unauthenticated allowlist at `/api/v1/public/warnings`. Partner
reports never appear there.
