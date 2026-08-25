# Observability and rate-limit runbook

The API emits one structured `http_request` event per request with request ID, method, matched
route template, status, and duration. User-supplied request IDs are accepted only when they are
valid UUIDs, preventing untrusted log fields and response-header reflection.

`GET /api/v1/readiness` executes `SELECT 1`; it returns `503` when the configured database cannot
serve queries. Liveness at `/api/v1/health` deliberately avoids downstream dependencies.

Prometheus-format process metrics are exposed at `/api/v1/metrics` only when `METRICS_TOKEN` is
configured. Scrapers must send `Authorization: Bearer <token>`. The endpoint is unavailable rather
than open when no token is configured. Rotate this token independently of user JWT secrets.

Authentication and unauthenticated public endpoints have bounded fixed-window limits and return
`429`, `Retry-After`, and `X-RateLimit-*` headers. Development and tests use a process-local
deterministic limiter. Production configuration is rejected unless `RATE_LIMIT_BACKEND=redis`;
the production limiter uses an atomic Redis Lua increment/expiry operation shared by every API
worker. Protected routes fail closed with `429` if Redis is unavailable. The ingress/API gateway
may enforce an additional tighter policy, but must not be configured with a weaker quota.

Recommended alerts:

- readiness unavailable for two consecutive probes;
- elevated 5xx rate for five minutes;
- p95 latency above the service objective;
- sustained authentication throttling;
- ingestion source freshness breach or dead-letter growth.
