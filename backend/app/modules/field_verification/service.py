from app.core.enums import VerificationStatus

TRANSITIONS = {
    VerificationStatus.OPEN: {VerificationStatus.SUBMITTED},
    VerificationStatus.SUBMITTED: {
        VerificationStatus.VERIFIED,
        VerificationStatus.REJECTED,
        VerificationStatus.MORE_EVIDENCE,
    },
    VerificationStatus.MORE_EVIDENCE: {VerificationStatus.SUBMITTED},
    VerificationStatus.VERIFIED: set(),
    VerificationStatus.REJECTED: set(),
}


def transition(
    current: VerificationStatus, target: VerificationStatus, capabilities: set[str]
) -> VerificationStatus:
    if target not in TRANSITIONS[current]:
        raise ValueError("Invalid field-verification transition")
    required = (
        "field_reports.submit" if target is VerificationStatus.SUBMITTED else "field_reports.verify"
    )
    if required not in capabilities:
        raise PermissionError(f"Missing capability: {required}")
    return target
