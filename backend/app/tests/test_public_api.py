from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.enums import AlertStatus, Classification, RiskDomain, RiskLevel
from app.db.base import Base
from app.db.models.core import AdminUnit, Alert, RiskSignal
from app.db.session import get_db
from app.main import app


@contextmanager
def public_client() -> Generator[tuple[TestClient, str], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        unit = AdminUnit(
            stable_code="SO-PUB-D1",
            name="Synthetic Public District",
            level="district",
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add(unit)
        db.flush()
        signals = [
            RiskSignal(
                domain=RiskDomain.DROUGHT,
                admin_unit_id=unit.id,
                level=RiskLevel.WARNING,
                score=0.7,
                confidence=0.8,
                drivers=[],
                provenance={},
                target_period="2027-Gu",
            )
            for _ in range(3)
        ]
        db.add_all(signals)
        db.flush()
        public = Alert(
            signal_id=signals[0].id,
            status=AlertStatus.PUBLISHED,
            classification=Classification.PUBLIC,
            title="Synthetic public warning",
            summary="SYNTHETIC / DEVELOPMENT DATA",
            published_at=datetime.now(timezone.utc),
        )
        internal = Alert(
            signal_id=signals[1].id,
            status=AlertStatus.PUBLISHED,
            classification=Classification.INTERNAL,
            title="Internal diagnostic",
            summary="must never appear",
            published_at=datetime.now(timezone.utc),
        )
        unapproved = Alert(
            signal_id=signals[2].id,
            status=AlertStatus.APPROVED,
            classification=Classification.PUBLIC,
            title="Not yet public",
            summary="must never appear",
        )
        db.add_all([public, internal, unapproved])
        db.commit()
        internal_id = str(internal.id)

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), internal_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_public_api_is_an_explicit_allowlist() -> None:
    with public_client() as (client, internal_id):
        response = client.get("/api/v1/public/warnings")
        assert response.status_code == 200
        warnings = response.json()
        assert len(warnings) == 1
        assert set(warnings[0]) == {
            "id",
            "title",
            "summary",
            "risk_domain",
            "risk_level",
            "target_period",
            "admin_unit_id",
            "admin_unit_name",
            "boundary_version",
            "published_at",
        }
        assert client.get(f"/api/v1/public/warnings/{internal_id}").status_code == 404
