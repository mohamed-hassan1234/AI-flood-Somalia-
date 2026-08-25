from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.enums import Classification
from app.db.base import Base
from app.db.models.core import AdminUnit
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import MembershipGrant, Principal, get_current_principal


@contextmanager
def ml_client() -> Generator[tuple[TestClient, str], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        unit = AdminUnit(
            stable_code="SO-ML-D1",
            name="Synthetic ML District",
            level="district",
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add(unit)
        db.commit()
        unit_id = str(unit.id)
    capabilities = frozenset(
        {
            "models.train",
            "models.read",
            "models.promote",
            "models.rollback",
            "models.infer",
            "models.evaluate",
            "outcomes.manage",
            "scenarios.run",
            "scenarios.read",
        }
    )
    principal = Principal(
        uuid4(),
        "ml@example.org",
        "Synthetic ML Scientist",
        (
            MembershipGrant(
                uuid4(), uuid4(), capabilities, Classification.INTERNAL, True, frozenset()
            ),
        ),
    )

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: principal
    try:
        yield TestClient(app), unit_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_registry_promotion_prediction_outcome_and_simulation() -> None:
    with ml_client() as (client, unit_id):
        snapshot = client.post(
            "/api/v1/ml/snapshots",
            json={
                "name": "Synthetic chronological snapshot",
                "content_hash": "a" * 64,
                "target_definition": {"event": "drought", "horizon_days": 30},
                "source_versions": [{"source": "synthetic-v1"}],
                "object_uri": "s3://test/snapshot.parquet",
                "row_count": 100,
            },
        )
        assert snapshot.status_code == 201
        feature = client.post(
            "/api/v1/ml/feature-versions",
            json={
                "name": "Synthetic drought features",
                "version": "test-v1",
                "definitions": [{"name": "rainfall_deficit"}],
                "leakage_controls": ["features stop at forecast issue time"],
            },
        )
        assert feature.status_code == 201
        model = client.post(
            "/api/v1/ml/models",
            json={
                "name": "Transparent drought benchmark",
                "version": "test-v1",
                "dataset_snapshot_id": snapshot.json()["id"],
                "feature_version_id": feature.json()["id"],
                "artifact_uri": "s3://test/model.joblib",
                "metrics": {
                    "precision": 0.7,
                    "recall": 0.8,
                    "f1": 0.74,
                    "macro_f1": 0.72,
                    "pr_auc": 0.76,
                    "roc_auc": 0.75,
                    "brier": 0.16,
                    "calibration_error": 0.08,
                    "high_risk_recall": 0.68,
                    "useful_lead_time_days": 21,
                },
                "model_card": {
                    "chronological_backtest": True,
                    "region_evaluation": True,
                    "season_evaluation": True,
                    "horizon_evaluation": True,
                    "calibration_evaluation": True,
                    "lead_time_evaluation": True,
                    "limitations": ["SYNTHETIC / DEVELOPMENT DATA"],
                },
            },
        )
        assert model.status_code == 201
        model_id = model.json()["id"]
        operations = client.get("/api/v1/ml/operations")
        assert operations.status_code == 200
        assert operations.json()[0]["snapshot_row_count"] == 100
        assert operations.json()[0]["feature_version"] == "test-v1"
        assert operations.json()[0]["promotion_ready"] is True
        assert "artifact_uri" not in operations.json()[0]
        assert (
            client.post(
                f"/api/v1/ml/models/{model_id}/transitions", json={"target": "validated"}
            ).status_code
            == 200
        )
        promoted = client.post(
            f"/api/v1/ml/models/{model_id}/transitions", json={"target": "production"}
        )
        assert promoted.status_code == 200
        prediction = client.post(
            "/api/v1/ml/predictions",
            json={
                "model_version_id": model_id,
                "admin_unit_id": unit_id,
                "domain": "drought",
                "target_period": "2027-Gu",
                "forecast_horizon_days": 30,
                "probability": 0.8,
                "uncertainty": {"interval": [0.65, 0.9], "low_data": False},
                "explanation": [{"feature": "rainfall_deficit", "contribution": 0.4}],
            },
        )
        assert prediction.status_code == 201
        assert prediction.json()["level"] == "critical"
        outcome = client.post(
            "/api/v1/outcomes",
            json={
                "prediction_id": prediction.json()["id"],
                "observed": True,
                "observed_at": "2027-05-01T00:00:00Z",
                "source_lineage": {"source": "SYNTHETIC / DEVELOPMENT DATA"},
            },
        )
        assert outcome.status_code == 201
        metrics = client.get(f"/api/v1/outcomes/models/{model_id}/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["recall"] == 1.0
        assert metrics.json()["macro_f1"] == 1.0
        assert metrics.json()["pr_auc"] is None
        assert metrics.json()["roc_auc"] is None
        assert metrics.json()["useful_lead_time_days"] > 0
        assert {item["dimension"] for item in metrics.json()["strata"]} == {
            "region",
            "season",
            "forecast_horizon_days",
        }
        scenario = client.post(
            "/api/v1/scenarios",
            json={
                "name": "Synthetic compound shock",
                "baseline_snapshot_id": snapshot.json()["id"],
                "admin_unit_id": unit_id,
                "domain": "drought",
                "baseline_score": 0.4,
                "modifications": {"rainfall_reduction": 0.2, "price_increase": 0.1},
            },
        )
        assert scenario.status_code == 201
        assert scenario.json()["label"] == "SIMULATION"
        assert scenario.json()["result"]["may_publish_warning"] is False
        options = client.get("/api/v1/ml/snapshot-options")
        assert options.status_code == 200
        assert options.json() == [
            {"id": snapshot.json()["id"], "name": "Synthetic chronological snapshot", "row_count": 100}
        ]
        history = client.get("/api/v1/scenarios")
        assert history.status_code == 200
        assert history.json()[0]["admin_unit_name"] == "Synthetic ML District"
        assert history.json()[0]["label"] == "SIMULATION"
        assert "created_by" not in history.json()[0]


def test_promotion_rejects_incomplete_model_card() -> None:
    with ml_client() as (client, _):
        snapshot = client.post(
            "/api/v1/ml/snapshots",
            json={
                "name": "Synthetic snapshot",
                "content_hash": "b" * 64,
                "target_definition": {"event": "flood"},
                "source_versions": [{"source": "synthetic-v1"}],
                "object_uri": "s3://test/snapshot.parquet",
                "row_count": 20,
            },
        ).json()
        feature = client.post(
            "/api/v1/ml/feature-versions",
            json={
                "name": "Synthetic features",
                "version": "test-bad",
                "definitions": [{"name": "river"}],
                "leakage_controls": ["chronological cutoff"],
            },
        ).json()
        model = client.post(
            "/api/v1/ml/models",
            json={
                "name": "Incomplete candidate",
                "version": "test-bad",
                "dataset_snapshot_id": snapshot["id"],
                "feature_version_id": feature["id"],
                "artifact_uri": "s3://test/model.joblib",
                "metrics": {"precision": 0.5},
                "model_card": {},
            },
        ).json()
        model_id = model["id"]
        assert (
            client.post(
                f"/api/v1/ml/models/{model_id}/transitions", json={"target": "validated"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/ml/models/{model_id}/transitions", json={"target": "production"}
            ).status_code
            == 409
        )
