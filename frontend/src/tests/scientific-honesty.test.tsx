/**
 * Scientific-honesty guards.
 *
 * These assert the claims the product must never make: nationwide flood
 * coverage from five gauges, district-level food-security output, an official
 * IPC classification, or a fabricated figure standing in for missing data.
 *
 * They are the tests most worth keeping if any others are ever dropped.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';

import { DroughtPage } from '../features/drought/DroughtPage';
import { FloodPage } from '../features/flood/FloodPage';
import { FoodSecurityPage } from '../features/food-security/FoodSecurityPage';
import {
  NATIONAL_ANALYST_CAPABILITIES,
  adminUnit,
  parentRegion,
  principal,
  riskSignal,
} from './fixtures';
import { renderWithProviders, signInForTest, signOutForTest, stubFetch } from './harness';

let stub: ReturnType<typeof stubFetch> | null = null;

beforeEach(() => {
  signInForTest();
});

afterEach(() => {
  stub?.restore();
  stub = null;
  signOutForTest();
  vi.unstubAllGlobals();
});

const GEOGRAPHY = {
  '/geography/boundaries': { body: { type: 'FeatureCollection', features: [] } },
  '/geography/admin-units': { body: [adminUnit(), parentRegion()] },
};

/* ---------------------------------------------------------------- drought -- */

describe('drought page', () => {
  it('renders district-scoped intelligence with its ranked table', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [riskSignal()] },
    });

    renderWithProviders(<DroughtPage />, { route: '/app/drought' });

    expect(
      await screen.findByRole('heading', { name: /drought intelligence/i }),
    ).toBeInTheDocument();
    expect(await screen.findAllByText('Jowhar')).not.toHaveLength(0);
    // The district's parent region is shown as context, not as its own signal.
    expect(await screen.findAllByText('Middle Shabelle')).not.toHaveLength(0);
  });

  it('never describes drought output as a famine forecast or IPC phase', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [riskSignal()] },
    });

    renderWithProviders(<DroughtPage />, { route: '/app/drought' });

    // Wait for the scope notice, which only renders once the principal and
    // its capabilities have resolved.
    await screen.findByText(/districts monitored/i);
    const text = document.body.textContent ?? '';
    expect(text).toContain('not a famine forecast');
    expect(text).toContain('not an IPC classification');
    expect(text).not.toMatch(/famine (is )?(predicted|forecast for|expected)/i);
  });

  it('states an honest empty condition when nothing is eligible', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [] },
    });

    renderWithProviders(<DroughtPage />, { route: '/app/drought' });

    expect(await screen.findByText(/no current drought intelligence/i)).toBeInTheDocument();
    expect(
      screen.getByText(/no eligible drought intelligence is available/i),
    ).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ flood -- */

describe('flood page', () => {
  const floodSignal = riskSignal({
    id: 'flood-1',
    domain: 'river_flood',
    level: 'critical',
    score: 0.82,
    provenance: {
      model_id: 'flood-early-warning',
      model_version: '1.1.0',
      station_code: 'SH004',
      river_name: 'Shabelle',
      level_condition: 'above normal',
      rate_of_rise_3d: 'above normal',
      antecedent_rainfall_7d: 'above normal',
      linked_district_name: 'Jowhar',
      population_context: 205986.7,
      data_quality: 'GOOD',
    },
  });

  it('frames flood intelligence as gauge monitoring, not area coverage', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [floodSignal] },
    });

    renderWithProviders(<FloodPage />, { route: '/app/flood' });

    expect(await screen.findByText(/river flood monitoring/i)).toBeInTheDocument();
    const text = document.body.textContent ?? '';
    expect(text).toContain('gauging stations only');
    expect(text).toContain('not Somalia-wide flood coverage');
    expect(text).toMatch(/does not cover flash or surface flooding/i);
  });

  it('counts gauges, never districts or an implied national area', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [floodSignal] },
    });

    renderWithProviders(<FloodPage />, { route: '/app/flood' });

    expect(await screen.findByText(/gauges at watch\+/i)).toBeInTheDocument();
    expect(screen.getByText(/gauges at warning\+/i)).toBeInTheDocument();
    expect(screen.getAllByText(/gauges monitored/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/highest station risk/i).length).toBeGreaterThan(0);
    // No area-scoped claim anywhere on the page.
    const text = document.body.textContent ?? '';
    expect(screen.queryByText(/districts flooded/i)).toBeNull();
    expect(text).not.toMatch(/estimated flood extent/i);
    expect(text).not.toMatch(/area (inundated|flooded)/i);
    // The map legend mentions flood extent only to deny that any is modelled.
    expect(text).toMatch(/no area flood extent is modelled or implied/i);
  });

  it('presents station attributes from the API without inventing missing ones', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': {
        body: [
          // A station whose provenance carries no hydrological detail at all.
          riskSignal({
            id: 'flood-bare',
            domain: 'river_flood',
            level: 'watch',
            score: 0.2,
            provenance: { station_code: 'JB009' },
          }),
        ],
      },
    });

    renderWithProviders(<FloodPage />, { route: '/app/flood' });

    expect(await screen.findByText('JB009')).toBeInTheDocument();
    // Absent hydrological facts render as not-reported, never as a plausible value.
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('describes exposure as population context, not people who would be flooded', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [floodSignal] },
    });

    renderWithProviders(<FloodPage />, { route: '/app/flood' });

    await screen.findByText('SH004');
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/people (who )?(will|would) be flooded/i);
    expect(text).not.toMatch(/people affected/i);
  });
});

/* ---------------------------------------------------------- food security -- */

describe('food security page', () => {
  const fsSignal = riskSignal({
    id: 'fs-1',
    domain: 'food_security_deterioration',
    level: 'watch',
    score: 0.41,
    admin_unit_id: parentRegion().id,
    provenance: { model_id: 'food-security-early-warning', model_version: '1.0.0' },
  });

  it('separates the model signal from an official IPC classification', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [fsSignal] },
    });

    renderWithProviders(<FoodSecurityPage />, { route: '/app/food-security' });

    expect(
      await screen.findByText(/this is a model early-warning signal, not an ipc classification/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/only the ipc technical working group can determine/i),
    ).toBeInTheDocument();
  });

  it('counts regions and never claims district-level output', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [fsSignal] },
    });

    renderWithProviders(<FoodSecurityPage />, { route: '/app/food-security' });

    expect(await screen.findByText(/regions monitored/i)).toBeInTheDocument();
    expect(screen.getByText(/regions at watch\+/i)).toBeInTheDocument();

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/no validated methodology exists to disaggregate this signal to district level/i);
    expect(screen.queryByText(/districts monitored/i)).toBeNull();
  });

  it('renders no IPC phase when the API supplies none', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [fsSignal] },
    });

    renderWithProviders(<FoodSecurityPage />, { route: '/app/food-security' });

    await screen.findByText(/regions monitored/i);
    // No fabricated phase number appears anywhere.
    expect(screen.queryByText(/phase [1-5]/i)).toBeNull();
    expect(screen.queryByText(/IPC 3/i)).toBeNull();
  });
});

/* ------------------------------------------------- no production fixtures -- */

describe('no production fixture fallback', () => {
  it('renders an empty state, never sample data, when the API returns nothing', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { body: [] },
    });

    renderWithProviders(<FloodPage />, { route: '/app/flood' });

    expect(await screen.findByText(/no current river flood intelligence/i)).toBeInTheDocument();

    const text = document.body.textContent ?? '';
    // Only identifiers unique to the fixtures count as leakage. Real place
    // names such as "Shabelle" legitimately appear in the page's own scope
    // statement, which describes which rivers the model covers.
    for (const marker of ['TEST FIXTURE', 'SH004', 'JB009', 'Lorem', 'Example Station']) {
      expect(text).not.toContain(marker);
    }
    // And no probability figure is invented for a station that does not exist.
    expect(text).not.toMatch(/[0-9]{1,3}%/);
  });

  it('renders an error state, never sample data, when the API fails', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      ...GEOGRAPHY,
      '/risks': { status: 500, body: { detail: 'pipeline unavailable' } },
    });

    renderWithProviders(<DroughtPage />, { route: '/app/drought' });

    expect(await screen.findByText(/service reported an internal error/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('TEST FIXTURE');
  });
});
