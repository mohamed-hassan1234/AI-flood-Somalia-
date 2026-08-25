from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from io import BytesIO
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
from app.modules.data_sources.router import get_object_storage


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def open(self, key: str) -> BytesIO:
        return BytesIO(self.objects[key])


FAKE_STORAGE = FakeObjectStorage()


@contextmanager
def source_client() -> Generator[tuple[TestClient, str, str], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    principal = Principal(
        uuid4(),
        "source-admin@example.org",
        "Synthetic Source Admin",
        (
            MembershipGrant(
                uuid4(),
                uuid4(),
                frozenset(
                    {
                        "data_sources.manage",
                        "data_sources.read",
                        "geography.read",
                        "indicators.read",
                        "indicators.manage",
                        "seasons.manage",
                        "seasons.approve",
                        "predictions.generate",
                    }
                ),
                Classification.INTERNAL,
                True,
                frozenset(),
            ),
        ),
    )
    with factory() as db:
        region = AdminUnit(
            stable_code="SO-R1",
            name="Synthetic Region",
            level="region",
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add(region)
        db.flush()
        unit = AdminUnit(
            stable_code="SO-D1",
            name="Synthetic District",
            level="district",
            parent_id=region.id,
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        sibling = AdminUnit(
            stable_code="SO-D2",
            name="Synthetic District Two",
            level="district",
            parent_id=region.id,
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add_all([unit, sibling])
        db.commit()
        unit_id = str(unit.id)
        region_id = str(region.id)

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_object_storage] = lambda: FAKE_STORAGE
    FAKE_STORAGE.objects.clear()
    try:
        yield TestClient(app), unit_id, region_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_registry_requires_complete_metadata_before_verification() -> None:
    with source_client() as (client, _, _):
        incomplete = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Unverified rainfall file",
                "domain": "rainfall",
                "access_method": "file",
                "verified": True,
            },
        )
        assert incomplete.status_code == 422
        created = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Unverified rainfall file",
                "domain": "rainfall",
                "access_method": "file",
                "verified": False,
            },
        )
        assert created.status_code == 201
        source_id = created.json()["id"]
        assert client.get("/api/v1/data-sources").json()[0]["verified"] is False
        health = client.get(f"/api/v1/data-sources/{source_id}/health")
        assert health.status_code == 200
        assert health.json()["status"] == "unknown"


def test_small_csv_fallback_is_idempotent_and_preserves_missing_values() -> None:
    content = "source_record_id,admin_unit_code,indicator_code,value,unit,reference_time\nr1,SO-D1,rainfall,,mm,2026-01-01T00:00:00Z\nr2,UNKNOWN,rainfall,4,mm,2026-01-02T00:00:00Z\n"
    with source_client() as (client, unit_id, _):
        created = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Fallback rainfall",
                "domain": "rainfall",
                "access_method": "file",
                "classification": "internal",
            },
        )
        source_id = created.json()["id"]
        files = {"file": ("rain.csv", content, "text/csv")}
        first = client.post(f"/api/v1/data-sources/{source_id}/imports/csv", files=files)
        assert first.status_code == 201
        assert first.json()["rows_accepted"] == 1
        assert first.json()["rows_quarantined"] == 1
        second = client.post(f"/api/v1/data-sources/{source_id}/imports/csv", files=files)
        assert second.status_code == 201
        assert second.json()["rows_accepted"] == 0
        observations = client.get("/api/v1/observations", params={"admin_unit_id": unit_id})
        assert observations.status_code == 200
        assert observations.json()[0]["value"] is None
        assert observations.json()[0]["stage"] == "raw"
        assert observations.json()[0]["quality_flags"] == [
            "source_unverified",
            "indicator_unregistered",
        ]
        assert observations.json()[0]["indicator_definition_id"] is None


def test_verified_normalized_evidence_creates_signal_not_warning() -> None:
    content = "source_record_id,admin_unit_code,indicator_code,value,unit,reference_time\nd1,SO-D1,drought.rainfall_deficit,0.8,index_0_1,2026-01-01T00:00:00Z\nd2,SO-D1,drought.vegetation_stress,0.7,index_0_1,2026-01-01T00:00:00Z\nd3,SO-D1,drought.dry_spell,0.6,index_0_1,2026-01-01T00:00:00Z\nd4,SO-D1,drought.unregistered,0.9,index_0_1,2026-01-01T00:00:00Z\n"
    with source_client() as (client, unit_id, _):
        source = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Verified synthetic drought source",
                "domain": "drought",
                "owner": "Synthetic owner",
                "license": "Synthetic test fixture license",
                "terms_url": "https://example.org/terms",
                "attribution": "SYNTHETIC / DEVELOPMENT DATA",
                "access_method": "file",
                "expected_frequency_minutes": 1440,
                "geographic_resolution": "synthetic district",
                "classification": "internal",
                "verified": True,
            },
        )
        assert source.status_code == 201
        for code in (
            "drought.rainfall_deficit",
            "drought.vegetation_stress",
            "drought.dry_spell",
        ):
            indicator = client.post(
                "/api/v1/indicators",
                json={
                    "code": code,
                    "name": code.replace(".", " "),
                    "domain": "drought",
                    "unit": "index_0_1",
                    "value_kind": "index",
                    "minimum_value": 0,
                    "maximum_value": 1,
                    "aggregation_method": "mean",
                    "version": "synthetic-v1",
                    "definition_source": "SYNTHETIC / DEVELOPMENT DATA",
                    "verified": True,
                },
            )
            assert indicator.status_code == 201
        assert len(client.get("/api/v1/indicators").json()) == 3
        season = client.post(
            "/api/v1/seasons",
            json={
                "name": "Synthetic test season",
                "start": "2025-12-01",
                "end": "2026-02-28",
                "authority": "SYNTHETIC / DEVELOPMENT DATA",
                "version": "synthetic-v1",
            },
        )
        assert season.status_code == 201
        assert season.json()["approved"] is False
        assert client.post(
            f"/api/v1/seasons/{season.json()['id']}/approval"
        ).status_code == 200
        overlap = client.post(
            "/api/v1/seasons",
            json={
                "name": "Synthetic overlap",
                "start": "2026-01-15",
                "end": "2026-03-01",
                "authority": "SYNTHETIC / DEVELOPMENT DATA",
                "version": "synthetic-overlap",
            },
        )
        assert client.post(
            f"/api/v1/seasons/{overlap.json()['id']}/approval"
        ).status_code == 409
        assert len(client.get("/api/v1/seasons").json()) == 1
        imported = client.post(
            f"/api/v1/data-sources/{source.json()['id']}/imports/csv",
            files={"file": ("drought.csv", content, "text/csv")},
        )
        assert imported.json()["rows_accepted"] == 3
        assert imported.json()["rows_quarantined"] == 1
        observations = client.get(
            "/api/v1/observations", params={"admin_unit_id": unit_id}
        ).json()
        assert all(row["indicator_definition_id"] for row in observations)
        assert all(row["indicator_version"] == "synthetic-v1" for row in observations)
        assert all(row["season_name"] == "Synthetic test season" for row in observations)
        assert all(row["season_version"] == "synthetic-v1" for row in observations)
        assert all(
            row["season_authority"] == "SYNTHETIC / DEVELOPMENT DATA"
            for row in observations
        )
        evaluated = client.post(
            "/api/v1/risks/drought/evaluations",
            json={"admin_unit_id": unit_id, "target_period": "2026-Gu"},
        )
        assert evaluated.status_code == 201
        payload = evaluated.json()
        assert payload["domain"] == "drought"
        assert payload["score"] == 0.715
        assert payload["provenance"]["automatic_warning_publication"] is False
        assert payload["provenance"]["lookback_days"] == 90
        assert payload["provenance"]["feature_weights"]["drought.rainfall_deficit"] == 0.4
        assert payload["provenance"]["score_thresholds"]["warning"] == 0.6
        assert payload["provenance"]["missing_indicators"] == []
        assert payload["drivers"][0]["boundary_version"] == "synthetic-v1"
        assert payload["drivers"][0]["unit"] == "index_0_1"
        stale_window = client.post(
            "/api/v1/risks/drought/evaluations",
            json={
                "admin_unit_id": unit_id,
                "target_period": "2026-Gu",
                "evaluation_at": "2026-06-01T00:00:00Z",
                "lookback_days": 30,
            },
        )
        assert stale_window.status_code == 422
        assert stale_window.json()["detail"] == "Insufficient verified normalized evidence"


def test_regional_aggregation_discloses_method_coverage_missingness_and_lineage() -> None:
    content = "source_record_id,admin_unit_code,indicator_code,value,unit,reference_time\na1,SO-D1,rainfall.total,10,mm,2026-01-01T00:00:00Z\na2,SO-D2,rainfall.total,20,mm,2026-01-01T00:00:00Z\na3,SO-D2,rainfall.total,,mm,2026-01-01T00:00:00Z\n"
    with source_client() as (client, _, region_id):
        source = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Synthetic aggregation source",
                "domain": "rainfall",
                "access_method": "file",
                "classification": "internal",
            },
        )
        imported = client.post(
            f"/api/v1/data-sources/{source.json()['id']}/imports/csv",
            files={"file": ("aggregate.csv", content, "text/csv")},
        )
        assert imported.json()["rows_accepted"] == 3
        response = client.get(
            "/api/v1/observations/aggregate",
            params={"admin_unit_id": region_id, "indicator_code": "rainfall.total"},
        )
        assert response.status_code == 200
        aggregate = response.json()[0]
        assert aggregate["value"] == 15.0
        assert aggregate["method"] == "unweighted_mean"
        assert aggregate["contributing_admin_units"] == 2
        assert aggregate["total_descendant_units"] == 2
        assert aggregate["missing_records"] == 1
        assert aggregate["source_names"] == ["Synthetic aggregation source"]


def test_csv_upload_rejects_unsupported_and_oversized_content() -> None:
    with source_client() as (client, _, _):
        source = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Synthetic upload security source",
                "domain": "rainfall",
                "access_method": "file",
                "classification": "internal",
            },
        )
        source_id = source.json()["id"]
        unsupported = client.post(
            f"/api/v1/data-sources/{source_id}/imports/csv",
            files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
        )
        assert unsupported.status_code == 415
        oversized = client.post(
            f"/api/v1/data-sources/{source_id}/imports/csv",
            files={"file": ("huge.csv", b"x" * (256 * 1024 + 1), "text/csv")},
        )
        assert oversized.status_code == 413


def test_verified_object_storage_connector_checks_prefix_checksum_and_registry() -> None:
    payload = b"source_record_id,admin_unit_code,indicator_code,value,unit,reference_time\no1,SO-D1,rainfall.total,12,mm,2026-01-01T00:00:00Z\n"
    with source_client() as (client, unit_id, _):
        assert client.post(
            "/api/v1/indicators",
            json={
                "code": "rainfall.total",
                "name": "Rainfall total",
                "domain": "rainfall",
                "unit": "mm",
                "value_kind": "observed",
                "minimum_value": 0,
                "maximum_value": 1000,
                "aggregation_method": "sum",
                "version": "synthetic-v1",
                "definition_source": "SYNTHETIC / DEVELOPMENT DATA",
                "verified": True,
            },
        ).status_code == 201
        source = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Verified synthetic object connector",
                "domain": "rainfall",
                "owner": "Synthetic owner",
                "license": "Synthetic fixture license",
                "terms_url": "https://example.org/terms",
                "attribution": "SYNTHETIC / DEVELOPMENT DATA",
                "access_method": "object_storage",
                "expected_frequency_minutes": 1440,
                "geographic_resolution": "synthetic district",
                "classification": "internal",
                "verified": True,
            },
        ).json()
        key = f"sources/{source['id']}/batch.csv"
        FAKE_STORAGE.objects[key] = payload
        imported = client.post(
            f"/api/v1/data-sources/{source['id']}/imports/object-storage",
            json={"object_key": key, "sha256": sha256(payload).hexdigest()},
        )
        assert imported.status_code == 201
        assert imported.json()["rows_accepted"] == 1
        observations = client.get(
            "/api/v1/observations", params={"admin_unit_id": unit_id}
        ).json()
        assert observations[0]["indicator_version"] == "synthetic-v1"
        assert client.post(
            f"/api/v1/data-sources/{source['id']}/imports/object-storage",
            json={"object_key": "sources/another/batch.csv", "sha256": "0" * 64},
        ).status_code == 422
        assert client.post(
            f"/api/v1/data-sources/{source['id']}/imports/object-storage",
            json={"object_key": key, "sha256": "0" * 64},
        ).status_code == 422
