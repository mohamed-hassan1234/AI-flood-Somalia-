import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { afterEach, test, vi } from 'vitest';
import { App } from './App';
import { DistrictProfilePage } from '../features/district-profile/DistrictProfilePage';

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

function renderWithClient(content: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{content}</QueryClientProvider>);
}

test('shows an unauthorized state without requesting internal data', () => {
  const fetch = vi.spyOn(globalThis, 'fetch');
  renderWithClient(<MemoryRouter><App /></MemoryRouter>);
  expect(screen.getByText(/Trusted evidence/i)).toBeInTheDocument();
  expect(screen.getByText('Sign in required')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test('switches the application shell and executive copy to Somali', async () => {
  renderWithClient(<MemoryRouter><App /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'so' } });
  expect(await screen.findByText('Guddiga Fulinta')).toBeInTheDocument();
  expect(screen.getByText('Caddeyn lagu kalsoon yahay.')).toBeInTheDocument();
  expect(screen.getByText('Gelitaan ayaa loo baahan yahay')).toBeInTheDocument();
  expect(document.documentElement.lang).toBe('so');
  expect(localStorage.getItem('somalia-ai-language')).toBe('so');
});

test('does not fabricate a map when no governed geometry exists', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  renderWithClient(<MemoryRouter initialEntries={['/map-explorer']}><App /></MemoryRouter>);
  expect(await screen.findByText('No approved boundary geometry configured')).toBeInTheDocument();
  expect(screen.getByText('No synthetic fallback')).toBeInTheDocument();
});

test('renders governed national data and explicit unknown domains', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  const summary = {
    generated_at: '2027-01-15T10:00:00Z',
    boundary_scope: 'versioned national aggregation',
    scope_admin_unit_id: null, scope_name: 'Somalia', scope_level: 'country', boundary_version: null,
    published_warning_count: 1,
    domains: [
      { domain: 'drought', level: 'warning', admin_units_evaluated: 3, target_periods: ['2027-Gu'], source_ids: ['synthetic-source'], as_of: '2027-01-15T09:00:00Z', stale: false },
      { domain: 'river_flood', level: null, admin_units_evaluated: 0, target_periods: [], source_ids: [], as_of: null, stale: true },
      { domain: 'flash_flood', level: null, admin_units_evaluated: 0, target_periods: [], source_ids: [], as_of: null, stale: true },
      { domain: 'food_security_deterioration', level: null, admin_units_evaluated: 0, target_periods: [], source_ids: [], as_of: null, stale: true },
    ],
  };
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(
    String(input).includes('/dashboard/scopes')
      ? [{ id: 'u1', name: 'Synthetic Region', level: 'region', boundary_version: 'synthetic-v1' }]
      : { ...summary, ...(String(input).includes('admin_unit_id') ? { scope_admin_unit_id: 'u1', scope_name: 'Synthetic Region', scope_level: 'region', boundary_version: 'synthetic-v1' } : {}) },
  ), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter><App /></MemoryRouter>);
  expect(await screen.findByText('3 areas evaluated')).toBeInTheDocument();
  expect(screen.getByText('1 published warnings')).toBeInTheDocument();
  expect(screen.getAllByText('unknown')).toHaveLength(3);
  expect(screen.getAllByText(/STALE · 0 SOURCES/)).toHaveLength(3);
  fireEvent.change(await screen.findByLabelText('Executive geography'), { target: { value: 'u1' } });
  expect(await screen.findByText('Synthetic Region · region')).toBeInTheDocument();
});

test('shows warnings returned by the public projection', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: '11111111-1111-1111-1111-111111111111',
    title: 'Drought warning for Synthetic District',
    summary: 'SYNTHETIC / DEVELOPMENT DATA',
    risk_domain: 'drought',
    risk_level: 'warning',
    target_period: '2027-Gu',
    admin_unit_id: '22222222-2222-2222-2222-222222222222',
    admin_unit_name: 'Synthetic District',
    boundary_version: 'synthetic-v1',
    published_at: '2027-01-15T10:00:00Z',
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter initialEntries={['/public-warnings']}><App /></MemoryRouter>);

  expect(await screen.findByText('Drought warning for Synthetic District')).toBeInTheDocument();
  expect(screen.getByText('Synthetic District')).toBeInTheDocument();
});

test('renders published public reports without authentication', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', title: 'Synthetic public situation report',
    reporting_period: '2027-Gu', admin_unit_id: 'u1', admin_unit_name: 'Synthetic District',
    boundary_version: 'synthetic-v1', sections: [{ heading: 'Situation', body: 'Synthetic evidence only' }],
    findings: ['Synthetic finding'], recommendations: ['Use an approved playbook'],
    published_at: '2027-01-15T10:00:00Z',
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  renderWithClient(<MemoryRouter initialEntries={['/reports']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic public situation report')).toBeInTheDocument();
  expect(screen.getByText('public')).toBeInTheDocument();
  expect(screen.getByText('Synthetic finding')).toBeInTheDocument();
  expect(screen.getByText('Use an approved playbook')).toBeInTheDocument();
});

test('renders the governed national administration inventory', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    const payload = url.endsWith('/administration/organizations')
      ? [{ id: 'o1', name: 'Synthetic Ministry', organization_type: 'government', active: true }]
      : url.endsWith('/administration/users')
        ? [{ id: 'u1', email: 'analyst@development.invalid', display_name: 'Synthetic Analyst', active: true }]
        : url.endsWith('/administration/roles')
          ? [{ id: 'r1', name: 'National Analyst', description: 'Synthetic role', capabilities: ['users.manage'] }]
          : [{ id: 'm1', user_id: 'u1', organization_id: 'o1', role_id: 'r1', classification_ceiling: 'internal', active: true, national: true, admin_unit_ids: [] }];
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  renderWithClient(<MemoryRouter initialEntries={['/administration']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic Analyst')).toBeInTheDocument();
  expect(screen.getByText('Synthetic Ministry')).toBeInTheDocument();
  expect(screen.getByText('National Analyst')).toBeInTheDocument();
  expect(screen.getByText('1 memberships')).toBeInTheDocument();
});

test('renders only published products in the partner portal', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const warnings = String(input).includes('/alerts/partner-warnings');
    return new Response(JSON.stringify(warnings ? [{
      id: 'w1', title: 'Synthetic partner warning', summary: 'SYNTHETIC / DEVELOPMENT DATA',
      classification: 'partner', risk_domain: 'drought', risk_level: 'warning',
      target_period: '2027-Gu', published_at: '2027-01-15T10:00:00Z',
    }] : [{
      id: 'r1', title: 'Synthetic partner report', reporting_period: '2027-Gu',
      boundary_version: 'synthetic-v1', classification: 'partner', findings: ['Synthetic finding'],
      recommendations: ['Approved action'], published_at: '2027-01-15T10:00:00Z',
    }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  renderWithClient(<MemoryRouter initialEntries={['/partner-portal']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic partner warning')).toBeInTheDocument();
  expect(screen.getByText('Synthetic partner report')).toBeInTheDocument();
  expect(screen.getAllByText('partner', { selector: 'strong' })).toHaveLength(2);
});

test('renders verified source freshness and quarantine status', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith('/data-sources')) {
      return new Response(JSON.stringify([{
        id: '33333333-3333-3333-3333-333333333333',
        name: 'Synthetic rainfall source',
        domain: 'rainfall',
        owner: 'Synthetic owner',
        license: 'Synthetic fixture license',
        access_method: 'file',
        expected_frequency_minutes: 1440,
        geographic_resolution: 'synthetic district',
        classification: 'internal',
        verified: true,
        enabled: true,
      }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({
      source_id: '33333333-3333-3333-3333-333333333333',
      status: 'stale',
      last_success: '2027-01-01T00:00:00Z',
      last_run_status: 'succeeded',
      rows_received: 10,
      rows_quarantined: 2,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });

  renderWithClient(<MemoryRouter initialEntries={['/data-health']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic rainfall source')).toBeInTheDocument();
  expect(screen.getByText('stale')).toBeInTheDocument();
  expect(screen.getByText('Synthetic fixture license · INTERNAL')).toBeInTheDocument();
  expect(screen.getByText('2')).toBeInTheDocument();
});

test('renders a scoped district time series with chart metadata and table', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes('/geography/admin-units')) {
      return new Response(JSON.stringify([{
        id: '44444444-4444-4444-4444-444444444444',
        stable_code: 'SO-SYN-D1',
        name: 'Synthetic District',
        level: 'district',
        parent_id: null,
        boundary_version: 'synthetic-v1',
        boundary_source: 'SYNTHETIC / DEVELOPMENT DATA',
        valid_from: '2020-01-01',
        valid_to: null,
        aliases: [],
      }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify([
      { id: 'o1', source_id: 's1', source_name: 'Synthetic rainfall source', source_classification: 'internal', admin_unit_id: '44444444-4444-4444-4444-444444444444', indicator_code: 'rainfall.total', value: null, value_kind: 'observed', unit: 'mm', reference_time: '2027-01-01T00:00:00Z', retrieved_at: '2027-01-02T00:00:00Z', stage: 'normalized', quality_flags: ['missing_value'], boundary_version: 'synthetic-v1', season_name: 'Synthetic season', season_version: 'v1', season_authority: 'SYNTHETIC / DEVELOPMENT DATA' },
      { id: 'o2', source_id: 's1', source_name: 'Synthetic rainfall source', source_classification: 'internal', admin_unit_id: '44444444-4444-4444-4444-444444444444', indicator_code: 'rainfall.total', value: 20, value_kind: 'observed', unit: 'mm', reference_time: '2027-01-08T00:00:00Z', retrieved_at: '2027-01-09T00:00:00Z', stage: 'normalized', quality_flags: [], boundary_version: 'synthetic-v1', season_name: 'Synthetic season', season_version: 'v1', season_authority: 'SYNTHETIC / DEVELOPMENT DATA' },
    ]), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });

  renderWithClient(<MemoryRouter><DistrictProfilePage /></MemoryRouter>);
  expect(
    await screen.findByText('Accessible observation values', {}, { timeout: 5000 }),
  ).toBeInTheDocument();
  expect(screen.getAllByText('Synthetic rainfall source').length).toBeGreaterThan(0);
  expect(screen.getByText('Missing mm')).toBeInTheDocument();
  expect(screen.getByText('missing_value')).toBeInTheDocument();
  expect(screen.getAllByText('Synthetic season (v1)')).toHaveLength(2);
  expect(screen.getByText(/Synthetic season · v1 · SYNTHETIC/)).toBeInTheDocument();
  expect(screen.getAllByText('synthetic-v1')).toHaveLength(2);
}, 60_000);

test('keeps risk severity separate from alert workflow status', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: '55555555-5555-5555-5555-555555555555',
    signal_id: '66666666-6666-6666-6666-666666666666',
    status: 'in_review',
    classification: 'internal',
    title: 'Synthetic drought review',
    summary: 'SYNTHETIC / DEVELOPMENT DATA',
    admin_unit_id: '44444444-4444-4444-4444-444444444444',
    risk_domain: 'drought',
    risk_level: 'critical',
    target_period: '2027-Gu',
    created_at: '2027-01-01T00:00:00Z',
    published_at: null,
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter initialEntries={['/alerts']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic drought review')).toBeInTheDocument();
  expect(screen.getByText('critical')).toBeInTheDocument();
  expect(screen.getByText('in review')).toBeInTheDocument();
  expect(screen.getByText('Not published')).toBeInTheDocument();
});

test('renders the scoped field verification work queue', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: '77777777-7777-7777-7777-777777777777',
    alert_id: '55555555-5555-5555-5555-555555555555',
    alert_title: 'Synthetic drought verification',
    classification: 'internal',
    admin_unit_id: '44444444-4444-4444-4444-444444444444',
    risk_domain: 'drought',
    assigned_to: null,
    due_at: '2020-01-01T00:00:00Z',
    priority: 'critical',
    status: 'open',
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter initialEntries={['/field-verification']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic drought verification')).toBeInTheDocument();
  expect(screen.getByText('critical')).toBeInTheDocument();
  expect(screen.getByText('open')).toBeInTheDocument();
  expect(screen.getByText(/OVERDUE/)).toBeInTheDocument();
});

test('renders accountable early actions with blockers and evidence progress', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: '88888888-8888-8888-8888-888888888888', plan_title: 'Synthetic response plan',
    alert_title: 'Synthetic drought warning', risk_domain: 'drought', classification: 'internal',
    description: 'Inspect synthetic water points', due_at: '2020-01-01T00:00:00Z',
    status: 'in_progress', blockers: ['Road access pending'], evidence_count: 2,
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter initialEntries={['/early-actions']}><App /></MemoryRouter>);
  expect(await screen.findByText('Inspect synthetic water points')).toBeInTheDocument();
  expect(screen.getByText('in progress')).toBeInTheDocument();
  expect(screen.getByText('Road access pending')).toBeInTheDocument();
  expect(screen.getByText('2 objects')).toBeInTheDocument();
  expect(screen.getByText(/OVERDUE/)).toBeInTheDocument();
});

test('renders scoped exposure with explicit unknowns and confidence', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: 'cccccccc-cccc-cccc-cccc-cccccccccccc', alert_title: 'Synthetic drought warning',
    classification: 'internal', risk_domain: 'drought', risk_level: 'warning',
    population: 1200, settlements: null, cropland_hectares: 340,
    infrastructure: { water_points: 4 }, confidence: 0.7, lineage_available: true,
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  renderWithClient(<MemoryRouter initialEntries={['/exposure']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic drought warning')).toBeInTheDocument();
  expect(screen.getByText('1,200')).toBeInTheDocument();
  expect(screen.getByText('Unknown')).toBeInTheDocument();
  expect(screen.getByText('340 ha')).toBeInTheDocument();
  expect(screen.getByText('70%')).toBeInTheDocument();
  expect(screen.getByText(/Source lineage recorded/)).toBeInTheDocument();
});

test('renders privacy-safe notification delivery operations', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: '99999999-9999-9999-9999-999999999999', event_key: 'synthetic-warning-published',
    event_title: 'Synthetic notified warning', channel: 'in_app', status: 'queued',
    recipient_is_current_user: true, attempt_count: 1, next_attempt_at: null,
    acknowledged_at: null, escalated_at: null, escalation_level: 0,
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter initialEntries={['/notifications']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic notified warning')).toBeInTheDocument();
  expect(screen.getByText('queued')).toBeInTheDocument();
  expect(screen.getByText('Level 0')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Acknowledge' })).toBeInTheDocument();
});

test('renders traceable model governance evidence', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{
    id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', name: 'Transparent drought benchmark',
    version: 'test-v1', state: 'validated', snapshot_name: 'Synthetic chronological snapshot',
    snapshot_row_count: 100, feature_name: 'Synthetic drought features', feature_version: 'features-v1',
    metrics: { precision: 0.7, recall: 0.8, brier: 0.16 },
    model_card: { chronological_backtest: true, region_evaluation: true, season_evaluation: true, limitations: ['SYNTHETIC'] },
    promotion_ready: true,
  }]), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  renderWithClient(<MemoryRouter initialEntries={['/ml-operations']}><App /></MemoryRouter>);
  expect(await screen.findByText('Transparent drought benchmark')).toBeInTheDocument();
  expect(screen.getByText('Promotion evidence complete')).toBeInTheDocument();
  expect(screen.getByText(/Synthetic chronological snapshot/)).toBeInTheDocument();
  expect(screen.getByText('0.16')).toBeInTheDocument();
});

test('renders a bounded scenario lab with non-publication guardrail', async () => {
  sessionStorage.setItem('somalia-ai-access-token', 'synthetic-test-token');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes('/ml/snapshot-options')) return new Response(JSON.stringify([{ id: 's1', name: 'Synthetic baseline', row_count: 100 }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/geography/admin-units')) return new Response(JSON.stringify([{ id: 'u1', name: 'Synthetic District' }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
    return new Response(JSON.stringify([{ id: 'x1', name: 'Synthetic compound shock', snapshot_name: 'Synthetic baseline', admin_unit_name: 'Synthetic District', domain: 'drought', modifications: { compound_shock: 0.1 }, result: { baseline_score: 0.4, simulated_score: 0.5, may_publish_warning: false }, label: 'SIMULATION', created_at: '2027-01-01T00:00:00Z' }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });

  renderWithClient(<MemoryRouter initialEntries={['/scenario-lab']}><App /></MemoryRouter>);
  expect(await screen.findByText('Synthetic compound shock')).toBeInTheDocument();
  expect(screen.getByText('SIMULATION')).toBeInTheDocument();
  expect(screen.getByText('Prohibited')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
});
