from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RiskDomain, RiskLevel


class RiskEvaluationRequest(BaseModel):
    admin_unit_id: UUID
    target_period: str = Field(min_length=4, max_length=80)
    evaluation_at: datetime | None = None
    lookback_days: int = Field(default=90, ge=1, le=365)


class RiskSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    domain: RiskDomain
    admin_unit_id: UUID
    level: RiskLevel
    score: float | None
    confidence: float | None
    drivers: list[dict[str, object]]
    provenance: dict[str, object]
    target_period: str
    created_at: datetime
