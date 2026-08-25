"""Concurrent synthetic HTTP/database benchmark; never a production capacity claim."""

import argparse
import asyncio
import json
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import Classification, RiskDomain
from app.db.base import Base
from app.db.models.core import (
    AdminUnit,
    DatasetSnapshot,
    DataSource,
    FeatureVersion,
    ModelVersion,
    Prediction,
    User,
)
from app.db.seed import ROLE_EMAILS, seed_development
from app.db.session import get_db
from app.main import create_app
from app.modules.auth.security import issue_access_token
from app.modules.ingestion.csv_adapter import ImportResult, ParsedObservation
from app.modules.ingestion.service import import_observation_batch
from app.modules.risks.baseline import EvidenceValue, transparent_baseline

SYNTHETIC_PASSWORD = "synthetic benchmark password"
PATHS = (
    ("readiness", "/api/v1/readiness"),
    ("national_summary", "/api/v1/dashboard/national-summary"),
    ("map_layer", "/api/v1/geography/boundaries"),
    ("district_time_series", "/api/v1/observations?admin_unit_id={admin_unit_id}"),
    ("risk_list", "/api/v1/risks"),
    ("alert_list", "/api/v1/alerts"),
    ("report_list", "/api/v1/reports"),
    ("public_warning_list", "/api/v1/public/warnings"),
    ("public_report_list", "/api/v1/public/reports"),
)


@dataclass(frozen=True)
class RequestSample:
    operation: str
    status_code: int
    duration_ms: float


def percentile(samples: list[float], percentile_value: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile_value)))
    return ordered[index]


async def exercise(
    app: FastAPI, token: str, requests: int, concurrency: int, admin_unit_id: str
) -> tuple[list[RequestSample], float]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://synthetic.test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        semaphore = asyncio.Semaphore(concurrency)

        async def request_one(index: int) -> RequestSample:
            operation, path_template = PATHS[index % len(PATHS)]
            path = path_template.format(admin_unit_id=admin_unit_id)
            async with semaphore:
                started = perf_counter()
                response = await client.get(path, headers=headers)
                duration = (perf_counter() - started) * 1000
            return RequestSample(operation, response.status_code, duration)

        started = perf_counter()
        samples = await asyncio.gather(*(request_one(index) for index in range(requests)))
        elapsed = perf_counter() - started
    return list(samples), elapsed


def exercise_database_workloads(
    db: Session, district: AdminUnit, rows: int = 200
) -> dict[str, Any]:
    source = DataSource(
        name="Synthetic benchmark source",
        domain="benchmark",
        access_method="generated",
        classification=Classification.INTERNAL,
        verified=False,
        enabled=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    parsed = ImportResult(
        accepted=tuple(
            ParsedObservation(
                source_record_id=f"benchmark-{index}",
                admin_unit_code=district.stable_code,
                indicator_code="synthetic_benchmark_indicator",
                value=float(index % 100) / 100,
                unit="index",
                reference_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
            for index in range(rows)
        ),
        rejected=(),
    )
    started = perf_counter()
    run = import_observation_batch(db, source, parsed)
    ingestion_seconds = perf_counter() - started

    snapshot = DatasetSnapshot(
        name="Synthetic benchmark snapshot",
        content_hash="b" * 64,
        target_definition={"label": "synthetic"},
        source_versions=[],
        object_uri="synthetic://benchmark/snapshot",
        row_count=rows,
    )
    features = FeatureVersion(
        name="Synthetic benchmark features",
        version="synthetic-benchmark-v1",
        definitions=[],
        leakage_controls=["synthetic-only"],
    )
    db.add_all([snapshot, features])
    db.flush()
    model = ModelVersion(
        name="Transparent synthetic benchmark",
        version="synthetic-benchmark-v1",
        state="development",
        dataset_snapshot_id=snapshot.id,
        feature_version_id=features.id,
        artifact_uri="synthetic://benchmark/model",
        metrics={},
        model_card={"limitations": ["Synthetic benchmark only"]},
    )
    db.add(model)
    db.flush()
    started = perf_counter()
    predictions = []
    for index in range(rows):
        baseline = transparent_baseline(
            [EvidenceValue((index % 100) / 100, 0.6), EvidenceValue(0.5, 0.4)]
        )
        predictions.append(
            Prediction(
                model_version_id=model.id,
                admin_unit_id=district.id,
                domain=RiskDomain.DROUGHT,
                target_period=f"synthetic-{index}",
                forecast_horizon_days=30,
                probability=baseline.score or 0.0,
                level=baseline.level,
                uncertainty={"kind": "synthetic"},
                explanation=[],
                dataset_snapshot_id=snapshot.id,
                feature_version_id=features.id,
            )
        )
    db.add_all(predictions)
    db.commit()
    prediction_seconds = perf_counter() - started

    def summarize(duration: float, count: int) -> dict[str, Any]:
        return {
            "rows": count,
            "duration_ms": round(duration * 1000, 3),
            "rows_per_second": round(count / duration, 3),
        }

    return {
        "bulk_ingestion": {
            **summarize(ingestion_seconds, rows),
            "accepted": run.rows_accepted,
            "quarantined": run.rows_quarantined,
        },
        "batch_predictions": summarize(prediction_seconds, len(predictions)),
    }


def run_benchmark(requests: int, concurrency: int) -> dict[str, Any]:
    if requests < len(PATHS) or concurrency < 1 or concurrency > requests:
        raise ValueError(
            f"requests must cover all {len(PATHS)} routes; concurrency must be positive "
            "and cannot exceed requests"
        )
    with TemporaryDirectory(prefix="somalia-ai-benchmark-") as directory:
        database_path = Path(directory) / "synthetic-load.db"
        database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        settings = Settings(
            environment="test",
            database_url=database_url,
            auth_rate_limit_per_minute=10_000,
            public_rate_limit_per_minute=100_000,
        )
        with factory() as db:
            seed_development(db, Settings(environment="test"), SYNTHETIC_PASSWORD)
            user = db.scalar(select(User).where(User.email == ROLE_EMAILS["National Analyst"]))
            if user is None:
                raise RuntimeError("Synthetic benchmark user was not seeded")
            district = db.scalar(select(AdminUnit).where(AdminUnit.level == "district"))
            if district is None:
                raise RuntimeError("Synthetic benchmark district was not seeded")
            token = issue_access_token(user.id, settings)
            operations = exercise_database_workloads(db, district)
            district_id = str(district.id)
        app = create_app(settings)

        def override_db() -> Generator[Session, None, None]:
            with factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            samples, elapsed = asyncio.run(exercise(app, token, requests, concurrency, district_id))
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    grouped: dict[str, list[RequestSample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.operation].append(sample)
    route_results = {}
    for operation, path_samples in sorted(grouped.items()):
        durations = [sample.duration_ms for sample in path_samples]
        route_results[operation] = {
            "requests": len(path_samples),
            "errors": sum(sample.status_code >= 400 for sample in path_samples),
            "p50_ms": round(percentile(durations, 0.50), 3),
            "p95_ms": round(percentile(durations, 0.95), 3),
            "max_ms": round(max(durations), 3),
        }
    errors = sum(sample.status_code >= 400 for sample in samples)
    return {
        "label": "SYNTHETIC / DEVELOPMENT DATA",
        "environment": "in-process ASGI + SQLite",
        "requests": requests,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_requests_per_second": round(requests / elapsed, 3),
        "error_rate": round(errors / requests, 6),
        "routes": route_results,
        "operations": operations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--max-operation-ms", type=float)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    args = parser.parse_args()
    result = run_benchmark(args.requests, args.concurrency)
    print(json.dumps(result, indent=2))
    route_p95 = max(float(route["p95_ms"]) for route in result["routes"].values())
    if args.max_p95_ms is not None and route_p95 > args.max_p95_ms:
        raise SystemExit(f"Synthetic p95 regression: {route_p95}ms > {args.max_p95_ms}ms")
    operation_max = max(
        float(operation["duration_ms"]) for operation in result["operations"].values()
    )
    if args.max_operation_ms is not None and operation_max > args.max_operation_ms:
        raise SystemExit(
            f"Synthetic database regression: {operation_max}ms > {args.max_operation_ms}ms"
        )
    if float(result["error_rate"]) > args.max_error_rate:
        raise SystemExit(
            f"Synthetic error-rate regression: {result['error_rate']} > {args.max_error_rate}"
        )


if __name__ == "__main__":
    main()
