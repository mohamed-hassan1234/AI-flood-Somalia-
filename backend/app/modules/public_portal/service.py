from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.enums import AlertStatus, Classification, RiskLevel


@dataclass(frozen=True)
class AlertRecord:
    id: UUID
    status: AlertStatus
    classification: Classification
    title: str
    summary: str
    risk_level: RiskLevel
    published_at: datetime | None
    internal_notes: str | None = None


def public_projection(record: AlertRecord) -> dict[str, object] | None:
    if (
        record.status is not AlertStatus.PUBLISHED
        or record.classification is not Classification.PUBLIC
    ):
        return None
    return {
        "id": str(record.id),
        "title": record.title,
        "summary": record.summary,
        "risk_level": record.risk_level.value,
        "published_at": record.published_at,
    }
