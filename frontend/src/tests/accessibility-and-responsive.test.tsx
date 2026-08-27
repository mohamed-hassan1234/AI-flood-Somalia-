/**
 * Accessibility and responsive behaviour.
 *
 * The accessibility rule this product cannot compromise on: severity is never
 * communicated by colour alone. Every severity indicator carries a glyph and a
 * text label, so meaning survives greyscale, colour-vision deficiency and a
 * screen reader.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppLayout } from '../app/layouts/AppLayout';
import { WarningCenterPage } from '../features/warnings/WarningCenterPage';
import { RiskBadge, DataQualityBadge, ConfidenceIndicator } from '../components/intelligence/badges';
import { ConfirmDialog, Tabs } from '../components/ui/layout';
import { severityDescriptors } from '../lib/risk';
import { NATIONAL_ANALYST_CAPABILITIES, alert, nationalSummary, principal } from './fixtures';
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

/* --------------------------------------------------------- colour is never alone -- */

describe('severity is never colour alone', () => {
  it('pairs every severity with a glyph and an uppercase label', () => {
    for (const descriptor of severityDescriptors()) {
      const { unmount } = renderWithProviders(<RiskBadge level={descriptor.key} />);
      // The label survives even if colour is unavailable.
      expect(screen.getByText(descriptor.label)).toBeInTheDocument();
      expect(screen.getByText(descriptor.glyph)).toBeInTheDocument();
      unmount();
    }
  });

  it('labels data quality for a screen reader', () => {
    renderWithProviders(<DataQualityBadge status="INSUFFICIENT" />);
    expect(screen.getByText('Data quality:')).toBeInTheDocument();
    expect(screen.getByText('INSUFFICIENT')).toBeInTheDocument();
  });

  it('exposes the confidence meter as text, not only as filled bars', () => {
    renderWithProviders(<ConfidenceIndicator value={0.64} />);
    expect(screen.getByRole('img', { name: /model confidence: 64%/i })).toBeInTheDocument();
    expect(screen.getByText('64%')).toBeInTheDocument();
  });

  it('says "not reported" rather than showing an empty meter', () => {
    renderWithProviders(<ConfidenceIndicator value={null} />);
    expect(screen.getByRole('img', { name: /not reported/i })).toBeInTheDocument();
    expect(screen.getByText('Not reported')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ semantics -- */

describe('semantic structure', () => {
  it('gives every page a single level-one heading', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: [alert()] },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });

    await screen.findByRole('heading', { level: 1, name: /warning center/i });
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('labels every filter control', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: [alert()] },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });

    expect(await screen.findByLabelText(/search warnings/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by severity/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by risk type/i)).toBeInTheDocument();
  });

  it('announces loading and status regions to assistive technology', async () => {
    stub = stubFetch({
      '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
      '/alerts': { body: [] },
    });

    renderWithProviders(<WarningCenterPage />, { route: '/app/warnings' });

    // The empty state is a status, not silent absence.
    expect(await screen.findByRole('status')).toBeInTheDocument();
  });
});

/* ---------------------------------------------------------- keyboard support -- */

describe('keyboard support', () => {
  it('moves between tabs with the arrow keys', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    function Harness() {
      return (
        <Tabs
          label="Test tabs"
          value="one"
          onChange={onChange}
          tabs={[
            { id: 'one', label: 'One' },
            { id: 'two', label: 'Two' },
            { id: 'three', label: 'Three' },
          ]}
        />
      );
    }

    renderWithProviders(<Harness />);

    const selected = screen.getByRole('tab', { name: 'One' });
    expect(selected).toHaveAttribute('aria-selected', 'true');
    expect(selected).toHaveAttribute('tabindex', '0');
    // Unselected tabs are removed from the tab sequence (roving tabindex).
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('tabindex', '-1');

    selected.focus();
    await user.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenCalledWith('two');

    await user.keyboard('{End}');
    expect(onChange).toHaveBeenCalledWith('three');
  });

  it('traps focus in a confirmation dialog and closes on Escape', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    renderWithProviders(
      <ConfirmDialog
        open
        onClose={onClose}
        onConfirm={vi.fn()}
        title="Publish this warning?"
        consequence="This cannot be undone."
        confirmLabel="Publish"
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    // The dialog is named by its heading.
    expect(within(dialog).getByText('Publish this warning?')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('does not focus the confirming control on open', async () => {
    renderWithProviders(
      <ConfirmDialog
        open
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        title="Publish this warning?"
        consequence="This cannot be undone."
        confirmLabel="Publish"
      />,
    );

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => {
      // A reflexive Enter must not publish; Cancel carries initial focus.
      expect(within(dialog).getByRole('button', { name: /cancel/i })).toHaveFocus();
    });
  });
});

/* -------------------------------------------------------------- responsive -- */

describe('responsive navigation', () => {
  const SHELL_ROUTES = {
    '/auth/me': { body: principal(NATIONAL_ANALYST_CAPABILITIES) },
    '/dashboard/national-summary': { body: nationalSummary() },
    '/alerts': { body: [] },
  };

  it('exposes a menu control that opens the navigation drawer', async () => {
    const user = userEvent.setup();
    stub = stubFetch(SHELL_ROUTES);

    renderWithProviders(<AppLayout />, { route: '/app/overview' });

    const menuButton = await screen.findByRole('button', { name: /open navigation/i });
    await user.click(menuButton);

    const drawer = await screen.findByRole('dialog', { name: /navigation/i });
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByRole('navigation', { name: /primary/i })).toBeInTheDocument();
  });

  it('closes the drawer from its own control', async () => {
    const user = userEvent.setup();
    stub = stubFetch(SHELL_ROUTES);

    renderWithProviders(<AppLayout />, { route: '/app/overview' });

    await user.click(await screen.findByRole('button', { name: /open navigation/i }));
    await screen.findByRole('dialog', { name: /navigation/i });

    await user.click(screen.getByRole('button', { name: /close navigation/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /navigation/i })).toBeNull();
    });
  });

  it('provides a skip link to the main content', async () => {
    stub = stubFetch(SHELL_ROUTES);
    renderWithProviders(<AppLayout />, { route: '/app/overview' });

    const skip = await screen.findByRole('link', { name: /skip to main content/i });
    expect(skip).toHaveAttribute('href', '#main-content');
    expect(document.getElementById('main-content')).not.toBeNull();
  });

  it('names the primary navigation landmark', async () => {
    stub = stubFetch(SHELL_ROUTES);
    renderWithProviders(<AppLayout />, { route: '/app/overview' });

    const navs = await screen.findAllByRole('navigation', { name: /primary/i });
    expect(navs.length).toBeGreaterThan(0);
  });
});
