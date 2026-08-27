/**
 * Risk semantics — the rules that keep severity meaning consistent and honest
 * across the whole product.
 */

import { describe, expect, it } from 'vitest';

import {
  ALERT_TRANSITIONS,
  TRANSITION_CAPABILITY,
  availableTransitions,
  domain,
  health,
  highestSeverity,
  quality,
  severity,
  toSeverity,
  workflow,
} from '../lib/risk';

describe('severity normalisation', () => {
  it('maps every backend RiskLevel to a descriptor', () => {
    for (const level of ['normal', 'watch', 'warning', 'critical'] as const) {
      expect(severity(level).key).toBe(level);
    }
  });

  it('treats the Phase 03 contract spelling SEVERE as the top severity band', () => {
    // The operational contract writes SEVERE; the API enum writes `critical`.
    // Resolving SEVERE to `unknown` would understate a real emergency.
    expect(toSeverity('SEVERE')).toBe('critical');
    expect(toSeverity('severe')).toBe('critical');
    expect(severity('SEVERE').label).toBe('CRITICAL');
  });

  it('reports a withheld prediction as unknown, never as normal', () => {
    expect(toSeverity(null)).toBe('unknown');
    expect(toSeverity(undefined)).toBe('unknown');
    expect(toSeverity('INSUFFICIENT')).toBe('unknown');
    expect(toSeverity('not-a-level')).toBe('unknown');
    // An absent prediction must never read as "no elevated risk".
    expect(toSeverity(null)).not.toBe('normal');
  });

  it('ranks unknown below normal so it never inflates a Watch+ count', () => {
    expect(severity('unknown').rank).toBeLessThan(severity('normal').rank);
    expect(severity('critical').rank).toBeGreaterThan(severity('warning').rank);
    expect(severity('warning').rank).toBeGreaterThan(severity('watch').rank);
  });

  it('communicates every severity with a glyph and label, not colour alone', () => {
    for (const level of ['normal', 'watch', 'warning', 'critical', 'unknown'] as const) {
      const descriptor = severity(level);
      expect(descriptor.glyph.length).toBeGreaterThan(0);
      expect(descriptor.label).toMatch(/^[A-Z]+$/);
      expect(descriptor.meaning.length).toBeGreaterThan(10);
    }
  });

  it('picks the highest severity from a mixed set', () => {
    expect(highestSeverity(['normal', 'watch', 'critical', 'warning'])).toBe('critical');
    expect(highestSeverity(['normal', 'watch'])).toBe('watch');
    expect(highestSeverity([])).toBe('unknown');
    expect(highestSeverity([null, undefined])).toBe('unknown');
  });
});

describe('domain scope statements', () => {
  it('ties river flood to gauges and denies nationwide or flash-flood coverage', () => {
    const descriptor = domain('river_flood');
    expect(descriptor.scope).toBe('station');
    expect(descriptor.scopeStatement).toMatch(/gaug/i);
    expect(descriptor.scopeStatement).toMatch(/not Somalia-wide/i);
    expect(descriptor.scopeStatement).toMatch(/flash/i);
  });

  it('keeps food security at region level and separate from IPC', () => {
    const descriptor = domain('food_security_deterioration');
    expect(descriptor.scope).toBe('region');
    expect(descriptor.scopeStatement).toMatch(/not an official IPC classification/i);
    expect(descriptor.scopeStatement).toMatch(/district/i);
  });

  it('describes drought as an early-warning signal, not a famine forecast', () => {
    const descriptor = domain('drought');
    expect(descriptor.scope).toBe('district');
    expect(descriptor.scopeStatement).toMatch(/not a famine forecast/i);
  });
});

describe('alert workflow', () => {
  it('mirrors the backend transition table exactly', () => {
    // Source of truth: backend/app/modules/alerts/service.py::TRANSITIONS
    expect(ALERT_TRANSITIONS).toEqual({
      draft: ['in_review'],
      in_review: ['verification_required', 'approved'],
      verification_required: ['verified'],
      verified: ['approved'],
      approved: ['published'],
      published: ['resolved'],
      resolved: [],
    });
  });

  it('mirrors the backend capability requirements exactly', () => {
    // Source of truth: alerts/service.py::REQUIRED_CAPABILITY
    expect(TRANSITION_CAPABILITY.in_review).toBe('alerts.review');
    expect(TRANSITION_CAPABILITY.verification_required).toBe('field_tasks.create');
    expect(TRANSITION_CAPABILITY.verified).toBe('field_reports.verify');
    expect(TRANSITION_CAPABILITY.approved).toBe('alerts.approve');
    expect(TRANSITION_CAPABILITY.published).toBe('alerts.publish');
    expect(TRANSITION_CAPABILITY.resolved).toBe('alerts.resolve');
  });

  it('offers no transition the backend does not define', () => {
    // There is no reject or hold transition in the platform workflow, so the
    // UI must not offer one from any state.
    const everyTarget = Object.values(ALERT_TRANSITIONS).flat();
    expect(everyTarget).not.toContain('rejected');
    expect(everyTarget).not.toContain('held');
    expect(everyTarget).not.toContain('suppressed');
  });

  it('distinguishes model output from human-authorised warning', () => {
    expect(workflow('draft').humanApproved).toBe(false);
    expect(workflow('in_review').humanApproved).toBe(false);
    expect(workflow('verified').humanApproved).toBe(false);
    expect(workflow('approved').humanApproved).toBe(true);
    expect(workflow('published').humanApproved).toBe(true);
    expect(workflow('published').published).toBe(true);
    expect(workflow('approved').published).toBe(false);
  });
});

describe('availableTransitions', () => {
  it('returns nothing when the principal holds no relevant capability', () => {
    expect(availableTransitions('in_review', new Set(['alerts.read']))).toEqual([]);
  });

  it('returns only the transitions the principal may perform', () => {
    const reviewerOnly = availableTransitions('in_review', new Set(['field_tasks.create']));
    expect(reviewerOnly.map((action) => action.target)).toEqual(['verification_required']);

    const approver = availableTransitions('in_review', new Set(['alerts.approve']));
    expect(approver.map((action) => action.target)).toEqual(['approved']);
  });

  it('marks approve, publish and resolve as consequential', () => {
    const approve = availableTransitions('in_review', new Set(['alerts.approve']))[0];
    expect(approve.consequential).toBe(true);
    expect(approve.consequence).toMatch(/authorised/i);

    const publish = availableTransitions('approved', new Set(['alerts.publish']))[0];
    expect(publish.consequential).toBe(true);
    expect(publish.consequence).toMatch(/cannot be undone/i);
  });

  it('offers nothing from the terminal resolved state', () => {
    const all = new Set(Object.values(TRANSITION_CAPABILITY).filter(Boolean) as string[]);
    expect(availableTransitions('resolved', all)).toEqual([]);
  });
});

describe('data health and quality descriptors', () => {
  it('treats every non-fresh health status as degraded', () => {
    expect(health('fresh').degraded).toBe(false);
    for (const status of ['delayed', 'stale', 'failed', 'unknown']) {
      expect(health(status).degraded).toBe(true);
    }
  });

  it('falls back to unknown rather than assuming a source is fresh', () => {
    expect(health(null).key).toBe('unknown');
    expect(health('something-new').key).toBe('unknown');
    expect(health(undefined).degraded).toBe(true);
  });

  it('reports missing data quality as not-reported, never as good', () => {
    expect(quality(null).key).toBe('unknown');
    expect(quality(null).label).toBe('NOT REPORTED');
    expect(quality('GOOD').key).toBe('good');
    expect(quality('INSUFFICIENT').key).toBe('insufficient');
  });
});
