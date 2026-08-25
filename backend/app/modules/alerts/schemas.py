from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AlertStatus, Classification, RiskDomain, RiskLevel


class AlertCreate(BaseModel):
    signal_id: UUID
    classification: Classification = Classification.INTERNAL
    title: str = Field(min_length=3, max_length=255)
    summary: str = Field(min_length=3, max_length=5000)


class AlertTransition(BaseModel):
    target: AlertStatus


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    signal_id: UUID
    status: AlertStatus
    classification: Classification
    title: str
    summary: str


class AlertListResponse(AlertResponse):
    admin_unit_id: UUID
    risk_domain: RiskDomain
    risk_level: RiskLevel
    target_period: str
    created_at: datetime
    published_at: datetime | None
