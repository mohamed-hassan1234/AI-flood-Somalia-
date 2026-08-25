from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import RiskDomain

ALLOWED_MODIFICATIONS = {"rainfall_reduction", "river_rise", "price_increase", "compound_shock"}


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    baseline_snapshot_id: UUID
    admin_unit_id: UUID
    domain: RiskDomain
    baseline_score: float = Field(ge=0, le=1)
    modifications: dict[str, float]

    @field_validator("modifications")
    @classmethod
    def supported_modifications(cls, value: dict[str, float]) -> dict[str, float]:
        if not value or not set(value).issubset(ALLOWED_MODIFICATIONS):
            raise ValueError("Scenario contains unsupported or empty modifications")
        if any(not -1 <= amount <= 1 for amount in value.values()):
            raise ValueError("Scenario modifications must be between -1 and 1")
        return value


class ScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    baseline_snapshot_id: UUID
    admin_unit_id: UUID
    domain: RiskDomain
    modifications: dict[str, object]
    result: dict[str, object]
    label: str
    created_by: UUID


class ScenarioListResponse(BaseModel):
    id: UUID
    name: str
    snapshot_name: str
    admin_unit_id: UUID
    admin_unit_name: str
    domain: RiskDomain
    modifications: dict[str, object]
    result: dict[str, object]
    label: str
    created_at: datetime
