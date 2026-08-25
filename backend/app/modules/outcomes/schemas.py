from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutcomeCreate(BaseModel):
    prediction_id: UUID
    observed: bool
    observed_at: datetime
    source_lineage: dict[str, object]
    analyst_override: dict[str, object] | None = None


class OutcomeResponse(OutcomeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class OutcomeMetricsResponse(BaseModel):
    model_version_id: UUID
    sample_count: int
    precision: float
    recall: float
    f1: float
    macro_f1: float
    pr_auc: float | None
    roc_auc: float | None
    brier: float
    calibration_error: float
    high_risk_recall: float
    useful_lead_time_days: float | None
    false_positives: int = Field(ge=0)
    missed_events: int = Field(ge=0)
    strata: list["OutcomeMetricStratum"]


class OutcomeMetricStratum(BaseModel):
    dimension: str
    value: str
    sample_count: int = Field(gt=0)
    precision: float
    recall: float
    f1: float
    macro_f1: float
    pr_auc: float | None
    roc_auc: float | None
    brier: float
    calibration_error: float
    high_risk_recall: float
    useful_lead_time_days: float | None
