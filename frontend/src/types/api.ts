/**
 * Types mirroring the FastAPI contract exposed under `/api/v1`.
 *
 * Every type here corresponds to a Pydantic response model in
 * `backend/app/modules/*!/schemas.py`. Field names and enum members are the
 * wire values, not display labels — presentation lives in `lib/risk.ts`.
 *
 * These are hand-written rather than generated because the backend does not
 * currently publish a committed OpenAPI artefact for the frontend to build
 * against. If one is added, replace this module with generated output.
 */

/* ---------------------------------------------------------------- enums -- */

/** `app.core.enums.RiskLevel` */
export type RiskLevel = 'normal' | 'watch' | 'warning' | 'critical';

/** `app.core.enums.RiskDomain` */
export type RiskDomain =
  | 'drought'
  | 'river_flood'
  | 'flash_flood'
  | 'food_security_deterioration';

/** `app.core.enums.AlertStatus` */
export type AlertStatus =
  | 'draft'
  | 'in_review'
  | 'verification_required'
  | 'verified'
  | 'approved'
  | 'published'
  | 'resolved';

/** `app.core.enums.Classification` */
export type Classification = 'internal' | 'partner' | 'public';

/** `app.core.enums.DataStage` */
export type DataStage = 'raw' | 'validated' | 'normalized' | 'derived' | 'published';

/** `app.core.enums.VerificationStatus` */
export type VerificationStatus =
  | 'open'
  | 'submitted'
  | 'verified'
  | 'rejected'
  | 'more_evidence_required';

/** `app.core.enums.ActionStatus` */
export type ActionStatus =
  | 'planned'
  | 'assigned'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'cancelled';

/** `app.core.enums.ReportStatus` */
export type ReportStatus = 'draft' | 'published';

/** `app.modules.data_sources.health.HealthStatus` */
export type HealthStatus = 'fresh' | 'delayed' | 'stale' | 'failed' | 'unknown';

/** Administrative hierarchy levels accepted by `/geography/admin-units`. */
export type AdminLevel = 'country' | 'region' | 'district';

/* ------------------------------------------------------- authentication -- */

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** `/auth/me` — the authoritative capability set for the signed-in user. */
export interface Principal {
  user_id: string;
  email: string;
  display_name: string;
  capabilities: string[];
}

/**
 * Capability strings declared in `backend/app/modules/auth/roles.py`.
 * The backend remains authoritative for every decision; these exist so the UI
 * can reason about which affordances to render without stringly-typed typos.
 */
export type Capability =
  | 'users.manage'
  | 'organizations.manage'
  | 'data_sources.manage'
  | 'data_sources.read'
  | 'geography.read'
  | 'geography.manage'
  | 'indicators.manage'
  | 'indicators.read'
  | 'seasons.manage'
  | 'seasons.approve'
  | 'audit.read'
  | 'predictions.read'
  | 'predictions.generate'
  | 'alerts.create'
  | 'alerts.read'
  | 'alerts.review'
  | 'alerts.approve'
  | 'alerts.publish'
  | 'alerts.resolve'
  | 'field_tasks.create'
  | 'field_tasks.read'
  | 'field_reports.submit'
  | 'field_reports.verify'
  | 'exposure.calculate'
  | 'exposure.read'
  | 'early_actions.playbooks.manage'
  | 'early_actions.create'
  | 'early_actions.read'
  | 'early_actions.assign'
  | 'early_actions.update'
  | 'early_actions.complete'
  | 'early_actions.approve'
  | 'notifications.send'
  | 'notifications.read'
  | 'notifications.manage'
  | 'notifications.escalate'
  | 'models.train'
  | 'models.read'
  | 'models.evaluate'
  | 'models.promote'
  | 'models.rollback'
  | 'models.infer'
  | 'outcomes.manage'
  | 'scenarios.run'
  | 'scenarios.read'
  | 'reports.generate'
  | 'reports.publish'
  | 'reports.read';

/* ------------------------------------------------------------ dashboard -- */

export interface NationalDomainSummary {
  domain: RiskDomain;
  level: RiskLevel | null;
  admin_units_evaluated: number;
  target_periods: string[];
  source_ids: string[];
  as_of: string | null;
  stale: boolean;
}

export interface NationalSummary {
  generated_at: string;
  boundary_scope: string;
  scope_admin_unit_id: string | null;
  scope_name: string;
  scope_level: string;
  boundary_version: string | null;
  published_warning_count: number;
  domains: NationalDomainSummary[];
}

export interface DashboardScope {
  id: string;
  name: string;
  level: string;
  parent_id: string | null;
  boundary_version: string;
}

/* --------------------------------------------------------- risk signals -- */

/**
 * A single model-attributed reason the risk was raised. The backend types this
 * as an open `dict[str, object]`, so every field is optional and the UI must
 * degrade gracefully. Field names follow the Phase 03 operational intelligence
 * contract (`docs/contracts/operational-intelligence-contract.md`).
 */
export interface RiskDriver {
  feature?: string;
  observed_value?: number | string | null;
  training_median?: number | string | null;
  probability_change_if_replaced_by_training_median?: number | null;
  reason_code?: string;
  indicator?: string;
  source_id?: string;
  [key: string]: unknown;
}

/** Open provenance envelope attached to every risk signal. */
export interface RiskProvenance {
  label?: string;
  automatic_warning_publication?: boolean;
  model_id?: string;
  model_version?: string;
  dataset_checksum?: string;
  pipeline_version?: string;
  data_quality?: string;
  freshness?: string;
  suppression_reason?: string | null;
  limitations?: string[];
  [key: string]: unknown;
}

export interface RiskSignal {
  id: string;
  domain: RiskDomain;
  admin_unit_id: string;
  level: RiskLevel;
  /** Model probability in [0,1], or null when input quality is insufficient. */
  score: number | null;
  confidence: number | null;
  drivers: RiskDriver[];
  provenance: RiskProvenance;
  target_period: string;
  created_at: string;
}

/* ---------------------------------------------------------------- alerts -- */

export interface Alert {
  id: string;
  signal_id: string;
  status: AlertStatus;
  classification: Classification;
  title: string;
  summary: string;
}

export interface AlertListItem extends Alert {
  admin_unit_id: string;
  risk_domain: RiskDomain;
  risk_level: RiskLevel;
  target_period: string;
  created_at: string;
  published_at: string | null;
}

export interface AlertTransitionRequest {
  target: AlertStatus;
}

/* ------------------------------------------------------------- geography -- */

export interface AdminUnit {
  id: string;
  stable_code: string;
  name: string;
  level: string;
  parent_id: string | null;
  boundary_version: string;
  boundary_source: string;
  valid_from: string;
  valid_to: string | null;
  aliases: string[];
}

export interface BoundaryFeatureProperties {
  name?: string;
  level?: string;
  stable_code?: string;
  boundary_version?: string;
  boundary_source?: string;
  [key: string]: unknown;
}

export interface BoundaryFeature {
  type: 'Feature';
  id: string;
  geometry: unknown;
  properties: BoundaryFeatureProperties;
}

export interface BoundaryFeatureCollection {
  type: 'FeatureCollection';
  features: BoundaryFeature[];
}

/* ---------------------------------------------------------- data sources -- */

export interface DataSource {
  id: string;
  name: string;
  domain: string;
  owner: string | null;
  license: string | null;
  access_method: 'api' | 'file' | 'manual' | 'object_storage';
  /** Source-specific cadence. IPC and MODIS are not daily — never assume 24h. */
  expected_frequency_minutes: number | null;
  geographic_resolution: string | null;
  classification: Classification;
  verified: boolean;
  enabled: boolean;
}

export interface DataSourceHealth {
  source_id: string;
  status: HealthStatus;
  last_success: string | null;
  last_run_status: string | null;
  rows_received: number;
  rows_quarantined: number;
}

/* -------------------------------------------------------------- exposure -- */

export interface ExposureListItem {
  id: string;
  alert_id: string;
  alert_title: string;
  classification: string;
  risk_domain: string;
  risk_level: string;
  admin_unit_id: string;
  population: number | null;
  settlements: number | null;
  cropland_hectares: number | null;
  infrastructure: Record<string, unknown>;
  confidence: number | null;
  lineage_available: boolean;
}

export interface ExposureAssessment {
  id: string;
  alert_id: string;
  admin_unit_id: string;
  population: number | null;
  settlements: number | null;
  cropland_hectares: number | null;
  infrastructure: Record<string, unknown>;
  source_lineage: Record<string, unknown>;
  confidence: number | null;
}

/* --------------------------------------------------------- early actions -- */

export interface ActionItemListItem {
  id: string;
  plan_id: string;
  plan_title: string;
  alert_title: string;
  risk_domain: RiskDomain;
  classification: string;
  admin_unit_id: string;
  owner_id: string | null;
  owner_organization_id: string;
  description: string;
  due_at: string;
  status: ActionStatus;
  blockers: string[];
  evidence_count: number;
}

/* ---------------------------------------------------------- observations -- */

export interface Observation {
  id: string;
  source_id: string;
  source_name: string;
  source_classification: Classification;
  admin_unit_id: string;
  indicator_code: string;
  indicator_definition_id: string | null;
  indicator_version: string | null;
  season_name: string | null;
  season_version: string | null;
  season_authority: string | null;
  value: number | null;
  value_kind: string;
  unit: string;
  reference_time: string;
  retrieved_at: string;
  stage: DataStage;
  quality_flags: string[];
  boundary_version: string;
}

export interface AggregatedObservation {
  admin_unit_id: string;
  indicator_code: string;
  reference_time: string;
  latest_retrieved_at: string;
  season_name: string | null;
  season_version: string | null;
  season_authority: string | null;
  value: number | null;
  unit: string;
  method: string;
  contributing_admin_units: number;
  total_descendant_units: number;
  missing_records: number;
  source_ids: string[];
  source_names: string[];
  boundary_version: string;
}

/* --------------------------------------------------- field verification -- */

export interface VerificationTaskListItem {
  id: string;
  alert_id: string;
  alert_title: string;
  classification: Classification;
  admin_unit_id: string;
  risk_domain: RiskDomain;
  assigned_to: string | null;
  due_at: string;
  priority: 'low' | 'normal' | 'high' | 'critical';
  status: VerificationStatus;
}

/* --------------------------------------------------------------- reports -- */

export interface ReportSection {
  heading: string;
  body: string;
}

export interface GovernedReport {
  id: string;
  alert_id: string;
  admin_unit_id: string;
  created_by: string;
  published_by: string | null;
  classification: Classification;
  status: ReportStatus;
  title: string;
  reporting_period: string;
  boundary_version: string;
  sections: ReportSection[];
  findings: string[];
  recommendations: string[];
  source_lineage: Array<Record<string, unknown>>;
  published_at: string | null;
  created_at: string;
}

export interface PublicWarning {
  id: string;
  title: string;
  summary: string;
  risk_domain: RiskDomain;
  risk_level: RiskLevel;
  target_period: string;
  admin_unit_id: string;
  admin_unit_name: string;
  boundary_version: string;
  published_at: string;
}

/* -------------------------------------------------------- administration -- */

export interface Organization {
  id: string;
  name: string;
  organization_type: string;
}

export interface UserAccount {
  id: string;
  email: string;
  display_name: string;
  active: boolean;
}

export interface RoleDefinition {
  id: string;
  name: string;
  capabilities: string[];
}

/* -------------------------------------------------------- ML / platform -- */

export interface ModelOperations {
  id: string;
  name: string;
  version: string;
  state: string;
  snapshot_name: string;
  snapshot_row_count: number;
  feature_name: string;
  feature_version: string;
  metrics: Record<string, unknown>;
  model_card: Record<string, unknown>;
  promotion_ready: boolean;
}

/** `/meta` — platform invariants the UI must respect and surface. */
export interface PlatformMeta {
  risk_domains: RiskDomain[];
  risk_levels: RiskLevel[];
  alert_statuses: AlertStatus[];
  classifications: Classification[];
  /** Always false: this platform does not emit official IPC classifications. */
  official_ipc_output: boolean;
  /** Always false: no warning is published without human authorisation. */
  automatic_warning_publication: boolean;
}
