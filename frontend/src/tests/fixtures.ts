/**
 * TEST-ONLY fixtures.
 *
 * These values exist solely so component behaviour can be asserted in
 * isolation. They are imported exclusively by files under `src/tests/` and by
 * `*.test.tsx` modules, and are never reachable from production code — the
 * application has no fallback path that substitutes fixture data when an API
 * call fails or returns nothing. `no-production-fixture-fallback.test.ts`
 * enforces that boundary.
 */

import type {
  AdminUnit,
  Alert,
  AlertListItem,
  DataSource,
  DataSourceHealth,
  NationalSummary,
  Principal,
  RiskSignal,
} from '../types/api';

export const TEST_LABEL = 'TEST FIXTURE — NOT PRODUCTION DATA';

export function principal(capabilities: string[] = []): Principal {
  return {
    user_id: '11111111-1111-4111-8111-111111111111',
    email: 'analyst@example.test',
    display_name: 'Test Analyst',
    capabilities,
  };
}

/** Capability sets mirroring roles in `backend/app/modules/auth/roles.py`. */
export const NATIONAL_ANALYST_CAPABILITIES = [
  'geography.read',
  'data_sources.read',
  'indicators.read',
  'predictions.read',
  'alerts.read',
  'alerts.review',
  'alerts.approve',
  'alerts.publish',
  'alerts.resolve',
  'field_tasks.create',
  'field_reports.verify',
  'exposure.read',
  'early_actions.read',
  'models.read',
  'reports.read',
];

export const VIEWER_CAPABILITIES = [
  'geography.read',
  'indicators.read',
  'alerts.read',
  'reports.read',
];

export const REGIONAL_ANALYST_CAPABILITIES = [
  'geography.read',
  'indicators.read',
  'predictions.read',
  'alerts.read',
  'alerts.review',
  'field_tasks.create',
  'field_reports.verify',
];

export function riskSignal(overrides: Partial<RiskSignal> = {}): RiskSignal {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    domain: 'drought',
    admin_unit_id: '33333333-3333-4333-8333-333333333333',
    level: 'warning',
    score: 0.72,
    confidence: 0.64,
    drivers: [
      {
        feature: 'ndvi_anomaly_90d',
        observed_value: -0.42,
        training_median: 0.05,
        probability_change_if_replaced_by_training_median: 0.28,
        reason_code: 'NDVI_BELOW_NORMAL',
      },
      {
        feature: 'rainfall_anomaly_30d',
        observed_value: -38.1,
        training_median: 2.4,
        probability_change_if_replaced_by_training_median: 0.16,
        reason_code: 'RAINFALL_BELOW_NORMAL',
      },
    ],
    provenance: {
      label: TEST_LABEL,
      model_id: 'drought-early-warning',
      model_version: '1.1.0',
      pipeline_version: '1.0.0',
      data_quality: 'GOOD',
      freshness: 'GOOD',
      automatic_warning_publication: false,
    },
    target_period: '2026-Gu',
    created_at: '2026-08-27T05:00:00Z',
    ...overrides,
  };
}

export function adminUnit(overrides: Partial<AdminUnit> = {}): AdminUnit {
  return {
    id: '33333333-3333-4333-8333-333333333333',
    stable_code: 'SO2101',
    name: 'Jowhar',
    level: 'district',
    parent_id: '44444444-4444-4444-8444-444444444444',
    boundary_version: 'test-1.0.0',
    boundary_source: TEST_LABEL,
    valid_from: '2024-01-01',
    valid_to: null,
    aliases: [],
    ...overrides,
  };
}

export function parentRegion(): AdminUnit {
  return adminUnit({
    id: '44444444-4444-4444-8444-444444444444',
    stable_code: 'SO21',
    name: 'Middle Shabelle',
    level: 'region',
    parent_id: null,
  });
}

export function alert(overrides: Partial<AlertListItem> = {}): AlertListItem {
  return {
    id: '55555555-5555-4555-8555-555555555555',
    signal_id: '22222222-2222-4222-8222-222222222222',
    status: 'in_review',
    classification: 'internal',
    title: 'Elevated drought risk — Jowhar',
    summary: 'Vegetation and rainfall indicators are below seasonal normal.',
    admin_unit_id: '33333333-3333-4333-8333-333333333333',
    risk_domain: 'drought',
    risk_level: 'warning',
    target_period: '2026-Gu',
    created_at: '2026-08-27T05:00:00Z',
    published_at: null,
    ...overrides,
  };
}

export function alertDetail(overrides: Partial<Alert> = {}): Alert {
  const list = alert();
  return {
    id: list.id,
    signal_id: list.signal_id,
    status: list.status,
    classification: list.classification,
    title: list.title,
    summary: list.summary,
    ...overrides,
  };
}

export function nationalSummary(overrides: Partial<NationalSummary> = {}): NationalSummary {
  return {
    generated_at: '2026-08-27T05:00:00Z',
    boundary_scope: 'national',
    scope_admin_unit_id: null,
    scope_name: 'Somalia',
    scope_level: 'country',
    boundary_version: 'test-1.0.0',
    published_warning_count: 2,
    domains: [
      {
        domain: 'drought',
        level: 'warning',
        admin_units_evaluated: 87,
        target_periods: ['2026-Gu'],
        source_ids: ['chirps', 'modis'],
        as_of: '2026-08-27T05:00:00Z',
        stale: false,
      },
      {
        domain: 'river_flood',
        level: 'critical',
        admin_units_evaluated: 5,
        target_periods: ['2026-08-28'],
        source_ids: ['swalim'],
        as_of: '2026-08-27T05:00:00Z',
        stale: false,
      },
      {
        domain: 'food_security_deterioration',
        level: 'watch',
        admin_units_evaluated: 18,
        target_periods: ['2026-Gu'],
        source_ids: ['ipc', 'wfp'],
        as_of: '2026-08-20T05:00:00Z',
        stale: true,
      },
    ],
    ...overrides,
  };
}

export function dataSource(overrides: Partial<DataSource> = {}): DataSource {
  return {
    id: '66666666-6666-4666-8666-666666666666',
    name: 'CHIRPS Rainfall',
    domain: 'rainfall',
    owner: 'UCSB Climate Hazards Center',
    license: 'Public domain',
    access_method: 'api',
    expected_frequency_minutes: 1440,
    geographic_resolution: '0.05 degrees',
    classification: 'public',
    verified: true,
    enabled: true,
    ...overrides,
  };
}

export function dataSourceHealth(
  overrides: Partial<DataSourceHealth> = {},
): DataSourceHealth {
  return {
    source_id: '66666666-6666-4666-8666-666666666666',
    status: 'fresh',
    last_success: '2026-08-27T04:00:00Z',
    last_run_status: 'succeeded',
    rows_received: 1024,
    rows_quarantined: 0,
    ...overrides,
  };
}
