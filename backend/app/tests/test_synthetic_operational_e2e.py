"""SYNTHETIC / DEVELOPMENT DATA end-to-end governance exercise."""

from app.core.enums import ActionStatus, AlertStatus, RiskLevel, VerificationStatus
from app.ml.evaluation import binary_metrics
from app.modules.alerts.service import TransitionRequest
from app.modules.alerts.service import transition as alert_transition
from app.modules.early_actions.service import transition as action_transition
from app.modules.field_verification.service import transition as verification_transition
from app.modules.notifications.service import deduplication_key
from app.modules.risks.baseline import EvidenceValue, transparent_baseline


def test_synthetic_signal_to_outcome_feedback_flow() -> None:
    signal = transparent_baseline([EvidenceValue(0.9, 0.5), EvidenceValue(0.8, 0.5)])
    assert signal.level is RiskLevel.CRITICAL

    alert = AlertStatus.DRAFT
    alert = alert_transition(
        TransitionRequest(alert, AlertStatus.IN_REVIEW, "alerts.review"), {"alerts.review"}
    )
    alert = alert_transition(
        TransitionRequest(alert, AlertStatus.VERIFICATION_REQUIRED, "field_tasks.create"),
        {"field_tasks.create"},
    )

    verification = verification_transition(
        VerificationStatus.OPEN, VerificationStatus.SUBMITTED, {"field_reports.submit"}
    )
    verification = verification_transition(
        verification, VerificationStatus.VERIFIED, {"field_reports.verify"}
    )
    assert verification is VerificationStatus.VERIFIED

    alert = alert_transition(
        TransitionRequest(
            AlertStatus.VERIFICATION_REQUIRED, AlertStatus.VERIFIED, "field_reports.verify"
        ),
        {"field_reports.verify"},
    )
    alert = alert_transition(
        TransitionRequest(alert, AlertStatus.APPROVED, "alerts.approve"), {"alerts.approve"}
    )
    alert = alert_transition(
        TransitionRequest(alert, AlertStatus.PUBLISHED, "alerts.publish"), {"alerts.publish"}
    )
    assert alert is AlertStatus.PUBLISHED

    action = action_transition(
        ActionStatus.PLANNED, ActionStatus.ASSIGNED, {"early_actions.update"}
    )
    action = action_transition(action, ActionStatus.IN_PROGRESS, {"early_actions.update"})
    action = action_transition(
        action, ActionStatus.COMPLETED, {"early_actions.complete"}, evidence_count=1
    )
    assert action is ActionStatus.COMPLETED
    assert deduplication_key("synthetic-alert", "synthetic-recipient", "in-app")

    outcome_metrics = binary_metrics([1], [signal.score or 0])
    assert outcome_metrics["recall"] == 1.0
