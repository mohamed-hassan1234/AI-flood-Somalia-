from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.enums import AlertStatus, Classification, RiskDomain, RiskLevel
from app.db.base import Base
from app.db.models.core import AdminUnit, Alert, RiskSignal
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import MembershipGrant, Principal, get_current_principal


@contextmanager
def dashboard_client(national: bool = True) -> Generator[tuple[TestClient, object], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        unit = AdminUnit(
            stable_code="SO-DASH-D1",
            name="Synthetic Dashboard District",
            level="district",
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add(unit)
        db.flush()
        old = RiskSignal(
            domain=RiskDomain.DROUGHT,
            admin_unit_id=unit.id,
            level=RiskLevel.CRITICAL,
            score=0.95,
            confidence=0.8,
            drivers=[],
            provenance={"label": "SYNTHETIC / DEVELOPMENT DATA"},
            target_period="old-period",
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        latest = RiskSignal(
            domain=RiskDomain.DROUGHT,
            admin_unit_id=unit.id,
            level=RiskLevel.WATCH,
            score=0.4,
            confidence=0.8,
            drivers=[{"source_id": "synthetic-source"}],
            provenance={"label": "SYNTHETIC / DEVELOPMENT DATA"},
            target_period="2027-Gu",
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([old, latest])
        db.flush()
        db.add(
            Alert(
                signal_id=latest.id,
                status=AlertStatus.PUBLISHED,
                classification=Classification.INTERNAL,
                title="Synthetic dashboard warning",
                summary="SYNTHETIC / DEVELOPMENT DATA",
                published_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        unit_id = unit.id

    principal = Principal(
        uuid4(),
        "dashboard@example.org",
        "Synthetic Dashboard User",
        (
            MembershipGrant(
                uuid4(),
                uuid4(),
                frozenset({"predictions.read", "alerts.read"}),
                Classification.INTERNAL,
                national,
                frozenset() if national else frozenset({unit_id}),
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


def test_national_summary_uses_latest_signals_and_explicit_unknowns() -> None:
    with dashboard_client() as (client, _):
        response = client.get("/api/v1/dashboard/national-summary")
        assert response.status_code == 200
        payload = response.json()
        drought = payload["domains"][0]
        assert drought["domain"] == "drought"
        assert drought["level"] == "watch"
        assert drought["target_periods"] == ["2027-Gu"]
        assert drought["source_ids"] == ["synthetic-source"]
        assert drought["stale"] is False
        assert payload["domains"][1]["level"] is None
        assert payload["domains"][1]["stale"] is True
        assert payload["published_warning_count"] == 1


def test_national_summary_rejects_district_only_scope() -> None:
    with dashboard_client(national=False) as (client, _):
        response = client.get("/api/v1/dashboard/national-summary")
        assert response.status_code == 403


def test_district_scope_can_read_its_executive_summary() -> None:
    with dashboard_client(national=False) as (client, unit_id):
        scopes = client.get("/api/v1/dashboard/scopes")
        assert scopes.status_code == 200
        assert scopes.json()[0]["id"] == str(unit_id)

        response = client.get(
            "/api/v1/dashboard/national-summary", params={"admin_unit_id": str(unit_id)}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["scope_name"] == "Synthetic Dashboard District"
        assert payload["scope_level"] == "district"
        assert payload["boundary_version"] == "synthetic-v1"
        assert payload["domains"][0]["admin_units_evaluated"] == 1


def test_scoped_risk_list_returns_governed_signal_history() -> None:
    with dashboard_client(national=False) as (client, unit_id):
        response = client.get("/api/v1/risks", params={"admin_unit_id": str(unit_id)})
        assert response.status_code == 200
        payload = response.json()
        assert [item["target_period"] for item in payload] == ["2027-Gu", "old-period"]
        assert all(item["admin_unit_id"] == str(unit_id) for item in payload)
        assert all(item["created_at"] for item in payload)
