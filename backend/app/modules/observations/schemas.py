from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import Classification, DataStage


class ObservationResponse(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str
    source_classification: Classification
    admin_unit_id: UUID
    indicator_code: str
    indicator_definition_id: UUID | None
    indicator_version: str | None
    season_name: str | None
    season_version: str | None
    season_authority: str | None
    value: float | None
    value_kind: str
    unit: str
    reference_time: datetime
    retrieved_at: datetime
    stage: DataStage
    quality_flags: list[str]
    boundary_version: str


class AggregatedObservationResponse(BaseModel):
    admin_unit_id: UUID
    indicator_code: str
    reference_time: datetime
    latest_retrieved_at: datetime
    season_name: str | None
    season_version: str | None
    season_authority: str | None
    value: float | None
    unit: str
    method: str
    contributing_admin_units: int
    total_descendant_units: int
    missing_records: int
    source_ids: list[UUID]
    source_names: list[str]
    boundary_version: str
