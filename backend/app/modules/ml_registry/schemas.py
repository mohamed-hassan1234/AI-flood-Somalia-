import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import RiskDomain, RiskLevel


class SnapshotCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    content_hash: str
    target_definition: dict[str, object]
    source_versions: list[dict[str, object]] = Field(min_length=1)
    object_uri: str = Field(pattern="^s3://")
    row_count: int = Field(gt=0)

    @field_validator("content_hash")
    @classmethod
    def sha256_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        return value


class SnapshotResponse(SnapshotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class SnapshotOptionResponse(BaseModel):
    id: UUID
    name: str
    row_count: int


class FeatureVersionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    definitions: list[dict[str, object]] = Field(min_length=1)
    leakage_controls: list[str] = Field(min_length=1)


class FeatureVersionResponse(FeatureVersionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ModelVersionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    dataset_snapshot_id: UUID
    feature_version_id: UUID
    artifact_uri: str = Field(pattern="^s3://")
    metrics: dict[str, object]
    model_card: dict[str, object]


class ModelVersionResponse(ModelVersionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    state: str


class ModelOperationsResponse(BaseModel):
    id: UUID
    name: str
    version: str
    state: str
    snapshot_name: str
    snapshot_row_count: int
    feature_name: str
    feature_version: str
    metrics: dict[str, object]
    model_card: dict[str, object]
    promotion_ready: bool


class ModelTransition(BaseModel):
    target: str = Field(pattern="^(validated|production|retired)$")


class PredictionCreate(BaseModel):
    model_version_id: UUID
    admin_unit_id: UUID
    domain: RiskDomain
    target_period: str = Field(min_length=3, max_length=80)
    forecast_horizon_days: int = Field(gt=0, le=365)
    probability: float = Field(ge=0, le=1)
    uncertainty: dict[str, object]
    explanation: list[dict[str, object]] = Field(min_length=1)


class PredictionResponse(PredictionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    level: RiskLevel
    dataset_snapshot_id: UUID
    feature_version_id: UUID
