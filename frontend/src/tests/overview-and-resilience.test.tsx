/**
 * National Overview: successful render, partial API failure, honest data
 * status, and stale/empty presentation.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { OverviewPage } from '../features/overview/OverviewPage';
import { DataHealthPage } from '../features/data-health/DataHealthPage';
import {
  NATIONAL_ANALYST_CAPABILITIES,
  alert,
  dataSource,
  dataSourceHealth,
  nationalSummary,
  principal,
} from './fixtures';
import { renderWithProviders, signInForTest, signOutForTest, stubFetch } from './harness';

let stub: ReturnType<typeof stubFetch> | null = null;

const BASE_ROUTES = {
  '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
  '/dashboard/scopes': { body: [] },
  '/geography/boundaries': { body: { type: 'FeatureCollection', features: [] } },
  '/geography/admin-units': { body: [] },
  '/risks': { body: [] },
  '/alerts': { body: [] },
  '/data-sources': { body: [] },
};

beforeEach(() => {
  signInForTest();
});

afterEach(() => {
  stub?.restore();
  stub = null;
  signOutForTest();
  vi.unstubAllGlobals();
});

describe('national overview', () => {
  it('renders the national summary with per-domain severity', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: nationalSummary() },
    });

    renderWithProviders(<OverviewPage />);

    expect(
      await screen.findByRole('heading', { name: /national early warning overview/i }),
    ).toBeInTheDocument();

    // Each domain card reports its own highest level.
    expect(await screen.findByText('Drought')).toBeInTheDocument();
    expect(screen.getByText('River Flood')).toBeInTheDocument();
    expect(screen.getByText('Food Security')).toBeInTheDocument();
  });

  it('reports PARTIAL data status when a domain is stale, and says why', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      // The fixture marks food security stale.
      '/dashboard/national-summary': { body: nationalSummary() },
    });

    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText('PARTIAL')).toBeInTheDocument();
    expect(
      await screen.findByText(/current intelligence is limited/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 of 3 domains are stale/i)).toBeInTheDocument();
  });

  it('never reports GOOD while any domain is stale', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: nationalSummary() },
    });

    renderWithProviders(<OverviewPage />);

    await screen.findByText('PARTIAL');
    expect(screen.queryByText(/^GOOD$/)).toBeNull();
  });

  it('reports GOOD only when every domain is fresh and evaluated', async () => {
    const healthy = nationalSummary();
    healthy.domains = healthy.domains.map((domain) => ({ ...domain, stale: false }));

    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: healthy },
    });

    renderWithProviders(<OverviewPage />);
    expect(await screen.findByText('GOOD')).toBeInTheDocument();
  });

  it('reports INSUFFICIENT rather than NORMAL when nothing was evaluated', async () => {
    const empty = nationalSummary();
    empty.domains = empty.domains.map((domain) => ({
      ...domain,
      level: null,
      admin_units_evaluated: 0,
    }));

    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: empty },
    });

    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText('INSUFFICIENT')).toBeInTheDocument();
    // "No evidence" must not be presented as a calm NORMAL reading.
    expect(await screen.findAllByText(/no evidence/i)).not.toHaveLength(0);
    expect(screen.queryByText('NORMAL')).toBeNull();
  });

  it('keeps healthy panels working when one endpoint fails', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: nationalSummary() },
      // The data-health widget fails; the rest of the page must survive.
      '/data-sources': { status: 500, body: { detail: 'database unavailable' } },
    });

    renderWithProviders(<OverviewPage />);

    // Summary still renders.
    expect(await screen.findByText('Drought')).toBeInTheDocument();
    // And the failing widget states its own failure.
    expect(await screen.findByText(/internal error/i)).toBeInTheDocument();
  });

  it('shows an honest error, not an empty state, when the summary itself fails', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { status: 500, body: { detail: 'upstream failure' } },
    });

    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/service reported an internal error/i)).toBeInTheDocument();
    // A technical failure must never be dressed as "no current intelligence".
    expect(screen.queryByText(/no eligible intelligence is available/i)).toBeNull();
  });

  it('states an empty review queue plainly when the request succeeded', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: nationalSummary() },
      '/alerts': { body: [] },
    });

    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/no warnings require review/i)).toBeInTheDocument();
  });

  it('surfaces a critical warning awaiting a decision in the priority queue', async () => {
    stub = stubFetch({
      ...BASE_ROUTES,
      '/dashboard/national-summary': { body: nationalSummary() },
      '/alerts': {
        body: [
          alert({ id: 'a-1', risk_level: 'watch', title: 'Watch item' }),
          alert({
            id: 'a-2',
            risk_level: 'critical',
            title: 'Critical river flood — Jowhar',
            risk_domain: 'river_flood',
          }),
        ],
      },
    });

    renderWithProviders(<OverviewPage />);

    const queue = await screen.findByText(/priority warnings/i);
    expect(queue).toBeInTheDocument();
    expect(await screen.findByText(/critical river flood — jowhar/i)).toBeInTheDocument();
  });
});

describe('data health', () => {
  it('judges each source against its own cadence, not a daily default', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/data-sources': {
        body: [
          dataSource({ id: 'src-daily', name: 'CHIRPS Rainfall', expected_frequency_minutes: 1440 }),
          dataSource({
            id: 'src-ipc',
            name: 'IPC Classification',
            domain: 'food security',
            // A seasonal assessment cycle, roughly quarterly.
            expected_frequency_minutes: 129600,
          }),
        ],
      },
      '/data-sources/src-daily/health': { body: dataSourceHealth({ status: 'fresh' }) },
      '/data-sources/src-ipc/health': {
        // Weeks old, but the backend still reports it fresh for its cadence.
        body: dataSourceHealth({ source_id: 'src-ipc', status: 'fresh', last_success: '2026-07-01T00:00:00Z' }),
      },
    });

    renderWithProviders(<DataHealthPage />);

    // Both the desktop table and the mobile card list are present in jsdom,
    // since Tailwind's responsive visibility is CSS-only. Assert on presence
    // rather than uniqueness.
    expect((await screen.findAllByText('IPC Classification')).length).toBeGreaterThan(0);
    // The declared cadence is displayed, so the freshness verdict is explicable.
    expect((await screen.findAllByText('Every 3 mo')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('FRESH').length).toBeGreaterThan(0);
  });

  it('degrades a single row when its health endpoint fails', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/data-sources': { body: [dataSource({ id: 'src-broken', name: 'SWALIM River Levels' })] },
      '/data-sources/src-broken/health': { status: 500, body: { detail: 'unavailable' } },
    });

    renderWithProviders(<DataHealthPage />);

    // The source still lists; only its status cell reports the gap.
    expect((await screen.findAllByText('SWALIM River Levels')).length).toBeGreaterThan(0);
    expect(await screen.findAllByText(/status unavailable/i)).not.toHaveLength(0);
    // It must never be shown as FRESH just because the check failed.
    expect(screen.queryByText('FRESH')).toBeNull();
  });

  it('states plainly when no source is configured', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/data-sources': { body: [] },
    });

    renderWithProviders(<DataHealthPage />);
    expect(await screen.findByText(/no data sources configured/i)).toBeInTheDocument();
  });

  it('explains that cadence, not a daily rule, determines freshness', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/data-sources': { body: [] },
    });

    renderWithProviders(<DataHealthPage />);
    const note = await screen.findByText(/cadence matters/i);
    expect(note.parentElement).toHaveTextContent(/not judged by a daily standard/i);
  });
});
