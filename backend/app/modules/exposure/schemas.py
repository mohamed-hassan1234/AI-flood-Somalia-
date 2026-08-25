from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExposureCreate(BaseModel):
    alert_id: UUID
    population: float | None = Field(default=None, ge=0)
    settlements: float | None = Field(default=None, ge=0)
    cropland_hectares: float | None = Field(default=None, ge=0)
    infrastructure: dict[str, object] = Field(default_factory=dict)
    source_lineage: dict[str, object]
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def has_evidence(self) -> "ExposureCreate":
        if not self.source_lineage:
            raise ValueError("Exposure assessment requires source lineage")
        if (
            all(
                value is None
                for value in [self.population, self.settlements, self.cropland_hectares]
            )
            and not self.infrastructure
        ):
            raise ValueError("Exposure assessment requires at least one measured asset")
        return self


class ExposureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    alert_id: UUID
    admin_unit_id: UUID
    population: float | None
    settlements: float | None
    cropland_hectares: float | None
    infrastructure: dict[str, object]
    source_lineage: dict[str, object]
    confidence: float | None


class ExposureListResponse(BaseModel):
    id: UUID
    alert_id: UUID
    alert_title: str
    classification: str
    risk_domain: str
    risk_level: str
    admin_unit_id: UUID
    population: float | None
    settlements: float | None
    cropland_hectares: float | None
    infrastructure: dict[str, object]
    confidence: float | None
    lineage_available: bool
