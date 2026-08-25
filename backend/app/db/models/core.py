from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    ActionStatus,
    AlertStatus,
    Classification,
    DataStage,
    DeliveryStatus,
    ReportStatus,
    RiskDomain,
    RiskLevel,
    VerificationStatus,
)
from app.db.base import Base, IdTimestampMixin


class Organization(IdTimestampMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(180), unique=True)
    organization_type: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(IdTimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(IdTimestampMixin, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(255))
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)


class Membership(IdTimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "role_id", name="uq_membership_assignment"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"))
    classification_ceiling: Mapped[Classification] = mapped_column(Enum(Classification))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class GeographicScope(IdTimestampMixin, Base):
    __tablename__ = "geographic_scopes"
    membership_id: Mapped[UUID] = mapped_column(ForeignKey("memberships.id"), index=True)
    admin_unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("admin_units.id"))
    national: Mapped[bool] = mapped_column(Boolean, default=False)


class RefreshToken(IdTimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminUnit(IdTimestampMixin, Base):
    __tablename__ = "admin_units"
    stable_code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(180))
    level: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("admin_units.id"))
    boundary_version: Mapped[str] = mapped_column(String(80))
    boundary_source: Mapped[str] = mapped_column(String(255))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    geometry: Mapped[dict[str, object] | None] = mapped_column(JSON)


class BoundaryRevision(IdTimestampMixin, Base):
    __tablename__ = "boundary_revisions"
    __table_args__ = (
        UniqueConstraint("admin_unit_id", "version", name="uq_boundary_revision_unit_version"),
        UniqueConstraint(
            "admin_unit_id", "valid_from", name="uq_boundary_revision_unit_effective_date"
        ),
    )
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"), index=True)
    parent_admin_unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("admin_units.id"))
    version: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(255))
    valid_from: Mapped[date] = mapped_column(Date, index=True)
    valid_to: Mapped[date | None] = mapped_column(Date)
    geometry: Mapped[dict[str, object]] = mapped_column(JSON)


class DataSource(IdTimestampMixin, Base):
    __tablename__ = "data_sources"
    name: Mapped[str] = mapped_column(String(180), unique=True)
    domain: Mapped[str] = mapped_column(String(80))
    license: Mapped[str | None] = mapped_column(String(255))
    attribution: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(180))
    terms_url: Mapped[str | None] = mapped_column(String(1024))
    expected_frequency_minutes: Mapped[int | None] = mapped_column()
    geographic_resolution: Mapped[str | None] = mapped_column(String(120))
    historical_start: Mapped[date | None] = mapped_column(Date)
    schedule: Mapped[str | None] = mapped_column(String(120))
    access_method: Mapped[str] = mapped_column(String(50))
    classification: Mapped[Classification] = mapped_column(Enum(Classification))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class IndicatorDefinition(IdTimestampMixin, Base):
    __tablename__ = "indicator_definitions"
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    domain: Mapped[str] = mapped_column(String(80), index=True)
    unit: Mapped[str] = mapped_column(String(80))
    value_kind: Mapped[str] = mapped_column(String(40))
    minimum_value: Mapped[float | None] = mapped_column(Float)
    maximum_value: Mapped[float | None] = mapped_column(Float)
    aggregation_method: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(80))
    definition_source: Mapped[str] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class SeasonDefinition(IdTimestampMixin, Base):
    __tablename__ = "season_definitions"
    name: Mapped[str] = mapped_column(String(100), index=True)
    start: Mapped[date] = mapped_column(Date, index=True)
    end: Mapped[date] = mapped_column(Date, index=True)
    authority: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(80))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class IngestionRun(IdTimestampMixin, Base):
    __tablename__ = "ingestion_runs"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_received: Mapped[int] = mapped_column(default=0)
    rows_accepted: Mapped[int] = mapped_column(default=0)
    rows_quarantined: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)


class QuarantineRecord(IdTimestampMixin, Base):
    __tablename__ = "quarantine_records"
    ingestion_run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    source_row: Mapped[int] = mapped_column()
    reason_code: Mapped[str] = mapped_column(String(80), index=True)
    safe_payload: Mapped[dict[str, object]] = mapped_column(JSON)


class Observation(IdTimestampMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", name="uq_observation_source_record"),
    )
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"))
    source_record_id: Mapped[str] = mapped_column(String(255))
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"))
    indicator_code: Mapped[str] = mapped_column(String(120), index=True)
    indicator_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("indicator_definitions.id")
    )
    value: Mapped[float | None] = mapped_column(Float)
    value_kind: Mapped[str] = mapped_column(String(20), default="observed")
    unit: Mapped[str] = mapped_column(String(40))
    reference_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stage: Mapped[DataStage] = mapped_column(Enum(DataStage))
    quality_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    boundary_version: Mapped[str] = mapped_column(String(80))


class RiskSignal(IdTimestampMixin, Base):
    __tablename__ = "risk_signals"
    domain: Mapped[RiskDomain] = mapped_column(Enum(RiskDomain), index=True)
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"))
    level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel))
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    drivers: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON)
    target_period: Mapped[str] = mapped_column(String(80))


class Alert(IdTimestampMixin, Base):
    __tablename__ = "alerts"
    signal_id: Mapped[UUID] = mapped_column(ForeignKey("risk_signals.id"))
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.DRAFT)
    classification: Mapped[Classification] = mapped_column(
        Enum(Classification), default=Classification.INTERNAL
    )
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationTask(IdTimestampMixin, Base):
    __tablename__ = "verification_tasks"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"))
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str] = mapped_column(String(20))
    status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus))
    form_schema: Mapped[dict[str, object]] = mapped_column(JSON)


class FieldReport(IdTimestampMixin, Base):
    __tablename__ = "field_reports"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("verification_tasks.id"), index=True)
    reporter_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    answers: Mapped[dict[str, object]] = mapped_column(JSON)
    evidence_objects: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)


class ExposureAssessment(IdTimestampMixin, Base):
    __tablename__ = "exposure_assessments"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"))
    population: Mapped[float | None] = mapped_column(Float)
    settlements: Mapped[float | None] = mapped_column(Float)
    cropland_hectares: Mapped[float | None] = mapped_column(Float)
    infrastructure: Mapped[dict[str, object]] = mapped_column(JSON)
    source_lineage: Mapped[dict[str, object]] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float)


class Playbook(IdTimestampMixin, Base):
    __tablename__ = "playbooks"
    name: Mapped[str] = mapped_column(String(180), unique=True)
    risk_domain: Mapped[RiskDomain] = mapped_column(Enum(RiskDomain))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[str] = mapped_column(String(40))
    steps: Mapped[list[dict[str, object]]] = mapped_column(JSON)


class ActionPlan(IdTimestampMixin, Base):
    __tablename__ = "action_plans"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    playbook_id: Mapped[UUID] = mapped_column(ForeignKey("playbooks.id"))
    owner_organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    title: Mapped[str] = mapped_column(String(255))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class ActionItem(IdTimestampMixin, Base):
    __tablename__ = "action_items"
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("action_plans.id"), index=True)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    owner_organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    description: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus))
    blockers: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_objects: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


class NotificationDelivery(IdTimestampMixin, Base):
    __tablename__ = "notification_deliveries"
    event_key: Mapped[str] = mapped_column(String(255))
    recipient_key: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(30))
    alert_id: Mapped[UUID | None] = mapped_column(ForeignKey("alerts.id"), index=True)
    action_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("action_items.id"), index=True)
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus))
    attempt_count: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(default=0)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "event_key", "recipient_key", "channel", name="uq_notification_deduplication"
        ),
    )


class DatasetSnapshot(IdTimestampMixin, Base):
    __tablename__ = "dataset_snapshots"
    name: Mapped[str] = mapped_column(String(180))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    target_definition: Mapped[dict[str, object]] = mapped_column(JSON)
    source_versions: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    object_uri: Mapped[str] = mapped_column(String(1024))
    row_count: Mapped[int] = mapped_column()


class FeatureVersion(IdTimestampMixin, Base):
    __tablename__ = "feature_versions"
    name: Mapped[str] = mapped_column(String(180))
    version: Mapped[str] = mapped_column(String(80), unique=True)
    definitions: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    leakage_controls: Mapped[list[str]] = mapped_column(JSON)


class ModelVersion(IdTimestampMixin, Base):
    __tablename__ = "model_versions"
    name: Mapped[str] = mapped_column(String(180))
    version: Mapped[str] = mapped_column(String(80), unique=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    dataset_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_snapshots.id"))
    feature_version_id: Mapped[UUID] = mapped_column(ForeignKey("feature_versions.id"))
    artifact_uri: Mapped[str] = mapped_column(String(1024))
    metrics: Mapped[dict[str, object]] = mapped_column(JSON)
    model_card: Mapped[dict[str, object]] = mapped_column(JSON)


class Prediction(IdTimestampMixin, Base):
    __tablename__ = "predictions"
    model_version_id: Mapped[UUID] = mapped_column(ForeignKey("model_versions.id"), index=True)
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"))
    domain: Mapped[RiskDomain] = mapped_column(Enum(RiskDomain))
    target_period: Mapped[str] = mapped_column(String(80))
    forecast_horizon_days: Mapped[int] = mapped_column()
    probability: Mapped[float] = mapped_column(Float)
    level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel))
    uncertainty: Mapped[dict[str, object]] = mapped_column(JSON)
    explanation: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    dataset_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_snapshots.id"))
    feature_version_id: Mapped[UUID] = mapped_column(ForeignKey("feature_versions.id"))


class Outcome(IdTimestampMixin, Base):
    __tablename__ = "outcomes"
    prediction_id: Mapped[UUID] = mapped_column(ForeignKey("predictions.id"), unique=True)
    observed: Mapped[bool] = mapped_column(Boolean)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_lineage: Mapped[dict[str, object]] = mapped_column(JSON)
    analyst_override: Mapped[dict[str, object] | None] = mapped_column(JSON)


class Scenario(IdTimestampMixin, Base):
    __tablename__ = "scenarios"
    name: Mapped[str] = mapped_column(String(180))
    baseline_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_snapshots.id"))
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"), index=True)
    domain: Mapped[RiskDomain] = mapped_column(Enum(RiskDomain))
    modifications: Mapped[dict[str, object]] = mapped_column(JSON)
    result: Mapped[dict[str, object]] = mapped_column(JSON)
    label: Mapped[str] = mapped_column(String(20), default="SIMULATION")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class Report(IdTimestampMixin, Base):
    __tablename__ = "reports"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    admin_unit_id: Mapped[UUID] = mapped_column(ForeignKey("admin_units.id"), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    published_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    classification: Mapped[Classification] = mapped_column(Enum(Classification), index=True)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), index=True)
    title: Mapped[str] = mapped_column(String(255))
    reporting_period: Mapped[str] = mapped_column(String(80))
    boundary_version: Mapped[str] = mapped_column(String(80))
    sections: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    findings: Mapped[list[str]] = mapped_column(JSON)
    recommendations: Mapped[list[str]] = mapped_column(JSON)
    source_lineage: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(160), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID] = mapped_column()
    details: Mapped[dict[str, object]] = mapped_column(JSON)
