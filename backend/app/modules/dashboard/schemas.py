from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import RiskDomain, RiskLevel


class NationalDomainSummary(BaseModel):
    domain: RiskDomain
    level: RiskLevel | None
    admin_units_evaluated: int
    target_periods: list[str]
    source_ids: list[str]
    as_of: datetime | None
    stale: bool


class NationalSummaryResponse(BaseModel):
    generated_at: datetime
    boundary_scope: str
    scope_admin_unit_id: UUID | None = None
    scope_name: str = "Somalia"
    scope_level: str = "country"
    boundary_version: str | None = None
    published_warning_count: int
    domains: list[NationalDomainSummary]


class DashboardScopeResponse(BaseModel):
    id: UUID
    name: str
    level: str
    parent_id: UUID | None
    boundary_version: str
