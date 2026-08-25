from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import RiskDomain, RiskLevel


class PublicWarningResponse(BaseModel):
    id: UUID
    title: str
    summary: str
    risk_domain: RiskDomain
    risk_level: RiskLevel
    target_period: str
    admin_unit_id: UUID
    admin_unit_name: str
    boundary_version: str
    published_at: datetime


class PublicReportResponse(BaseModel):
    id: UUID
    title: str
    reporting_period: str
    admin_unit_id: UUID
    admin_unit_name: str
    boundary_version: str
    sections: list[dict[str, str]]
    findings: list[str]
    recommendations: list[str]
    published_at: datetime
