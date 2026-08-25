# Security baseline

Authorization combines user, organization membership, capability, geography,
and classification. Frontend visibility is never authorization. Use Argon2,
revocable refresh tokens, append-only audit events, safe upload quarantine, and
explicit Public projections. Logs exclude secrets and evidence payloads.

Authentication and public routes are rate limited. Metrics require a dedicated bearer token and
are disabled when it is absent. Production deployments with multiple API workers must add an
atomic Redis or ingress-level distributed quota; the application limiter is process-local.
