from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ActionStatus, RiskDomain


class PlaybookCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    risk_domain: RiskDomain
    version: str = Field(min_length=1, max_length=40)
    steps: list[dict[str, object]] = Field(min_length=1)


class PlaybookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    risk_domain: RiskDomain
    approved: bool
    approved_by: UUID | None
    version: str
    steps: list[dict[str, object]]


class ActionPlanCreate(BaseModel):
    alert_id: UUID
    playbook_id: UUID
    owner_organization_id: UUID
    title: str = Field(min_length=3, max_length=255)


class ActionPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    alert_id: UUID
    playbook_id: UUID
    owner_organization_id: UUID
    title: str
    approved: bool


class ActionItemCreate(BaseModel):
    owner_id: UUID | None = None
    owner_organization_id: UUID
    description: str = Field(min_length=3, max_length=5000)
    due_at: datetime


class ActionItemTransition(BaseModel):
    target: ActionStatus
    blockers: list[str] = Field(default_factory=list, max_length=20)
    evidence_objects: list[dict[str, object]] = Field(default_factory=list, max_length=20)


class ActionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    plan_id: UUID
    owner_id: UUID | None
    owner_organization_id: UUID
    description: str
    due_at: datetime
    status: ActionStatus
    blockers: list[str]
    evidence_objects: list[dict[str, object]]


class ActionItemListResponse(BaseModel):
    id: UUID
    plan_id: UUID
    plan_title: str
    alert_title: str
    risk_domain: RiskDomain
    classification: str
    admin_unit_id: UUID
    owner_id: UUID | None
    owner_organization_id: UUID
    description: str
    due_at: datetime
    status: ActionStatus
    blockers: list[str]
    evidence_count: int
