/**
 * Warning Center filtering and the review workspace decision panel.
 *
 * These are the tests that guard the governance model: which actions are
 * offered, to whom, and what confirmation a consequential decision requires.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { WarningCenterPage } from '../features/warnings/WarningCenterPage';
import { WarningReviewPage } from '../features/warnings/WarningReviewPage';
import {
  NATIONAL_ANALYST_CAPABILITIES,
  REGIONAL_ANALYST_CAPABILITIES,
  VIEWER_CAPABILITIES,
  alert,
  alertDetail,
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

const QUEUE = [
  alert({ id: 'w-critical', risk_level: 'critical', title: 'Critical flood at SH004', risk_domain: 'river_flood', status: 'in_review' }),
  alert({ id: 'w-watch', risk_level: 'watch', title: 'Watch drought in Baidoa', status: 'draft' }),
  alert({ id: 'w-published', risk_level: 'warning', title: 'Published warning', status: 'published', published_at: '2026-08-26T05:00:00Z' }),
  alert({ id: 'w-approved', risk_level: 'warning', title: 'Approved warning', status: 'approved' }),
];

/* ------------------------------------------------------------ warning center -- */

describe('warning center', () => {
  it('defaults to the queue that needs a human decision', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: QUEUE },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });

    expect(await screen.findByText('Critical flood at SH004')).toBeInTheDocument();
    expect(screen.getByText('Watch drought in Baidoa')).toBeInTheDocument();
    // Approved and published warnings are not in the review queue.
    expect(screen.queryByText('Published warning')).toBeNull();
    expect(screen.queryByText('Approved warning')).toBeNull();
  });

  it('orders the most severe warning first', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: QUEUE },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });

    await screen.findByText('Critical flood at SH004');
    const items = screen.getAllByRole('listitem');
    expect(within(items[0]).getByText('Critical flood at SH004')).toBeInTheDocument();
  });

  it('reads the active queue from the URL so a view can be shared', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: QUEUE },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings?status=published' });

    expect(await screen.findByText('Published warning')).toBeInTheDocument();
    expect(screen.queryByText('Critical flood at SH004')).toBeNull();
  });

  it('applies severity and risk-type filters from the URL', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: QUEUE },
    });

    renderWithProviders(<WarningCenterPage />, {
      route: '/app/warnings?status=all&severity=critical&type=river_flood',
    });

    expect(await screen.findByText('Critical flood at SH004')).toBeInTheDocument();
    expect(screen.queryByText('Watch drought in Baidoa')).toBeNull();
  });

  it('filters by search text', async () => {
    const user = userEvent.setup();
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: QUEUE },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings?status=all' });

    await screen.findByText('Critical flood at SH004');
    await user.type(screen.getByLabelText(/search warnings/i), 'Baidoa');

    await waitFor(() => {
      expect(screen.queryByText('Critical flood at SH004')).toBeNull();
    });
    expect(screen.getByText('Watch drought in Baidoa')).toBeInTheDocument();
  });

  it('offers no filter for a workflow state the backend does not define', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: QUEUE },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });

    await screen.findByRole('tablist');
    // The platform workflow has no rejected, held or suppressed state.
    expect(screen.queryByRole('tab', { name: /rejected/i })).toBeNull();
    expect(screen.queryByRole('tab', { name: /held/i })).toBeNull();
    expect(screen.queryByRole('tab', { name: /suppressed/i })).toBeNull();
  });

  it('states an empty queue rather than showing a blank list', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: [] },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });
    expect(await screen.findByText(/no warnings require review/i)).toBeInTheDocument();
  });
});

/* ---------------------------------------------------------- review workspace -- */

function reviewRoutes(capabilities: string[], status = 'in_review') {
  return {
    '/auth/me': { body: principal(capabilities) },
    '/alerts/55555555-5555-4555-8555-555555555555': {
      body: alertDetail({ status: status as never }),
    },
    '/alerts': { body: [alert({ status: status as never })] },
    '/risks': { body: [riskSignal()] },
    '/exposure/assessments': { body: [] },
    '/early-actions/items': { body: [] },
  };
}

const REVIEW_ROUTE = '/app/warnings/55555555-5555-4555-8555-555555555555';
const REVIEW_PATH = '/app/warnings/:alertId';

describe('warning review workspace', () => {
  it('renders the full evidence structure', async () => {
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    expect(await screen.findByText('Warning summary')).toBeInTheDocument();
    expect(screen.getByText(/evidence, data quality and model/i)).toBeInTheDocument();
    expect(screen.getByText('Decision')).toBeInTheDocument();
  });

  it('shows the governance chain and marks unapproved output as AI-generated', async () => {
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    expect(await screen.findByLabelText(/governance progress/i)).toBeInTheDocument();
    // The sentence emphasises "not" in its own element, so assert on the
    // rendered text content rather than a single text node.
    expect(document.body.textContent).toContain(
      'has not been approved as an official warning',
    );
    expect(document.body.textContent).toContain('model-generated intelligence under review');
  });

  it('translates model drivers into operational language', async () => {
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    expect(
      await screen.findByText(/vegetation index is below its seasonal normal/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/recent rainfall is below normal/i)).toBeInTheDocument();
    // Raw feature internals stay behind a disclosure.
    expect(screen.getByText(/technical attribution/i)).toBeInTheDocument();
    expect(screen.queryByText('ndvi_anomaly_90d')).toBeNull();
  });

  it('offers only the transitions the backend defines for this state', async () => {
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    // From in_review: verification_required and approved. Nothing else.
    expect(await screen.findByRole('button', { name: /request field verification/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^reject$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^hold$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^publish$/i })).toBeNull();
  });

  it('explains why no reject or hold action exists', async () => {
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });
    expect(
      await screen.findByText(/why is there no reject or hold action/i),
    ).toBeInTheDocument();
  });

  it('hides decision actions from a role that lacks the capability', async () => {
    // A regional analyst may review but not approve.
    stub = stubFetch(reviewRoutes(REGIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    // A regional analyst may request verification but may not approve.
    expect(
      await screen.findByRole('button', { name: /request field verification/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^approve$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^publish$/i })).toBeNull();
  });

  it('states the boundary for a read-only role instead of disabled buttons', async () => {
    stub = stubFetch(reviewRoutes(VIEWER_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    expect(await screen.findByText(/read-only for warnings/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^approve$/i })).toBeNull();
  });

  it('requires explicit confirmation before approving', async () => {
    const user = userEvent.setup();
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    await user.click(await screen.findByRole('button', { name: /^approve$/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/authorised institutional decision/i)).toBeInTheDocument();

    // Nothing was submitted merely by opening the confirmation.
    expect(stub.calls.some((call) => call.startsWith('POST'))).toBe(false);
  });

  it('never publishes on a single click', async () => {
    const user = userEvent.setup();
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES, 'approved'));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    await user.click(await screen.findByRole('button', { name: /^publish$/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    expect(stub.calls.some((call) => call.includes('/transitions'))).toBe(false);
  });

  it('submits the transition only after confirmation', async () => {
    const user = userEvent.setup();
    stub = stubFetch({
      ...reviewRoutes(NATIONAL_ANALYST_CAPABILITIES),
      'POST /transitions': { body: alertDetail({ status: 'approved' }) },
    });

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    await user.click(await screen.findByRole('button', { name: /^approve$/i }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /^approve$/i }));

    await waitFor(() => {
      expect(stub?.calls.some((call) => call.includes('POST') && call.includes('/transitions'))).toBe(
        true,
      );
    });
  });

  it('reports a conflict honestly instead of implying the decision succeeded', async () => {
    const user = userEvent.setup();
    stub = stubFetch({
      ...reviewRoutes(NATIONAL_ANALYST_CAPABILITIES),
      'POST /transitions': {
        status: 409,
        body: { detail: 'in_review cannot transition to approved' },
      },
    });

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    await user.click(await screen.findByRole('button', { name: /^approve$/i }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /^approve$/i }));

    expect(await screen.findByText(/changed state while you were reviewing/i)).toBeInTheDocument();
  });

  it('cancels without submitting anything', async () => {
    const user = userEvent.setup();
    stub = stubFetch(reviewRoutes(NATIONAL_ANALYST_CAPABILITIES));

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    await user.click(await screen.findByRole('button', { name: /^approve$/i }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    expect(stub.calls.some((call) => call.includes('/transitions'))).toBe(false);
  });

  it('surfaces a suppression reason rather than hiding it', async () => {
    stub = stubFetch({
      ...reviewRoutes(NATIONAL_ANALYST_CAPABILITIES),
      '/risks': {
        body: [
          riskSignal({
            provenance: {
              model_id: 'flood-early-warning',
              model_version: '1.1.0',
              data_quality: 'STALE',
              suppression_reason: 'Critical river observation is stale.',
            },
          }),
        ],
      },
    });

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    expect(await screen.findByText(/warning suppressed/i)).toBeInTheDocument();
    expect(screen.getByText(/critical river observation is stale/i)).toBeInTheDocument();
  });

  it('reports a withheld probability rather than showing zero', async () => {
    stub = stubFetch({
      ...reviewRoutes(NATIONAL_ANALYST_CAPABILITIES),
      '/risks': { body: [riskSignal({ score: null, level: 'normal' })] },
    });

    renderWithProviders(<WarningReviewPage />, { route: REVIEW_ROUTE, path: REVIEW_PATH });

    expect(await screen.findByText('Withheld')).toBeInTheDocument();
    expect(
      screen.getByText(/no probability was issued for this record/i),
    ).toBeInTheDocument();
  });
});
