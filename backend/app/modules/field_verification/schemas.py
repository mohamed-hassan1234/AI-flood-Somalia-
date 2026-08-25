from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Classification, RiskDomain, VerificationStatus


class VerificationTaskCreate(BaseModel):
    alert_id: UUID
    assigned_to: UUID | None = None
    due_at: datetime
    priority: str = Field(pattern="^(low|normal|high|critical)$")
    form_schema: dict[str, object]


class VerificationTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    alert_id: UUID
    admin_unit_id: UUID
    assigned_to: UUID | None
    due_at: datetime
    priority: str
    status: VerificationStatus
    form_schema: dict[str, object]


class VerificationTaskListResponse(BaseModel):
    id: UUID
    alert_id: UUID
    alert_title: str
    classification: Classification
    admin_unit_id: UUID
    risk_domain: RiskDomain
    assigned_to: UUID | None
    due_at: datetime
    priority: str
    status: VerificationStatus


class FieldReportSubmit(BaseModel):
    answers: dict[str, object]
    evidence_objects: list[dict[str, object]] = Field(default_factory=list, max_length=20)


class FieldReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_id: UUID
    reporter_id: UUID
    answers: dict[str, object]
    evidence_objects: list[dict[str, object]]
    submitted_at: datetime
    review_notes: str | None


class VerificationReview(BaseModel):
    target: VerificationStatus
    notes: str = Field(min_length=3, max_length=5000)
