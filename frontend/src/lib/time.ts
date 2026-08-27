/**
 * Time handling for an operational service that runs on Somalia time.
 *
 * The platform's operational timezone is Africa/Mogadishu (UTC+03:00, no DST).
 * The API returns ISO-8601 instants. The single most dangerous mistake this
 * module exists to prevent is rendering a UTC instant as if it were local
 * Mogadishu time — a three-hour error in a flood warning is operationally
 * significant, so every formatter here is explicit about its zone and every
 * rendered timestamp carries a zone label.
 */

export const OPERATIONAL_TIMEZONE = 'Africa/Mogadishu';
/** Short label appended to rendered timestamps so the zone is never implicit. */
export const OPERATIONAL_TIMEZONE_LABEL = 'EAT';

/**
 * Parses an API instant. Returns `null` for absent or unparseable values
 * rather than an Invalid Date, so callers must handle the missing case.
 *
 * Naive timestamps (no trailing `Z` or offset) are treated as UTC, matching
 * how the backend serialises `datetime` columns that were stored naive.
 */
export function parseInstant(value: string | null | undefined): Date | null {
  if (!value) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const normalised = hasZone ? value : `${value}Z`;
  const parsed = new Date(normalised);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatter(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: OPERATIONAL_TIMEZONE,
    ...options,
  });
}

/** `27 Aug 2026, 14:30 EAT` — the default for operational timestamps. */
export function formatDateTime(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseInstant(value);
  if (!date) return '—';
  const text = formatter({
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
  return `${text} ${OPERATIONAL_TIMEZONE_LABEL}`;
}

/** `27 Aug 2026` — for dates where time of day carries no meaning. */
export function formatDate(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseInstant(value);
  if (!date) return '—';
  return formatter({ day: '2-digit', month: 'short', year: 'numeric' }).format(date);
}

/** `14:30 EAT` — for same-day operational context such as a run time. */
export function formatTime(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseInstant(value);
  if (!date) return '—';
  const text = formatter({ hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
  return `${text} ${OPERATIONAL_TIMEZONE_LABEL}`;
}

/** Machine-readable value for a `<time dateTime>` attribute. */
export function isoAttribute(value: string | Date | null | undefined): string | undefined {
  const date = value instanceof Date ? value : parseInstant(value);
  return date ? date.toISOString() : undefined;
}

/**
 * Compact elapsed-time label: `just now`, `14m ago`, `3h ago`, `6d ago`.
 * Falls back to an absolute date beyond 30 days, where relative phrasing
 * stops being useful for judging freshness.
 */
export function formatRelative(
  value: string | Date | null | undefined,
  now: Date = new Date(),
): string {
  const date = value instanceof Date ? value : parseInstant(value);
  if (!date) return '—';

  const deltaMs = now.getTime() - date.getTime();
  const future = deltaMs < 0;
  const seconds = Math.abs(deltaMs) / 1000;

  if (seconds < 45) return future ? 'in moments' : 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return future ? `in ${minutes}m` : `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return future ? `in ${hours}h` : `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days <= 30) return future ? `in ${days}d` : `${days}d ago`;

  return formatDate(date);
}

/** Age in whole hours, or `null` when the instant is missing. */
export function ageInHours(
  value: string | Date | null | undefined,
  now: Date = new Date(),
): number | null {
  const date = value instanceof Date ? value : parseInstant(value);
  if (!date) return null;
  return (now.getTime() - date.getTime()) / 3_600_000;
}

/**
 * Next scheduled operational run, expressed in Mogadishu time.
 *
 * The platform's documented cadence is a daily 08:00 Africa/Mogadishu run.
 * This is a *schedule* derived from configuration, never a claim that the run
 * succeeded — callers must pair it with the actual last-run status from the
 * API so a stalled pipeline is never masked by a healthy-looking schedule.
 */
export function nextScheduledRun(now: Date = new Date(), atHour = 8): Date {
  // Mogadishu is UTC+03:00 year-round, so the offset arithmetic is exact and
  // needs no DST handling.
  const OFFSET_MINUTES = 180;
  const nowLocalMs = now.getTime() + OFFSET_MINUTES * 60_000;
  const local = new Date(nowLocalMs);

  const runLocal = new Date(
    Date.UTC(
      local.getUTCFullYear(),
      local.getUTCMonth(),
      local.getUTCDate(),
      atHour,
      0,
      0,
      0,
    ),
  );
  if (runLocal.getTime() <= nowLocalMs) {
    runLocal.setUTCDate(runLocal.getUTCDate() + 1);
  }
  return new Date(runLocal.getTime() - OFFSET_MINUTES * 60_000);
}

/** ISO `YYYY-MM-DD` in Mogadishu time — for date inputs and range filters. */
export function toDateInputValue(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseInstant(value);
  if (!date) return '';
  const parts = formatter({ day: '2-digit', month: '2-digit', year: 'numeric' })
    .formatToParts(date)
    .reduce<Record<string, string>>((acc, part) => {
      acc[part.type] = part.value;
      return acc;
    }, {});
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/** Start-of-day UTC instant for a `YYYY-MM-DD` value entered in Mogadishu time. */
export function fromDateInputValue(value: string, endOfDay = false): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const suffix = endOfDay ? 'T23:59:59+03:00' : 'T00:00:00+03:00';
  const parsed = new Date(`${value}${suffix}`);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}
