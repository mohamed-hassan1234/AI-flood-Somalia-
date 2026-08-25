from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SeasonCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    start: date
    end: date
    authority: str = Field(min_length=3, max_length=255)
    version: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def chronological(self) -> "SeasonCreate":
        if self.start >= self.end:
            raise ValueError("Season start must be before end")
        return self


class SeasonResponse(SeasonCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    approved: bool
    approved_by: UUID | None
    active: bool
