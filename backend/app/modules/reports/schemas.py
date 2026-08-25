from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import Classification, ReportStatus


class ReportSection(BaseModel):
    heading: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=5000)


class SourceReference(BaseModel):
    source_id: str = Field(min_length=1, max_length=255)
    reference_period: str = Field(min_length=1, max_length=120)
    retrieved_at: datetime


class ReportCreate(BaseModel):
    alert_id: UUID
    classification: Classification
    title: str = Field(min_length=1, max_length=255)
    reporting_period: str = Field(min_length=1, max_length=80)
    sections: list[ReportSection] = Field(min_length=1, max_length=20)
    findings: list[str] = Field(default_factory=list, max_length=50)
    recommendations: list[str] = Field(default_factory=list, max_length=50)
    source_lineage: list[SourceReference] = Field(min_length=1, max_length=100)


class ReportResponse(BaseModel):
    id: UUID
    alert_id: UUID
    admin_unit_id: UUID
    created_by: UUID
    published_by: UUID | None
    classification: Classification
    status: ReportStatus
    title: str
    reporting_period: str
    boundary_version: str
    sections: list[dict[str, str]]
    findings: list[str]
    recommendations: list[str]
    source_lineage: list[dict[str, object]]
    published_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
