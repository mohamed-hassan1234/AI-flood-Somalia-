/**
 * Value formatting for a data-dense operational interface.
 *
 * Every formatter distinguishes "genuinely zero" from "not reported". A
 * missing value renders as an em dash, never as `0`, `null`, `NaN` or an
 * empty cell — mistaking absent evidence for a measured zero is exactly the
 * failure mode this product cannot afford.
 */

export const NOT_REPORTED = '—';

function isMissing(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value);
}

/**
 * Model probability rendered as a whole percentage.
 *
 * Deliberately not rounded to decimals: the calibration of these models does
 * not justify presenting sub-percent precision, and false precision invites
 * over-reading of small differences between units.
 */
export function formatProbability(value: number | null | undefined): string {
  if (isMissing(value)) return NOT_REPORTED;
  return `${Math.round(value * 100)}%`;
}

/** Confidence on the same scale as probability, with a distinct caller. */
export function formatConfidence(value: number | null | undefined): string {
  if (isMissing(value)) return NOT_REPORTED;
  return `${Math.round(value * 100)}%`;
}

/** Whole-number count with thousands separators. */
export function formatCount(value: number | null | undefined): string {
  if (isMissing(value)) return NOT_REPORTED;
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(value);
}

/**
 * Population figures abbreviated for metric cards (`1.2M`, `18.8K`).
 * Use `formatCount` wherever the exact figure matters, such as detail panels.
 */
export function formatCompact(value: number | null | undefined): string {
  if (isMissing(value)) return NOT_REPORTED;
  if (Math.abs(value) < 1000) return formatCount(Math.round(value));
  return new Intl.NumberFormat('en-GB', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

/** Measurement with a unit, e.g. `4.32 m`. */
export function formatMeasurement(
  value: number | null | undefined,
  unit: string | null | undefined,
  digits = 2,
): string {
  if (isMissing(value)) return NOT_REPORTED;
  const number = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
  return unit ? `${number} ${unit}` : number;
}

/** Signed delta for driver contributions, e.g. `+31%` / `−12%`. */
export function formatSignedPercent(value: number | null | undefined): string {
  if (isMissing(value)) return NOT_REPORTED;
  const points = Math.round(value * 100);
  if (points === 0) return '0%';
  // U+2212 MINUS SIGN reads correctly at small sizes; ASCII hyphen does not.
  return points > 0 ? `+${points}%` : `−${Math.abs(points)}%`;
}

/**
 * Turns a machine token into a readable label:
 * `river_flood` → `River flood`, `RIVER_LEVEL_NEAR_THRESHOLD` → `River level near threshold`.
 */
export function humanise(value: string | null | undefined): string {
  if (!value) return NOT_REPORTED;
  const spaced = value.replaceAll('_', ' ').trim();
  if (!spaced) return NOT_REPORTED;
  const lower = spaced === spaced.toUpperCase() ? spaced.toLowerCase() : spaced;
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** Truncates a UUID for display while keeping it recognisable. */
export function shortId(value: string | null | undefined, length = 8): string {
  if (!value) return NOT_REPORTED;
  return value.length <= length ? value : value.slice(0, length);
}

/** `12 districts` / `1 district` — count with a correctly pluralised noun. */
export function pluralise(count: number, singular: string, plural?: string): string {
  const noun = count === 1 ? singular : (plural ?? `${singular}s`);
  return `${formatCount(count)} ${noun}`;
}

/** Minutes-based cadence rendered as an operator-readable interval. */
export function formatCadence(minutes: number | null | undefined): string {
  if (isMissing(minutes) || minutes <= 0) return 'Not declared';
  if (minutes < 60) return `Every ${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 24) return `Every ${trim(hours)} h`;
  const days = hours / 24;
  if (days < 7) return `Every ${trim(days)} d`;
  const weeks = days / 7;
  if (weeks < 5) return `Every ${trim(weeks)} wk`;
  const months = days / 30.44;
  return `Every ${trim(months)} mo`;
}

function trim(value: number): string {
  // Round first, then drop a trailing `.0`: 2.96 months is "3 mo", not "3.0 mo".
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** Joins non-empty parts with a middle dot for compact metadata rows. */
export function metaJoin(...parts: Array<string | null | undefined | false>): string {
  return parts.filter((part): part is string => Boolean(part)).join(' · ');
}

/**
 * Coerces an unknown JSON value into something safely renderable.
 * Driver and provenance payloads are open `dict[str, object]` on the wire, so
 * anything can appear; this never throws and never renders `[object Object]`.
 */
export function renderUnknown(value: unknown): string {
  if (value === null || value === undefined) return NOT_REPORTED;
  if (typeof value === 'string') return value || NOT_REPORTED;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return NOT_REPORTED;
    return Number.isInteger(value) ? formatCount(value) : String(Number(value.toFixed(4)));
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) {
    return value.length ? value.map(renderUnknown).join(', ') : NOT_REPORTED;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return NOT_REPORTED;
  }
}

/**
 * Safely stringifies a value of unknown shape for use in a label.
 *
 * Chart libraries type their formatter callbacks with very wide parameters
 * (`ReactNode`, `ValueType`), so a bare `String(value)` there can silently
 * render "[object Object]". This narrows to the primitives that actually
 * occur and reports anything else as not-reported instead.
 */
export function safeLabel(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : NOT_REPORTED;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return NOT_REPORTED;
}
