from dataclasses import dataclass

from app.core.enums import AlertStatus


class InvalidTransition(ValueError):
    pass


TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
    AlertStatus.DRAFT: {AlertStatus.IN_REVIEW},
    AlertStatus.IN_REVIEW: {AlertStatus.VERIFICATION_REQUIRED, AlertStatus.APPROVED},
    AlertStatus.VERIFICATION_REQUIRED: {AlertStatus.VERIFIED},
    AlertStatus.VERIFIED: {AlertStatus.APPROVED},
    AlertStatus.APPROVED: {AlertStatus.PUBLISHED},
    AlertStatus.PUBLISHED: {AlertStatus.RESOLVED},
    AlertStatus.RESOLVED: set(),
}


@dataclass(frozen=True)
class TransitionRequest:
    current: AlertStatus
    target: AlertStatus
    capability: str


REQUIRED_CAPABILITY = {
    AlertStatus.IN_REVIEW: "alerts.review",
    AlertStatus.VERIFICATION_REQUIRED: "field_tasks.create",
    AlertStatus.VERIFIED: "field_reports.verify",
    AlertStatus.APPROVED: "alerts.approve",
    AlertStatus.PUBLISHED: "alerts.publish",
    AlertStatus.RESOLVED: "alerts.resolve",
}


def transition(request: TransitionRequest, granted: set[str]) -> AlertStatus:
    if request.target not in TRANSITIONS[request.current]:
        raise InvalidTransition(f"{request.current} cannot transition to {request.target}")
    required = REQUIRED_CAPABILITY[request.target]
    if request.capability != required or required not in granted:
        raise PermissionError(f"Missing capability: {required}")
    return request.target
