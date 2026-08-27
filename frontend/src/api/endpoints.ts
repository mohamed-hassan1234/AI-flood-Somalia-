/**
 * Typed bindings for every API route this application consumes.
 *
 * One function per endpoint, named for the operation rather than the HTTP
 * verb. Routes here correspond exactly to the FastAPI surface generated from
 * `backend/app/api/router.py`; nothing is invented, and endpoints the backend
 * does not expose are absent by design.
 */

import { apiGet, apiPost, apiRequest } from './client';
import type {
  ActionItemListItem,
  AdminLevel,
  Alert,
  AlertListItem,
  AlertStatus,
  AdminUnit,
  AggregatedObservation,
  BoundaryFeatureCollection,
  DashboardScope,
  DataSource,
  DataSourceHealth,
  ExposureListItem,
  GovernedReport,
  ModelOperations,
  NationalSummary,
  Observation,
  Organization,
  PlatformMeta,
  Principal,
  PublicWarning,
  RiskDomain,
  RiskSignal,
  RoleDefinition,
  TokenResponse,
  UserAccount,
  VerificationTaskListItem,
} from '../types/api';

/* ------------------------------------------------------------------ auth -- */

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    anonymous: true,
  });
}

export function fetchPrincipal(signal?: AbortSignal): Promise<Principal> {
  return apiGet<Principal>('/auth/me', undefined, signal);
}

/* -------------------------------------------------------------- platform -- */

export function fetchPlatformMeta(signal?: AbortSignal): Promise<PlatformMeta> {
  return apiGet<PlatformMeta>('/meta', undefined, signal);
}

/* ------------------------------------------------------------- dashboard -- */

export function fetchDashboardScopes(signal?: AbortSignal): Promise<DashboardScope[]> {
  return apiGet<DashboardScope[]>('/dashboard/scopes', undefined, signal);
}

export function fetchNationalSummary(
  adminUnitId?: string,
  signal?: AbortSignal,
): Promise<NationalSummary> {
  return apiGet<NationalSummary>(
    '/dashboard/national-summary',
    { admin_unit_id: adminUnitId },
    signal,
  );
}

/* ----------------------------------------------------------- risk signals -- */

export interface RiskSignalQuery {
  domain?: RiskDomain;
  admin_unit_id?: string;
  /** Backend accepts 1–1000; defaults to 200 server-side. */
  limit?: number;
}

export function fetchRiskSignals(
  query: RiskSignalQuery = {},
  signal?: AbortSignal,
): Promise<RiskSignal[]> {
  return apiGet<RiskSignal[]>('/risks', { ...query }, signal);
}

/* ------------------------------------------------------------------ alerts -- */

/**
 * The backend exposes no server-side filtering on `/alerts`; it returns every
 * alert the principal may read, newest first. Filtering and pagination are
 * therefore applied client-side in the Warning Center.
 */
export function fetchAlerts(signal?: AbortSignal): Promise<AlertListItem[]> {
  return apiGet<AlertListItem[]>('/alerts', undefined, signal);
}

export function fetchAlert(alertId: string, signal?: AbortSignal): Promise<Alert> {
  return apiGet<Alert>(`/alerts/${alertId}`, undefined, signal);
}

export function fetchPartnerWarnings(signal?: AbortSignal): Promise<AlertListItem[]> {
  return apiGet<AlertListItem[]>('/alerts/partner-warnings', undefined, signal);
}

/**
 * Advances an alert through the governed workflow. The backend validates both
 * the transition legality and the caller's capability; a rejected transition
 * surfaces as an `ApiError` with kind `conflict` or `forbidden`.
 */
export function transitionAlert(alertId: string, target: AlertStatus): Promise<Alert> {
  return apiPost<Alert>(`/alerts/${alertId}/transitions`, { target });
}

/* --------------------------------------------------------------- geography -- */

export function fetchAdminUnits(
  level?: AdminLevel,
  signal?: AbortSignal,
): Promise<AdminUnit[]> {
  return apiGet<AdminUnit[]>('/geography/admin-units', { level }, signal);
}

export function fetchAdminUnit(adminUnitId: string, signal?: AbortSignal): Promise<AdminUnit> {
  return apiGet<AdminUnit>(`/geography/admin-units/${adminUnitId}`, undefined, signal);
}

export function fetchBoundaries(
  boundaryVersion?: string,
  signal?: AbortSignal,
): Promise<BoundaryFeatureCollection> {
  return apiGet<BoundaryFeatureCollection>(
    '/geography/boundaries',
    { boundary_version: boundaryVersion },
    signal,
  );
}

/* ------------------------------------------------------------ data sources -- */

export function fetchDataSources(signal?: AbortSignal): Promise<DataSource[]> {
  return apiGet<DataSource[]>('/data-sources', undefined, signal);
}

export function fetchDataSourceHealth(
  sourceId: string,
  signal?: AbortSignal,
): Promise<DataSourceHealth> {
  return apiGet<DataSourceHealth>(`/data-sources/${sourceId}/health`, undefined, signal);
}

/* ---------------------------------------------------------------- exposure -- */

export function fetchExposureAssessments(signal?: AbortSignal): Promise<ExposureListItem[]> {
  return apiGet<ExposureListItem[]>('/exposure/assessments', undefined, signal);
}

/* ----------------------------------------------------------- early actions -- */

export function fetchActionItems(signal?: AbortSignal): Promise<ActionItemListItem[]> {
  return apiGet<ActionItemListItem[]>('/early-actions/items', undefined, signal);
}

/* ------------------------------------------------------------ observations -- */

export interface ObservationQuery {
  admin_unit_id: string;
  indicator_code?: string;
  /** ISO-8601 instants. */
  start?: string;
  end?: string;
  limit?: number;
}

export function fetchObservations(
  query: ObservationQuery,
  signal?: AbortSignal,
): Promise<Observation[]> {
  return apiGet<Observation[]>('/observations', { ...query }, signal);
}

export function fetchAggregatedObservations(
  adminUnitId: string,
  indicatorCode?: string,
  signal?: AbortSignal,
): Promise<AggregatedObservation[]> {
  return apiGet<AggregatedObservation[]>(
    '/observations/aggregate',
    { admin_unit_id: adminUnitId, indicator_code: indicatorCode },
    signal,
  );
}

/* ------------------------------------------------------ field verification -- */

export function fetchVerificationTasks(
  signal?: AbortSignal,
): Promise<VerificationTaskListItem[]> {
  return apiGet<VerificationTaskListItem[]>('/field-verification/tasks', undefined, signal);
}

/* ----------------------------------------------------------------- reports -- */

export function fetchReports(signal?: AbortSignal): Promise<GovernedReport[]> {
  return apiGet<GovernedReport[]>('/reports', undefined, signal);
}

export function fetchReport(reportId: string, signal?: AbortSignal): Promise<GovernedReport> {
  return apiGet<GovernedReport>(`/reports/${reportId}`, undefined, signal);
}

export function fetchPublicWarnings(signal?: AbortSignal): Promise<PublicWarning[]> {
  return apiGet<PublicWarning[]>('/public/warnings', undefined, signal);
}

/* --------------------------------------------------------------------- ML -- */

export function fetchModelOperations(signal?: AbortSignal): Promise<ModelOperations[]> {
  return apiGet<ModelOperations[]>('/ml/operations', undefined, signal);
}

/* --------------------------------------------------------- administration -- */

export function fetchOrganizations(signal?: AbortSignal): Promise<Organization[]> {
  return apiGet<Organization[]>('/administration/organizations', undefined, signal);
}

export function fetchUsers(signal?: AbortSignal): Promise<UserAccount[]> {
  return apiGet<UserAccount[]>('/administration/users', undefined, signal);
}

export function fetchRoles(signal?: AbortSignal): Promise<RoleDefinition[]> {
  return apiGet<RoleDefinition[]>('/administration/roles', undefined, signal);
}
