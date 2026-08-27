/**
 * Authentication, protected routing and role-aware navigation.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LoginPage } from '../features/auth/LoginPage';
import { AppRouter } from '../app/router/AppRouter';
import {
  landingRoute,
  visibleItems,
  visibleSections,
} from '../app/layouts/navigation';
import {
  NATIONAL_ANALYST_CAPABILITIES,
  REGIONAL_ANALYST_CAPABILITIES,
  VIEWER_CAPABILITIES,
  nationalSummary,
  principal,
} from './fixtures';
import { renderWithProviders, signInForTest, signOutForTest, stubFetch } from './harness';

let stub: ReturnType<typeof stubFetch> | null = null;

beforeEach(() => {
  signOutForTest();
});

afterEach(() => {
  stub?.restore();
  stub = null;
  signOutForTest();
  vi.unstubAllGlobals();
});

/* ---------------------------------------------------------------- sign-in -- */

describe('sign-in', () => {
  it('signs in with valid credentials and resolves the principal', async () => {
    const user = userEvent.setup();
    stub = stubFetch({
      '/auth/login': {
        body: {
          access_token: 'token',
          refresh_token: 'refresh-token-long-enough-for-the-backend-validator',
          token_type: 'bearer',
          expires_in: 900,
        },
      },
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
    });

    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'analyst@example.test');
    await user.type(screen.getByLabelText(/^password$/i), 'a-sufficiently-long-password');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    await waitFor(() => {
      expect(stub?.calls.some((call) => call.includes('/auth/login'))).toBe(true);
    });
  });

  it('shows a non-disclosing message on invalid credentials', async () => {
    const user = userEvent.setup();
    stub = stubFetch({
      '/auth/login': { status: 401, body: { detail: 'Invalid credentials' } },
    });

    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'analyst@example.test');
    await user.type(screen.getByLabelText(/^password$/i), 'wrong-password-value');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/were not accepted/i);
    // Must not reveal which field was wrong.
    expect(alert.textContent).not.toMatch(/user (not )?found|no such account/i);
  });

  it('offers a retryable message on network failure rather than blaming credentials', async () => {
    const user = userEvent.setup();
    stub = stubFetch({ '/auth/login': { networkError: true } });

    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'analyst@example.test');
    await user.type(screen.getByLabelText(/^password$/i), 'a-sufficiently-long-password');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot reach the platform/i);
  });

  it('toggles password visibility', async () => {
    const user = userEvent.setup();
    stub = stubFetch({});
    renderWithProviders(<LoginPage />);

    const field = screen.getByLabelText(/^password$/i);
    expect(field).toHaveAttribute('type', 'password');

    await user.click(screen.getByRole('button', { name: /show password/i }));
    expect(field).toHaveAttribute('type', 'text');

    await user.click(screen.getByRole('button', { name: /hide password/i }));
    expect(field).toHaveAttribute('type', 'password');
  });

  it('does not offer sign-in methods the backend has no endpoint for', () => {
    stub = stubFetch({});
    renderWithProviders(<LoginPage />);

    expect(screen.queryByText(/sign in with google/i)).toBeNull();
    expect(screen.queryByText(/continue with/i)).toBeNull();
    expect(screen.queryByText(/forgot (your )?password/i)).toBeNull();
    expect(screen.queryByLabelText(/remember me/i)).toBeNull();
  });
});

/* -------------------------------------------------------- protected routes -- */

describe('protected routes', () => {
  it('redirects an unauthenticated visitor to sign-in', async () => {
    stub = stubFetch({});
    renderWithProviders(<AppRouter />, { route: '/app/overview' });

    expect(await screen.findByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
  });

  it('renders the application shell for an authenticated principal', async () => {
    signInForTest();
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/dashboard/national-summary': { body: nationalSummary() },
      '/dashboard/scopes': { body: [] },
      '/geography/boundaries': { body: { type: 'FeatureCollection', features: [] } },
      '/geography/admin-units': { body: [] },
      '/risks': { body: [] },
      '/alerts': { body: [] },
      '/data-sources': { body: [] },
    });

    renderWithProviders(<AppRouter />, { route: '/app/overview' });

    expect(
      await screen.findByRole('heading', { name: /national early warning overview/i }),
    ).toBeInTheDocument();
  });

  it('states the access boundary instead of silently redirecting', async () => {
    signInForTest();
    stub = stubFetch({
      '/auth/me': { body: principal(VIEWER_CAPABILITIES) },
      '/data-sources': { body: [] },
    });

    // A read-only viewer holds no `data_sources.read` capability.
    renderWithProviders(<AppRouter />, { route: '/app/data-health' });

    expect(await screen.findByText(/access not authorised/i)).toBeInTheDocument();
    expect(screen.getByText(/platform administrator/i)).toBeInTheDocument();
  });
});

/* ------------------------------------------------------- role-aware navigation -- */

describe('role-aware navigation', () => {
  it('hides destinations a role cannot use', () => {
    const viewer = new Set(VIEWER_CAPABILITIES);
    const destinations = visibleItems(viewer).map((item) => item.to);

    expect(destinations).toContain('/app/warnings');
    expect(destinations).toContain('/app/reports');
    // A viewer has neither predictions.read nor data_sources.read.
    expect(destinations).not.toContain('/app/drought');
    expect(destinations).not.toContain('/app/data-health');
    expect(destinations).not.toContain('/app/admin');
  });

  it('shows the full operational surface to a national analyst', () => {
    const analyst = new Set(NATIONAL_ANALYST_CAPABILITIES);
    const destinations = visibleItems(analyst).map((item) => item.to);

    for (const route of [
      '/app/overview',
      '/app/map',
      '/app/drought',
      '/app/flood',
      '/app/food-security',
      '/app/warnings',
      '/app/history',
      '/app/data-health',
    ]) {
      expect(destinations).toContain(route);
    }
    // Even a national analyst does not administer users.
    expect(destinations).not.toContain('/app/admin');
  });

  it('drops sections that would otherwise render empty', () => {
    const sections = visibleSections(new Set(VIEWER_CAPABILITIES));
    for (const section of sections) {
      expect(section.items.length).toBeGreaterThan(0);
    }
  });

  it('lands each role on a page it can actually use', () => {
    expect(landingRoute(new Set(NATIONAL_ANALYST_CAPABILITIES))).toBe('/app/overview');
    expect(landingRoute(new Set(REGIONAL_ANALYST_CAPABILITIES))).toBe('/app/overview');
    // A principal with no capabilities still reaches a valid page.
    expect(landingRoute(new Set())).toBe('/app/profile');
  });
});
