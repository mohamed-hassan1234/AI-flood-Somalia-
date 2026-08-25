from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.enums import Classification, RiskDomain, RiskLevel
from app.db.base import Base
from app.db.models.core import (
    AdminUnit,
    AuditEvent,
    GeographicScope,
    Membership,
    Organization,
    RiskSignal,
    Role,
    User,
)
from app.db.session import get_db
from app.integrations.notifications.port import NotificationMessage, SendResult
from app.integrations.notifications.providers import (
    DevelopmentSinkProvider,
    RoutingNotificationProvider,
)
from app.main import app
from app.modules.auth.security import hash_password
from app.modules.notifications.service import dispatch_delivery


@contextmanager
def alert_client() -> Generator[tuple[TestClient, sessionmaker[Session], UUID], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        org = Organization(
            name="Synthetic authority", organization_type="national government institution"
        )
        role = Role(
            name="Synthetic analyst",
            description="test",
            capabilities=[
                "alerts.create",
                "alerts.read",
                "alerts.review",
                "alerts.approve",
                "alerts.publish",
                "alerts.resolve",
                "field_tasks.create",
                "field_tasks.read",
                "field_reports.submit",
                "field_reports.verify",
                "exposure.calculate",
                "exposure.read",
                "early_actions.playbooks.manage",
                "early_actions.read",
                "early_actions.create",
                "early_actions.approve",
                "early_actions.assign",
                "early_actions.update",
                "early_actions.complete",
                "notifications.send",
                "notifications.read",
                "notifications.manage",
                "notifications.escalate",
                "reports.generate",
                "reports.publish",
                "reports.read",
            ],
        )
        public_role = Role(
            name="Synthetic public viewer",
            description="test",
            capabilities=["reports.read"],
        )
        user = User(
            email="alerts@example.org",
            display_name="Synthetic Analyst",
            password_hash=hash_password("development password only"),
        )
        public_user = User(
            email="public-viewer@example.org",
            display_name="Synthetic Public Viewer",
            password_hash=hash_password("development password only"),
        )
        unit = AdminUnit(
            stable_code="SO-D-SYN",
            name="Synthetic District",
            level="district",
            boundary_version="synthetic-v1",
            boundary_source="SYNTHETIC / DEVELOPMENT DATA",
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add_all([org, role, public_role, user, public_user, unit])
        db.flush()
        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            classification_ceiling=Classification.INTERNAL,
        )
        db.add(membership)
        db.flush()
        db.add(GeographicScope(membership_id=membership.id, national=True))
        public_membership = Membership(
            user_id=public_user.id,
            organization_id=org.id,
            role_id=public_role.id,
            classification_ceiling=Classification.PUBLIC,
        )
        db.add(public_membership)
        db.flush()
        db.add(GeographicScope(membership_id=public_membership.id, national=True))
        signal = RiskSignal(
            domain=RiskDomain.DROUGHT,
            admin_unit_id=unit.id,
            level=RiskLevel.WARNING,
            score=0.7,
            confidence=0.8,
            drivers=[{"indicator": "synthetic"}],
            provenance={"label": "SYNTHETIC / DEVELOPMENT DATA"},
            target_period="2026-09",
        )
        db.add(signal)
        db.commit()
        signal_id = signal.id

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), factory, signal_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def auth_header(
    client: TestClient, email: str = "alerts@example.org"
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "development password only"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_alert_lifecycle_is_http_authorized_and_audited() -> None:
    with alert_client() as (client, factory, signal_id):
        headers = auth_header(client)
        created = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={
                "signal_id": str(signal_id),
                "classification": "internal",
                "title": "Synthetic drought signal",
                "summary": "SYNTHETIC / DEVELOPMENT DATA",
            },
        )
        assert created.status_code == 201
        alert_id = created.json()["id"]
        assert (
            client.post(
                f"/api/v1/alerts/{alert_id}/transitions",
                headers=headers,
                json={"target": "published"},
            ).status_code
            == 409
        )
        for target in ("in_review", "approved", "published"):
            response = client.post(
                f"/api/v1/alerts/{alert_id}/transitions", headers=headers, json={"target": target}
            )
            assert response.status_code == 200
        assert (
            client.get(f"/api/v1/alerts/{alert_id}", headers=headers).json()["status"]
            == "published"
        )
        listed = client.get("/api/v1/alerts", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["risk_domain"] == "drought"
        assert listed.json()[0]["risk_level"] == "warning"
        exposure = client.post(
            "/api/v1/exposure/assessments",
            headers=headers,
            json={
                "alert_id": alert_id,
                "population": 1200,
                "source_lineage": {
                    "label": "SYNTHETIC / DEVELOPMENT DATA",
                    "method": "test fixture",
                },
                "confidence": 0.7,
            },
        )
        assert exposure.status_code == 201
        exposure_queue = client.get("/api/v1/exposure/assessments", headers=headers)
        assert exposure_queue.status_code == 200
        assert exposure_queue.json()[0]["alert_title"] == "Synthetic drought signal"
        assert exposure_queue.json()[0]["lineage_available"] is True
        assert "source_lineage" not in exposure_queue.json()[0]
        assert (
            client.get(
                f"/api/v1/exposure/assessments/{exposure.json()['id']}", headers=headers
            ).status_code
            == 200
        )
        resolved = client.post(
            f"/api/v1/alerts/{alert_id}/transitions",
            headers=headers,
            json={"target": "resolved"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == 5


def test_field_verification_submission_and_review_unlocks_approval() -> None:
    with alert_client() as (client, _, signal_id):
        headers = auth_header(client)
        created = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={
                "signal_id": str(signal_id),
                "classification": "internal",
                "title": "Synthetic verification signal",
                "summary": "SYNTHETIC / DEVELOPMENT DATA",
            },
        )
        alert_id = created.json()["id"]
        assert (
            client.post(
                f"/api/v1/alerts/{alert_id}/transitions",
                headers=headers,
                json={"target": "in_review"},
            ).status_code
            == 200
        )
        task = client.post(
            "/api/v1/field-verification/tasks",
            headers=headers,
            json={
                "alert_id": alert_id,
                "due_at": "2027-01-01T00:00:00Z",
                "priority": "high",
                "form_schema": {"required": ["local_observation"]},
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]
        listed = client.get("/api/v1/field-verification/tasks", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["alert_title"] == "Synthetic verification signal"
        assert "form_schema" not in listed.json()[0]
        report = client.post(
            f"/api/v1/field-verification/tasks/{task_id}/reports",
            headers=headers,
            json={
                "answers": {"local_observation": "synthetic"},
                "evidence_objects": [],
            },
        )
        assert report.status_code == 201
        reviewed = client.post(
            f"/api/v1/field-verification/tasks/{task_id}/reviews",
            headers=headers,
            json={"target": "verified", "notes": "Synthetic evidence reviewed"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "verified"
        approved = client.post(
            f"/api/v1/alerts/{alert_id}/transitions",
            headers=headers,
            json={"target": "approved"},
        )
        assert approved.status_code == 200


def test_approved_playbook_drives_evidenced_early_action() -> None:
    with alert_client() as (client, factory, signal_id):
        headers = auth_header(client)
        created = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={
                "signal_id": str(signal_id),
                "classification": "internal",
                "title": "Synthetic action warning",
                "summary": "SYNTHETIC / DEVELOPMENT DATA",
            },
        )
        alert_id = created.json()["id"]
        for target in ("in_review", "approved", "published"):
            assert (
                client.post(
                    f"/api/v1/alerts/{alert_id}/transitions",
                    headers=headers,
                    json={"target": target},
                ).status_code
                == 200
            )
        playbook = client.post(
            "/api/v1/early-actions/playbooks",
            headers=headers,
            json={
                "name": "Synthetic drought playbook",
                "risk_domain": "drought",
                "version": "test-v1",
                "steps": [{"action": "verify water access"}],
            },
        )
        assert playbook.status_code == 201
        playbook_id = playbook.json()["id"]
        assert (
            client.post(
                f"/api/v1/early-actions/playbooks/{playbook_id}/approval", headers=headers
            ).status_code
            == 200
        )
        with factory() as db:
            organization_id = str(db.scalar(select(Organization.id)))
        plan = client.post(
            "/api/v1/early-actions/plans",
            headers=headers,
            json={
                "alert_id": alert_id,
                "playbook_id": playbook_id,
                "owner_organization_id": organization_id,
                "title": "Synthetic response plan",
            },
        )
        assert plan.status_code == 201
        plan_id = plan.json()["id"]
        assert (
            client.post(
                f"/api/v1/early-actions/plans/{plan_id}/approval", headers=headers
            ).status_code
            == 200
        )
        item = client.post(
            f"/api/v1/early-actions/plans/{plan_id}/items",
            headers=headers,
            json={
                "owner_organization_id": organization_id,
                "description": "Inspect synthetic water points",
                "due_at": "2027-01-15T00:00:00Z",
            },
        )
        assert item.status_code == 201
        item_id = item.json()["id"]
        for target in ("assigned", "in_progress"):
            assert (
                client.post(
                    f"/api/v1/early-actions/items/{item_id}/transitions",
                    headers=headers,
                    json={"target": target},
                ).status_code
                == 200
            )
        assert (
            client.post(
                f"/api/v1/early-actions/items/{item_id}/transitions",
                headers=headers,
                json={"target": "completed"},
            ).status_code
            == 409
        )
        completed = client.post(
            f"/api/v1/early-actions/items/{item_id}/transitions",
            headers=headers,
            json={
                "target": "completed",
                "evidence_objects": [{"object_key": "synthetic/evidence-1"}],
            },
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        queue = client.get("/api/v1/early-actions/items", headers=headers)
        assert queue.status_code == 200
        assert queue.json()[0]["plan_title"] == "Synthetic response plan"
        assert queue.json()[0]["evidence_count"] == 1
        assert "evidence_objects" not in queue.json()[0]


def test_notification_is_deduplicated_acknowledged_and_not_escalated_after_ack() -> None:
    with alert_client() as (client, factory, signal_id):
        headers = auth_header(client)
        user_id = client.get("/api/v1/auth/me", headers=headers).json()["user_id"]
        created = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={
                "signal_id": str(signal_id),
                "classification": "internal",
                "title": "Synthetic notified warning",
                "summary": "SYNTHETIC / DEVELOPMENT DATA",
            },
        )
        alert_id = created.json()["id"]
        for target in ("in_review", "approved", "published"):
            assert (
                client.post(
                    f"/api/v1/alerts/{alert_id}/transitions",
                    headers=headers,
                    json={"target": target},
                ).status_code
                == 200
            )
        delivery_body = {
            "event_key": "synthetic-warning-published",
            "recipient_key": user_id,
            "channel": "in_app",
            "alert_id": alert_id,
        }
        delivery = client.post(
            "/api/v1/notifications/deliveries", headers=headers, json=delivery_body
        )
        duplicate = client.post(
            "/api/v1/notifications/deliveries", headers=headers, json=delivery_body
        )
        assert duplicate.json()["id"] == delivery.json()["id"]
        queue = client.get("/api/v1/notifications/deliveries", headers=headers)
        assert queue.status_code == 200
        assert queue.json()[0]["event_title"] == "Synthetic notified warning"
        assert queue.json()[0]["recipient_is_current_user"] is True
        assert "recipient_key" not in queue.json()[0]
        with factory() as db:
            dispatched = dispatch_delivery(
                db,
                UUID(delivery.json()["id"]),
                RoutingNotificationProvider(DevelopmentSinkProvider()),
            )
            assert dispatched.status.value == "delivered"
            assert dispatched.provider_message_id is not None
        acknowledged = client.post(
            f"/api/v1/notifications/deliveries/{delivery.json()['id']}/acknowledgement",
            headers=headers,
        )
        assert acknowledged.json()["status"] == "acknowledged"
        assert (
            client.post(
                f"/api/v1/notifications/deliveries/{delivery.json()['id']}/escalation",
                headers=headers,
            ).status_code
            == 409
        )

        external = client.post(
            "/api/v1/notifications/deliveries",
            headers=headers,
            json={**delivery_body, "event_key": "synthetic-email", "channel": "email"},
        )

        class RetryableFailureProvider:
            def send(self, message: NotificationMessage) -> SendResult:
                assert message.channel == "email"
                return SendResult(False, retryable=True, error_code="synthetic_unavailable")

        attempt_time = datetime(2027, 1, 1, tzinfo=timezone.utc)
        with factory() as db:
            first = dispatch_delivery(
                db,
                UUID(external.json()["id"]),
                RetryableFailureProvider(),
                now=attempt_time,
                max_attempts=2,
            )
            assert first.status.value == "failed"
            assert first.next_attempt_at is not None
            second = dispatch_delivery(
                db,
                first.id,
                RetryableFailureProvider(),
                now=attempt_time + timedelta(minutes=2),
                max_attempts=2,
            )
            assert second.dead_lettered_at is not None
            assert second.next_attempt_at is None
            assert second.last_error_code == "synthetic_unavailable"


def test_partner_report_requires_publication_and_preserves_classification() -> None:
    with alert_client() as (client, factory, signal_id):
        analyst = auth_header(client)
        public_viewer = auth_header(client, "public-viewer@example.org")
        created = client.post(
            "/api/v1/alerts",
            headers=analyst,
            json={
                "signal_id": str(signal_id),
                "classification": "public",
                "title": "Synthetic published warning",
                "summary": "SYNTHETIC / DEVELOPMENT DATA",
            },
        )
        alert_id = created.json()["id"]
        for target in ("in_review", "approved", "published"):
            assert client.post(
                f"/api/v1/alerts/{alert_id}/transitions",
                headers=analyst,
                json={"target": target},
                ).status_code == 200
        partner_warnings = client.get("/api/v1/alerts/partner-warnings", headers=analyst)
        assert partner_warnings.status_code == 200
        assert [item["status"] for item in partner_warnings.json()] == ["published"]

        payload = {
            "alert_id": alert_id,
            "classification": "partner",
            "title": "Synthetic partner situation report",
            "reporting_period": "2027-Gu",
            "sections": [{"heading": "Situation", "body": "Synthetic evidence only"}],
            "findings": ["Synthetic finding"],
            "recommendations": ["Use an approved playbook"],
            "source_lineage": [{
                "source_id": "synthetic-source",
                "reference_period": "2027-Gu",
                "retrieved_at": "2027-01-15T10:00:00Z",
            }],
        }
        created_report = client.post("/api/v1/reports", headers=analyst, json=payload)
        assert created_report.status_code == 201
        report_id = created_report.json()["id"]
        assert created_report.json()["status"] == "draft"
        assert client.get(f"/api/v1/reports/{report_id}", headers=analyst).status_code == 404

        published = client.post(f"/api/v1/reports/{report_id}/publish", headers=analyst)
        assert published.status_code == 200
        assert published.json()["status"] == "published"
        exported = client.get(
            f"/api/v1/reports/{report_id}/export?format=csv", headers=analyst
        )
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        assert "source_lineage" not in exported.text
        document = client.get(
            f"/api/v1/reports/{report_id}/export?format=html", headers=analyst
        )
        assert document.status_code == 200
        assert document.headers["content-type"].startswith("text/html")
        assert "sandbox" in document.headers["content-security-policy"]
        assert 'attachment; filename="report-' in document.headers["content-disposition"]
        assert "SOMALIA AI · GOVERNED SITUATION REPORT" in document.text
        assert payload["sections"][0]["body"] in document.text
        assert "source_lineage" not in document.text
        assert client.get(
            f"/api/v1/reports/{report_id}", headers=public_viewer
        ).status_code == 403
        assert client.get("/api/v1/alerts", headers=public_viewer).status_code == 403
        public_payload = {
            **payload,
            "classification": "public",
            "title": "Synthetic public situation report",
        }
        public_report = client.post("/api/v1/reports", headers=analyst, json=public_payload)
        assert public_report.status_code == 201
        assert client.post(
            f"/api/v1/reports/{public_report.json()['id']}/publish", headers=analyst
        ).status_code == 200
        public_reports = client.get("/api/v1/public/reports")
        assert public_reports.status_code == 200
        assert public_reports.json()[0]["title"] == "Synthetic public situation report"
        assert public_reports.json()[0]["admin_unit_name"] == "Synthetic District"
        assert "source_lineage" not in public_reports.json()[0]
        assert "created_by" not in public_reports.json()[0]
        with factory() as db:
            actions = set(
                db.scalars(select(AuditEvent.action).where(AuditEvent.entity_type == "report"))
            )
            assert actions == {"reports.generate", "reports.publish"}
