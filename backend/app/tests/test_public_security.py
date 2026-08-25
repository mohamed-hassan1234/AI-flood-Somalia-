from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.enums import AlertStatus, Classification, RiskLevel
from app.main import app
from app.modules.public_portal.service import AlertRecord, public_projection


def test_security_headers_and_request_id() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_internal_or_unpublished_alert_never_has_public_projection() -> None:
    assert (
        public_projection(
            AlertRecord(
                id=uuid4(),
                status=AlertStatus.PUBLISHED,
                classification=Classification.INTERNAL,
                title="Test",
                summary="Safe",
                risk_level=RiskLevel.WATCH,
                published_at=datetime.now(timezone.utc),
                internal_notes="secret",
            )
        )
        is None
    )
    assert (
        public_projection(
            AlertRecord(
                id=uuid4(),
                status=AlertStatus.APPROVED,
                classification=Classification.PUBLIC,
                title="Test",
                summary="Safe",
                risk_level=RiskLevel.WATCH,
                published_at=datetime.now(timezone.utc),
            )
        )
        is None
    )


def test_public_projection_is_allowlisted() -> None:
    record = AlertRecord(
        uuid4(),
        AlertStatus.PUBLISHED,
        Classification.PUBLIC,
        "Test",
        "Safe",
        RiskLevel.WARNING,
        datetime.now(timezone.utc),
        "never expose",
    )
    projection = public_projection(record)
    assert projection is not None
    assert "internal_notes" not in projection
