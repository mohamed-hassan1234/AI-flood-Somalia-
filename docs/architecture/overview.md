# Architecture

React calls `/api/v1` on a feature-based FastAPI modular monolith. Application
services and repositories use MySQL 8. Redis/Celery isolate ingestion,
geospatial, reporting, inference, and notification work. Large assets use an
S3-compatible port (MinIO locally). Risk and publication states are independent.

