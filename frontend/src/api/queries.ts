/**
 * TanStack Query bindings: one hook per read, plus a single key factory.
 *
 * Query keys are centralised so invalidation after a workflow mutation cannot
 * drift from the keys the reads actually use — a class of bug that shows up in
 * this product as a stale warning status after an approval.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { ApiError } from './client';
import * as api from './endpoints';
import type {
  ActionItemListItem,
  AdminLevel,
  Alert,
  AlertListItem,
  AlertStatus,
  AdminUnit,
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
  RiskSignal,
  RoleDefinition,
  UserAccount,
  VerificationTaskListItem,
} from '../types/api';

/* ------------------------------------------------------------ key factory -- */

export const queryKeys = {
  principal: ['principal'] as const,
  meta: ['meta'] as const,

  dashboardScopes: ['dashboard', 'scopes'] as const,
  nationalSummary: (scopeId?: string) => ['dashboard', 'national-summary', scopeId ?? null] as const,

  riskSignals: (query: api.RiskSignalQuery = {}) =>
    ['risks', query.domain ?? null, query.admin_unit_id ?? null, query.limit ?? null] as const,

  alerts: ['alerts'] as const,
  alert: (id: string) => ['alerts', id] as const,

  adminUnits: (level?: AdminLevel) => ['geography', 'admin-units', level ?? null] as const,
  boundaries: (version?: string) => ['geography', 'boundaries', version ?? null] as const,

  dataSources: ['data-sources'] as const,
  dataSourceHealth: (id: string) => ['data-sources', id, 'health'] as const,

  exposure: ['exposure', 'assessments'] as const,
  actionItems: ['early-actions', 'items'] as const,
  verificationTasks: ['field-verification', 'tasks'] as const,

  observations: (adminUnitId: string, indicator?: string, start?: string, end?: string) =>
    ['observations', adminUnitId, indicator ?? null, start ?? null, end ?? null] as const,

  reports: ['reports'] as const,
  modelOperations: ['ml', 'operations'] as const,

  organizations: ['administration', 'organizations'] as const,
  users: ['administration', 'users'] as const,
  roles: ['administration', 'roles'] as const,
};

/* ------------------------------------------------------------ retry policy -- */

/**
 * Never retry an access boundary or a validation failure — retrying a 403
 * cannot succeed and only delays an honest "not authorised" screen. Transient
 * classes get two extra attempts.
 *
 * Installed once on the QueryClient (`AppProviders.createQueryClient`) rather
 * than repeated on each hook, so a differently-configured client — a test
 * client that disables retries, for instance — actually takes effect.
 */
export function shouldRetry(failureCount: number, error: ApiError): boolean {
  // Typed as ApiError rather than unknown so TanStack infers TError from it —
  // an `unknown` parameter here silently widens every hook's error type and
  // forces a cast at each call site that wants to branch on `error.kind`.
  if (error instanceof ApiError && !error.retryable) return false;
  return failureCount < 2;
}

/* -------------------------------------------------------------------- auth -- */

export function usePrincipal(enabled = true): UseQueryResult<Principal, ApiError> {
  return useQuery({
    queryKey: queryKeys.principal,
    queryFn: ({ signal }) => api.fetchPrincipal(signal),
    enabled,
    // The capability set changes only on an administrative action, so a long
    // stale window avoids re-fetching it on every navigation.
    staleTime: 5 * 60_000,
  });
}

export function usePlatformMeta(enabled = true): UseQueryResult<PlatformMeta, ApiError> {
  return useQuery({
    queryKey: queryKeys.meta,
    queryFn: ({ signal }) => api.fetchPlatformMeta(signal),
    enabled,
    staleTime: 30 * 60_000,
  });
}

/* --------------------------------------------------------------- dashboard -- */

export function useDashboardScopes(enabled = true): UseQueryResult<DashboardScope[], ApiError> {
  return useQuery({
    queryKey: queryKeys.dashboardScopes,
    queryFn: ({ signal }) => api.fetchDashboardScopes(signal),
    enabled,
    staleTime: 10 * 60_000,
  });
}

export function useNationalSummary(
  scopeId?: string,
  enabled = true,
): UseQueryResult<NationalSummary, ApiError> {
  return useQuery({
    queryKey: queryKeys.nationalSummary(scopeId),
    queryFn: ({ signal }) => api.fetchNationalSummary(scopeId, signal),
    enabled,
    staleTime: 60_000,
  });
}

/* ------------------------------------------------------------ risk signals -- */

export function useRiskSignals(
  query: api.RiskSignalQuery = {},
  enabled = true,
): UseQueryResult<RiskSignal[], ApiError> {
  return useQuery({
    queryKey: queryKeys.riskSignals(query),
    queryFn: ({ signal }) => api.fetchRiskSignals(query, signal),
    enabled,
    staleTime: 60_000,
  });
}

/* ------------------------------------------------------------------ alerts -- */

export function useAlerts(enabled = true): UseQueryResult<AlertListItem[], ApiError> {
  return useQuery({
    queryKey: queryKeys.alerts,
    queryFn: ({ signal }) => api.fetchAlerts(signal),
    enabled,
    staleTime: 30_000,
  });
}

export function useAlert(id: string, enabled = true): UseQueryResult<Alert, ApiError> {
  return useQuery({
    queryKey: queryKeys.alert(id),
    queryFn: ({ signal }) => api.fetchAlert(id, signal),
    enabled: enabled && Boolean(id),
  });
}

export interface TransitionVariables {
  alertId: string;
  target: AlertStatus;
}

/**
 * Applies a governed workflow transition and refreshes every view whose
 * content depends on alert state — the warning list, the specific alert, and
 * the national summary's published-warning count.
 */
export function useAlertTransition(): UseMutationResult<Alert, ApiError, TransitionVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ alertId, target }: TransitionVariables) => api.transitionAlert(alertId, target),
    // A workflow decision is a deliberate act; retrying it automatically could
    // replay an approval the user did not intend to repeat.
    retry: false,
    onSuccess: (_alert, variables) => {
      void client.invalidateQueries({ queryKey: queryKeys.alerts });
      void client.invalidateQueries({ queryKey: queryKeys.alert(variables.alertId) });
      void client.invalidateQueries({ queryKey: ['dashboard', 'national-summary'] });
    },
  });
}

/* --------------------------------------------------------------- geography -- */

export function useAdminUnits(
  level?: AdminLevel,
  enabled = true,
): UseQueryResult<AdminUnit[], ApiError> {
  return useQuery({
    queryKey: queryKeys.adminUnits(level),
    queryFn: ({ signal }) => api.fetchAdminUnits(level, signal),
    enabled,
    // Administrative boundaries are versioned reference data, not live state.
    staleTime: 30 * 60_000,
  });
}

export function useBoundaries(
  version?: string,
  enabled = true,
): UseQueryResult<BoundaryFeatureCollection, ApiError> {
  return useQuery({
    queryKey: queryKeys.boundaries(version),
    queryFn: ({ signal }) => api.fetchBoundaries(version, signal),
    enabled,
    staleTime: 30 * 60_000,
  });
}

/* ------------------------------------------------------------ data sources -- */

export function useDataSources(enabled = true): UseQueryResult<DataSource[], ApiError> {
  return useQuery({
    queryKey: queryKeys.dataSources,
    queryFn: ({ signal }) => api.fetchDataSources(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useDataSourceHealth(
  sourceId: string,
  enabled = true,
): UseQueryResult<DataSourceHealth, ApiError> {
  return useQuery({
    queryKey: queryKeys.dataSourceHealth(sourceId),
    queryFn: ({ signal }) => api.fetchDataSourceHealth(sourceId, signal),
    enabled: enabled && Boolean(sourceId),
    staleTime: 60_000,
  });
}

/* ------------------------------------------------------------- operational -- */

export function useExposureAssessments(
  enabled = true,
): UseQueryResult<ExposureListItem[], ApiError> {
  return useQuery({
    queryKey: queryKeys.exposure,
    queryFn: ({ signal }) => api.fetchExposureAssessments(signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useActionItems(enabled = true): UseQueryResult<ActionItemListItem[], ApiError> {
  return useQuery({
    queryKey: queryKeys.actionItems,
    queryFn: ({ signal }) => api.fetchActionItems(signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useVerificationTasks(
  enabled = true,
): UseQueryResult<VerificationTaskListItem[], ApiError> {
  return useQuery({
    queryKey: queryKeys.verificationTasks,
    queryFn: ({ signal }) => api.fetchVerificationTasks(signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useObservations(
  query: api.ObservationQuery,
  enabled = true,
): UseQueryResult<Observation[], ApiError> {
  return useQuery({
    queryKey: queryKeys.observations(
      query.admin_unit_id,
      query.indicator_code,
      query.start,
      query.end,
    ),
    queryFn: ({ signal }) => api.fetchObservations(query, signal),
    enabled: enabled && Boolean(query.admin_unit_id),
    staleTime: 60_000,
  });
}

export function useReports(enabled = true): UseQueryResult<GovernedReport[], ApiError> {
  return useQuery({
    queryKey: queryKeys.reports,
    queryFn: ({ signal }) => api.fetchReports(signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useModelOperations(enabled = true): UseQueryResult<ModelOperations[], ApiError> {
  return useQuery({
    queryKey: queryKeys.modelOperations,
    queryFn: ({ signal }) => api.fetchModelOperations(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

/* --------------------------------------------------------- administration -- */

export function useOrganizations(enabled = true): UseQueryResult<Organization[], ApiError> {
  return useQuery({
    queryKey: queryKeys.organizations,
    queryFn: ({ signal }) => api.fetchOrganizations(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useUsers(enabled = true): UseQueryResult<UserAccount[], ApiError> {
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: ({ signal }) => api.fetchUsers(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useRoles(enabled = true): UseQueryResult<RoleDefinition[], ApiError> {
  return useQuery({
    queryKey: queryKeys.roles,
    queryFn: ({ signal }) => api.fetchRoles(signal),
    enabled,
    staleTime: 30 * 60_000,
  });
}
