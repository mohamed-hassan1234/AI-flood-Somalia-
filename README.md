# Somalia AI National Early Warning & Early Action Platform

Human-governed decision support for drought, river flood, flash flood, and food-security
deterioration in Somalia. Model outputs are signals—not official IPC/FSNAU classifications—and
never auto-publish warnings.

## Local container start

Prerequisites: Docker with Compose v2 and enough local resources for MySQL, Redis, MinIO, the API,
worker, and frontend.

1. Copy `.env.example` to `.env`.
2. Replace every `replace-*` database, JWT, object-storage, metrics, and seed value. Keep the
   credentials in `DATABASE_URL` consistent with `MYSQL_USER` and `MYSQL_PASSWORD`.
3. Run `docker compose up --build`.

The one-shot `migration` service must finish successfully before the API and worker start. The API
is at `http://localhost:8000/docs`, the UI at `http://localhost:5173`, and MinIO's console at
`http://localhost:9001`. Health and readiness are `/api/v1/health` and `/api/v1/readiness`.

## Optional development seed

The seed command refuses to run unless `ENVIRONMENT` is `development` or `test`, requires an
operator-supplied `SEED_PASSWORD` of at least 12 characters, and is idempotent:

```shell
docker compose --profile seed run --rm seed
```

It creates one local account for each required role and a complete, explicitly labelled synthetic
workflow. It never prints or embeds the supplied password. See
[`docs/data/development-seed.md`](docs/data/development-seed.md).

## Native quality gates

```shell
cd backend
python -m pip install -e ".[test]"
ruff check .
mypy app scripts
pytest

cd ../frontend
npm install
npm run check
npm test -- --run
npm run build
```

Run the repeatable synthetic performance baseline from `backend/` with
`python -m scripts.benchmark_core`, and the concurrent HTTP/database regression exercise with
`python -m scripts.benchmark_http --requests 90 --concurrency 6`. All development fixtures must be labelled
`SYNTHETIC / DEVELOPMENT DATA`.

## Production boundaries

Production requires approved data-source licenses and credentials, reviewed Somalia boundary
data, distributed ingress/Redis rate limiting, managed encrypted backups with a witnessed restore,
representative load testing, monitoring integration, and an institutionally approved release.
None of those external approvals are fabricated by this repository.
