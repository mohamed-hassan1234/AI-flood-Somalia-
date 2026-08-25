# ADR 0001: Platform architecture

- Status: Accepted
- Decision: FastAPI modular monolith, MySQL, Redis/Celery, S3-compatible storage,
  and MapLibre.
- Alternatives: Microservices, RQ, PostgreSQL/PostGIS, Leaflet.
- Consequences: simpler governance and transactions; workers scale by queue;
  ports preserve future provider evaluation.

