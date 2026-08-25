from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import Classification
from app.modules.data_sources.health import HealthStatus


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    domain: str = Field(min_length=2, max_length=80)
    owner: str | None = Field(default=None, max_length=180)
    license: str | None = Field(default=None, max_length=255)
    terms_url: str | None = Field(default=None, max_length=1024)
    attribution: str | None = Field(default=None, max_length=5000)
    access_method: str = Field(pattern="^(api|file|manual|object_storage)$")
    expected_frequency_minutes: int | None = Field(default=None, gt=0)
    geographic_resolution: str | None = Field(default=None, max_length=120)
    historical_start: date | None = None
    schedule: str | None = Field(default=None, max_length=120)
    classification: Classification = Classification.INTERNAL
    verified: bool = False

    @model_validator(mode="after")
    def verified_metadata_is_complete(self) -> "DataSourceCreate":
        if self.verified and not all(
            [
                self.owner,
                self.license,
                self.terms_url,
                self.attribution,
                self.expected_frequency_minutes,
                self.geographic_resolution,
            ]
        ):
            raise ValueError(
                "Verified sources require owner, license, terms, attribution, frequency, and resolution"
            )
        return self


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    domain: str
    owner: str | None
    license: str | None
    access_method: str
    expected_frequency_minutes: int | None
    geographic_resolution: str | None
    classification: Classification
    verified: bool
    enabled: bool


class DataSourceHealthResponse(BaseModel):
    source_id: UUID
    status: HealthStatus
    last_success: datetime | None
    last_run_status: str | None
    rows_received: int
    rows_quarantined: int
