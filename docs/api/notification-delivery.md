# Notification delivery providers

Notification creation is separate from dispatch. `POST /api/v1/notifications/deliveries` validates
the published-warning/action context, capability, classification, geography, channel, and
deduplication key, then records a queued delivery. Celery Beat selects bounded due batches every 30
seconds and the notifications worker dispatches them.

The provider port supports `in_app`, `email`, `sms`, `push`, and `webhook`. In-app delivery is local.
Development uses an inert sink for external channels: it records a deterministic non-PII provider
fingerprint but transmits and logs no recipient or message content. Production refuses to start
unless `NOTIFICATION_PROVIDER=gateway`, the gateway uses HTTPS, and a secret token is supplied.
The fixed-origin gateway resolves opaque recipient keys; arbitrary recipient-controlled URLs are
never fetched by the platform.

Dispatch persists attempt count, safe error code, last-attempt time, provider message ID, next
attempt, and explicit dead-letter time. Retryable failures use bounded exponential minute delays;
non-retryable failures and exhausted attempts are dead-lettered. Provider exceptions are converted
to a safe retryable code so one integration cannot crash the worker loop. API list projections
exclude recipient keys and message bodies.
