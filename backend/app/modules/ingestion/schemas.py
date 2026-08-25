from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_received: int
    rows_accepted: int
    rows_quarantined: int


class ObjectStorageImportRequest(BaseModel):
    object_key: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9/_.-]{2,1023}\.csv$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
