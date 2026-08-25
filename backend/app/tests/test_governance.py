import pytest

from app.core.enums import AlertStatus, RiskLevel
from app.modules.alerts.service import InvalidTransition, TransitionRequest, transition
from app.modules.risks.baseline import EvidenceValue, transparent_baseline


def test_critical_signal_cannot_skip_human_review() -> None:
    with pytest.raises(InvalidTransition):
        transition(
            TransitionRequest(AlertStatus.DRAFT, AlertStatus.PUBLISHED, "alerts.publish"),
            {"alerts.publish"},
        )


def test_publication_requires_capability() -> None:
    with pytest.raises(PermissionError):
        transition(
            TransitionRequest(AlertStatus.APPROVED, AlertStatus.PUBLISHED, "alerts.publish"), set()
        )


def test_missing_evidence_is_not_zero_filled() -> None:
    result = transparent_baseline([EvidenceValue(None, 0.6), EvidenceValue(0.9, 0.4)])
    assert result.low_data is True
    assert result.score is None
    assert result.level is RiskLevel.NORMAL


def test_transparent_thresholds() -> None:
    result = transparent_baseline([EvidenceValue(0.8, 1), EvidenceValue(0.6, 1)])
    assert result.level is RiskLevel.WARNING
    assert result.score == 0.7


def test_out_of_range_evidence_is_rejected() -> None:
    with pytest.raises(ValueError):
        transparent_baseline([EvidenceValue(1.1, 1)])
