from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    assert TestClient(app).get("/api/v1/health").json() == {"status": "healthy"}


def test_readiness_checks_database() -> None:
    response = TestClient(app).get("/api/v1/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "available"}


def test_versioned_openapi() -> None:
    assert "/api/v1/health" in TestClient(app).get("/openapi.json").json()["paths"]


def test_metadata_keeps_risk_and_publication_separate() -> None:
    payload = TestClient(app).get("/api/v1/meta").json()
    assert payload["risk_domains"] == [
        "drought",
        "river_flood",
        "flash_flood",
        "food_security_deterioration",
    ]
    assert payload["automatic_warning_publication"] is False
    assert payload["official_ipc_output"] is False
