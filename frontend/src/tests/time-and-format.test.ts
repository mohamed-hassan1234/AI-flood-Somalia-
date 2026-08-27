/**
 * Timezone and value formatting.
 *
 * The timezone tests exist because rendering a UTC instant as Mogadishu local
 * time is a three-hour error in a flood warning — an operational fault, not a
 * cosmetic one.
 */

import { describe, expect, it } from 'vitest';

import {
  OPERATIONAL_TIMEZONE,
  ageInHours,
  formatDate,
  formatDateTime,
  formatRelative,
  formatTime,
  fromDateInputValue,
  nextScheduledRun,
  parseInstant,
  toDateInputValue,
} from '../lib/time';
import {
  NOT_REPORTED,
  formatCadence,
  formatCompact,
  formatCount,
  formatProbability,
  formatSignedPercent,
  humanise,
  renderUnknown,
  safeLabel,
} from '../lib/format';

describe('operational timezone', () => {
  it('renders UTC instants in Africa/Mogadishu, not UTC', () => {
    // 05:00 UTC is 08:00 in Mogadishu (UTC+03:00, no DST).
    expect(formatDateTime('2026-08-27T05:00:00Z')).toBe('27 Aug 2026, 08:00 EAT');
    expect(formatTime('2026-08-27T05:00:00Z')).toBe('08:00 EAT');
  });

  it('always labels the zone so a timestamp is never ambiguous', () => {
    expect(formatDateTime('2026-08-27T05:00:00Z')).toContain('EAT');
    expect(formatTime('2026-08-27T05:00:00Z')).toContain('EAT');
  });

  it('rolls the date correctly across the Mogadishu day boundary', () => {
    // 22:30 UTC on the 26th is 01:30 on the 27th in Mogadishu.
    expect(formatDateTime('2026-08-26T22:30:00Z')).toBe('27 Aug 2026, 01:30 EAT');
    expect(formatDate('2026-08-26T22:30:00Z')).toBe('27 Aug 2026');
  });

  it('treats a naive backend timestamp as UTC', () => {
    const naive = parseInstant('2026-08-27T05:00:00');
    const explicit = parseInstant('2026-08-27T05:00:00Z');
    expect(naive?.getTime()).toBe(explicit?.getTime());
  });

  it('returns null for absent or unparseable values instead of Invalid Date', () => {
    expect(parseInstant(null)).toBeNull();
    expect(parseInstant(undefined)).toBeNull();
    expect(parseInstant('')).toBeNull();
    expect(parseInstant('not a date')).toBeNull();
  });

  it('renders a missing timestamp as not-reported', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatRelative(null)).toBe('—');
  });

  it('declares the operational timezone explicitly', () => {
    expect(OPERATIONAL_TIMEZONE).toBe('Africa/Mogadishu');
  });
});

describe('relative time', () => {
  const now = new Date('2026-08-27T12:00:00Z');

  it('describes recent instants in operational units', () => {
    expect(formatRelative('2026-08-27T11:59:40Z', now)).toBe('just now');
    expect(formatRelative('2026-08-27T11:30:00Z', now)).toBe('30m ago');
    expect(formatRelative('2026-08-27T09:00:00Z', now)).toBe('3h ago');
    expect(formatRelative('2026-08-21T12:00:00Z', now)).toBe('6d ago');
  });

  it('falls back to an absolute date beyond a month', () => {
    expect(formatRelative('2026-06-01T12:00:00Z', now)).toBe('01 Jun 2026');
  });

  it('computes age in hours for freshness checks', () => {
    expect(ageInHours('2026-08-27T09:00:00Z', now)).toBeCloseTo(3);
    expect(ageInHours(null)).toBeNull();
  });
});

describe('scheduled run', () => {
  it('reports the next 08:00 Mogadishu run as a future instant', () => {
    // 04:00 UTC is 07:00 Mogadishu, so today's 08:00 run is still ahead.
    const next = nextScheduledRun(new Date('2026-08-27T04:00:00Z'));
    expect(formatTime(next)).toBe('08:00 EAT');
    expect(next.getTime()).toBeGreaterThan(new Date('2026-08-27T04:00:00Z').getTime());
  });

  it('rolls to the following day once the run time has passed', () => {
    // 06:00 UTC is 09:00 Mogadishu — today's run has already happened.
    const next = nextScheduledRun(new Date('2026-08-27T06:00:00Z'));
    expect(formatDate(next)).toBe('28 Aug 2026');
    expect(formatTime(next)).toBe('08:00 EAT');
  });
});

describe('date inputs', () => {
  it('round-trips a Mogadishu calendar date', () => {
    expect(toDateInputValue('2026-08-26T22:30:00Z')).toBe('2026-08-27');
    const start = fromDateInputValue('2026-08-27');
    expect(start).toBe('2026-08-26T21:00:00.000Z');
  });

  it('rejects malformed input rather than guessing', () => {
    expect(fromDateInputValue('27/08/2026')).toBeUndefined();
    expect(fromDateInputValue('')).toBeUndefined();
  });
});

describe('value formatting', () => {
  it('distinguishes a measured zero from an absent value', () => {
    expect(formatCount(0)).toBe('0');
    expect(formatCount(null)).toBe(NOT_REPORTED);
    expect(formatProbability(0)).toBe('0%');
    expect(formatProbability(null)).toBe(NOT_REPORTED);
    expect(formatProbability(undefined)).toBe(NOT_REPORTED);
  });

  it('never renders NaN', () => {
    expect(formatCount(Number.NaN)).toBe(NOT_REPORTED);
    expect(formatProbability(Number.NaN)).toBe(NOT_REPORTED);
    expect(formatCompact(Number.NaN)).toBe(NOT_REPORTED);
    expect(renderUnknown(Number.POSITIVE_INFINITY)).toBe(NOT_REPORTED);
  });

  it('renders probability as a whole percentage', () => {
    expect(formatProbability(0.82)).toBe('82%');
    expect(formatProbability(0.005)).toBe('1%');
    expect(formatProbability(1)).toBe('100%');
  });

  it('signs driver contributions with a real minus sign', () => {
    expect(formatSignedPercent(0.31)).toBe('+31%');
    expect(formatSignedPercent(-0.12)).toBe('−12%');
    expect(formatSignedPercent(0)).toBe('0%');
    expect(formatSignedPercent(null)).toBe(NOT_REPORTED);
  });

  it('respects source-specific cadence rather than assuming daily', () => {
    expect(formatCadence(30)).toBe('Every 30 min');
    expect(formatCadence(1440)).toBe('Every 1 d');
    expect(formatCadence(10080)).toBe('Every 1 wk');
    // An IPC-style assessment cycle is months, not a late daily feed.
    expect(formatCadence(129600)).toBe('Every 3 mo');
    expect(formatCadence(null)).toBe('Not declared');
  });

  it('humanises machine tokens', () => {
    expect(humanise('river_flood')).toBe('River flood');
    expect(humanise('RIVER_LEVEL_NEAR_THRESHOLD')).toBe('River level near threshold');
    expect(humanise(null)).toBe(NOT_REPORTED);
    expect(humanise('')).toBe(NOT_REPORTED);
  });

  it('never renders [object Object] from an open payload', () => {
    expect(renderUnknown({ nested: true })).not.toContain('[object Object]');
    expect(safeLabel({ nested: true })).toBe(NOT_REPORTED);
    expect(safeLabel(['a'])).toBe(NOT_REPORTED);
    expect(safeLabel('drought')).toBe('drought');
    expect(safeLabel(42)).toBe('42');
  });
});
