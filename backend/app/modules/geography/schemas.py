from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdminUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    stable_code: str
    name: str
    level: str
    parent_id: UUID | None
    boundary_version: str
    boundary_source: str
    valid_from: date
    valid_to: date | None
    aliases: list[str]


class BoundaryImportRequest(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=3, max_length=255)
    valid_from: date
    feature_collection: dict[str, object]


class BoundaryImportResponse(BaseModel):
    imported: int
    version: str


class BoundaryFeatureCollectionResponse(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict[str, object]]


class RasterGridRequest(BaseModel):
    values: list[list[float | None]] = Field(min_length=1, max_length=512)
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    boundary_version: str | None = Field(default=None, min_length=1, max_length=80)


class ZonalStatisticsResponse(BaseModel):
    admin_unit_id: UUID
    boundary_version: str
    cells_in_zone: int
    valid_cells: int
    missing_cells: int
    coverage: float
    minimum: float | None
    maximum: float | None
    mean: float | None
