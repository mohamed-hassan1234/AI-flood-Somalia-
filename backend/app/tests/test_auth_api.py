from collections.abc import Generator
from contextlib import contextmanager
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.enums import Classification
from app.db.base import Base
from app.db.models.core import AdminUnit, GeographicScope, Membership, Organization, Role, User
from app.db.session import get_db
from app.main import app
from app.modules.auth.security import hash_password


@contextmanager
def make_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        organization = Organization(
            name="SYNTHETIC / DEVELOPMENT DATA Ministry",
            organization_type="national government institution",
        )
        role = Role(
            name="National Analyst",
            description="test",
            capabilities=[
                "geography.read",
                "geography.manage",
                "indicators.read",
                "alerts.review",
                "organizations.manage",
                "users.manage",
            ],
        )
        privileged_role = Role(
            name="Synthetic Privileged Role",
            description="test escalation guard",
            capabilities=["platform.forbidden"],
        )
        user = User(
            email="analyst@example.org",
            display_name="Synthetic Analyst",
            password_hash=hash_password("development password only"),
        )
        country = AdminUnit(
            stable_code="SO",
            name="Somalia",
            level="country",
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add_all([organization, role, privileged_role, user, country])
        db.flush()
        region = AdminUnit(
            stable_code="SO-R1",
            name="Synthetic Region",
            level="region",
            parent_id=country.id,
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add(region)
        db.flush()
        db.add(
            AdminUnit(
                stable_code="SO-D1",
                name="Synthetic District",
                level="district",
                parent_id=region.id,
                boundary_version="synthetic-v1",
                boundary_source="SYNTHETIC / DEVELOPMENT DATA",
                valid_from=date(2020, 1, 1),
                aliases=[],
            )
        )
        membership = Membership(
            user_id=user.id,
            organization_id=organization.id,
            role_id=role.id,
            classification_ceiling=Classification.INTERNAL,
        )
        db.add(membership)
        db.flush()
        db.add(GeographicScope(membership_id=membership.id, national=True))
        db.commit()

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_login_me_and_rotating_refresh() -> None:
    with make_client() as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@example.org", "password": "development password only"},
        )
        assert login.status_code == 200
        tokens = login.json()
        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["capabilities"] == [
            "alerts.review",
            "geography.manage",
            "geography.read",
            "indicators.read",
            "organizations.manage",
            "users.manage",
        ]
        geography = client.get(
            "/api/v1/geography/admin-units",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert geography.status_code == 200
        assert {item["level"] for item in geography.json()} == {"country", "region", "district"}
        imported = client.post(
            "/api/v1/geography/boundaries/import",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={
                "version": "synthetic-v2",
                "source": "SYNTHETIC / DEVELOPMENT DATA",
                "valid_from": "2027-01-01",
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {"type": "Feature", "properties": {"stable_code": "SO", "name": "Somalia", "level": "country", "aliases": []}, "geometry": {"type": "Polygon", "coordinates": [[[45, 5], [46, 5], [46, 6], [45, 5]]]}},
                        {"type": "Feature", "properties": {"stable_code": "SO-R1", "name": "Synthetic Region", "level": "region", "parent_code": "SO", "aliases": []}, "geometry": {"type": "Polygon", "coordinates": [[[45, 5], [45.5, 5], [45.5, 5.5], [45, 5]]]}},
                        {"type": "Feature", "properties": {"stable_code": "SO-D1", "name": "Synthetic District", "level": "district", "parent_code": "SO-R1", "aliases": []}, "geometry": {"type": "Polygon", "coordinates": [[[45, 5], [45.2, 5], [45.2, 5.2], [45, 5]]]}},
                    ],
                },
            },
        )
        assert imported.status_code == 200
        boundaries = client.get(
            "/api/v1/geography/boundaries",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert boundaries.status_code == 200
        assert len(boundaries.json()["features"]) == 3
        assert boundaries.json()["features"][0]["properties"]["boundary_version"] == "synthetic-v2"
        historical_layer = client.get(
            "/api/v1/geography/boundaries",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            params={"boundary_version": "synthetic-v2"},
        )
        assert historical_layer.status_code == 200
        assert len(historical_layer.json()["features"]) == 3
        assert {
            item["properties"]["boundary_version"]
            for item in historical_layer.json()["features"]
        } == {"synthetic-v2"}
        resolved = client.get(
            "/api/v1/geography/resolve-point",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            params={
                "longitude": 45.15,
                "latitude": 5.05,
                "boundary_version": "synthetic-v2",
                "reference_date": "2027-01-02",
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["stable_code"] == "SO-D1"
        zonal = client.post(
            f"/api/v1/geography/admin-units/{resolved.json()['id']}/zonal-statistics",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={
                "values": [[None, 10], [20, 30]],
                "west": 45,
                "south": 5,
                "east": 45.2,
                "north": 5.2,
            },
        )
        assert zonal.status_code == 200
        assert zonal.json()["boundary_version"] == "synthetic-v2"
        assert zonal.json()["cells_in_zone"] == 2
        assert zonal.json()["valid_cells"] == 2
        assert zonal.json()["mean"] == 20
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 200
        replay = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401


def test_national_administrator_creates_password_safe_scoped_membership() -> None:
    with make_client() as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@example.org", "password": "development password only"},
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        organization = client.post(
            "/api/v1/administration/organizations",
            headers=headers,
            json={"name": "Synthetic Response Partner", "organization_type": "partner"},
        )
        assert organization.status_code == 201
        user = client.post(
            "/api/v1/administration/users",
            headers=headers,
            json={
                "email": "new.partner@example.org",
                "display_name": "Synthetic Partner User",
                "password": "development password only",
            },
        )
        assert user.status_code == 201
        assert "password" not in user.json()
        assert "password_hash" not in user.json()
        roles = client.get("/api/v1/administration/roles", headers=headers)
        assignable_role = next(item for item in roles.json() if item["name"] == "National Analyst")
        membership = client.post(
            "/api/v1/administration/memberships",
            headers=headers,
            json={
                "user_id": user.json()["id"],
                "organization_id": organization.json()["id"],
                "role_id": assignable_role["id"],
                "classification_ceiling": "partner",
                "national": True,
                "admin_unit_ids": [],
            },
        )
        assert membership.status_code == 201
        assert membership.json()["national"] is True
        assert membership.json()["classification_ceiling"] == "partner"
        memberships = client.get("/api/v1/administration/memberships", headers=headers)
        assert memberships.status_code == 200
        created_membership = next(
            item for item in memberships.json() if item["id"] == membership.json()["id"]
        )
        assert created_membership["national"] is True
        assert created_membership["admin_unit_ids"] == []
        forbidden_role = next(
            item for item in roles.json() if item["name"] == "Synthetic Privileged Role"
        )
        escalated = client.post(
            "/api/v1/administration/memberships",
            headers=headers,
            json={
                "user_id": user.json()["id"],
                "organization_id": organization.json()["id"],
                "role_id": forbidden_role["id"],
                "classification_ceiling": "partner",
                "national": True,
                "admin_unit_ids": [],
            },
        )
        assert escalated.status_code == 403
        assert client.post(
            "/api/v1/auth/login",
            json={
                "email": "new.partner@example.org",
                "password": "development password only",
            },
        ).status_code == 200


def test_bad_credentials_and_missing_bearer_are_rejected() -> None:
    with make_client() as client:
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "analyst@example.org", "password": "wrong password!!"},
            ).status_code
            == 401
        )
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/geography/admin-units").status_code == 401
        injection = client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@example.org' OR '1'='1", "password": "irrelevant password"},
        )
        assert injection.status_code == 422
