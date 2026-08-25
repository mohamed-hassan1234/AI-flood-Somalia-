from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IndicatorCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    name: str = Field(min_length=3, max_length=180)
    domain: str = Field(min_length=2, max_length=80)
    unit: str = Field(min_length=1, max_length=80)
    value_kind: str = Field(pattern="^(observed|index|probability|count|area|currency)$")
    minimum_value: float | None = None
    maximum_value: float | None = None
    aggregation_method: str = Field(pattern="^(mean|sum|min|max|latest)$")
    version: str = Field(min_length=1, max_length=80)
    definition_source: str = Field(min_length=3, max_length=500)
    verified: bool = False

    @model_validator(mode="after")
    def valid_range(self) -> "IndicatorCreate":
        if (
            self.minimum_value is not None
            and self.maximum_value is not None
            and self.minimum_value >= self.maximum_value
        ):
            raise ValueError("Indicator minimum must be less than maximum")
        return self


class IndicatorResponse(IndicatorCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
