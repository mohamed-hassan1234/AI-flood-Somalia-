/**
 * Semantic status badges.
 *
 * Every badge here follows the same accessibility contract: a glyph, a text
 * label and a colour, so severity survives greyscale printing, colour-vision
 * deficiency and screen readers. Nothing in this file may be used decoratively
 * — the colours carry operational meaning.
 */

import type { ReactNode } from 'react';
import { Clock, ShieldCheck, ShieldAlert } from 'lucide-react';

import { Badge, cx } from '../ui/primitives';
import {
  CLASSIFICATION_CHIP,
  classificationLabel,
  health,
  quality,
  severity,
  workflow,
} from '../../lib/risk';
import { formatConfidence } from '../../lib/format';
import { formatDateTime, formatRelative } from '../../lib/time';
import type { AlertStatus, Classification } from '../../types/api';

/* ------------------------------------------------------------- risk badge -- */

/**
 * The canonical severity indicator. Used identically on the map, in tables,
 * on cards and in detail views so that a given colour always means the same
 * operational thing.
 */
export function RiskBadge({
  level,
  size = 'md',
  showGlyph = true,
  className,
}: {
  level: string | null | undefined;
  size?: 'sm' | 'md';
  showGlyph?: boolean;
  className?: string;
}) {
  const descriptor = severity(level);
  return (
    <Badge size={size} className={cx(descriptor.chip, className)}>
      {showGlyph && (
        <span aria-hidden="true" className="text-[0.9em] leading-none">
          {descriptor.glyph}
        </span>
      )}
      {descriptor.label}
    </Badge>
  );
}

/* --------------------------------------------------------- workflow badge -- */

/**
 * Governance state. Deliberately not coloured on the severity scale — an
 * approved CRITICAL warning and a draft CRITICAL warning must be told apart
 * at a glance, and conflating the two scales is exactly how a model output
 * gets mistaken for an authorised one.
 */
export function StatusBadge({
  status,
  size = 'md',
  className,
}: {
  status: AlertStatus;
  size?: 'sm' | 'md';
  className?: string;
}) {
  const descriptor = workflow(status);
  return (
    <Badge size={size} className={cx(descriptor.chip, className)}>
      {descriptor.humanApproved ? (
        <ShieldCheck className="size-3" aria-hidden="true" />
      ) : (
        <ShieldAlert className="size-3" aria-hidden="true" />
      )}
      {descriptor.label}
    </Badge>
  );
}

/**
 * A compact statement of whether a record has human authorisation yet.
 * Rendered next to any AI-derived risk so the distinction is never implicit.
 */
export function GovernanceBadge({
  status,
  className,
}: {
  status: AlertStatus;
  className?: string;
}) {
  const descriptor = workflow(status);
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-[--radius-xs] px-2 py-0.5 text-[11px] font-medium',
        descriptor.humanApproved
          ? 'bg-[--color-ok-bg] text-[--color-ok-fg] ring-1 ring-inset ring-[--color-ok-line]'
          : 'bg-[--color-muted-bg] text-[--color-muted-fg] ring-1 ring-inset ring-[--color-muted-line]',
        className,
      )}
    >
      {descriptor.humanApproved ? 'Human-authorised' : 'AI-generated · not yet authorised'}
    </span>
  );
}

/* ----------------------------------------------------- data quality badge -- */

export function DataQualityBadge({
  status,
  size = 'md',
  className,
}: {
  status: string | null | undefined;
  size?: 'sm' | 'md';
  className?: string;
}) {
  const descriptor = quality(status);
  return (
    <Badge size={size} className={cx(descriptor.chip, className)} >
      <span aria-hidden="true" className="text-[0.9em] leading-none">
        {descriptor.glyph}
      </span>
      <span className="sr-only">Data quality: </span>
      {descriptor.label}
    </Badge>
  );
}

/* --------------------------------------------------------- freshness badge -- */

/**
 * Source freshness. The status comes from the backend's own per-source
 * assessment, which weighs each source against *its* declared cadence — IPC
 * is not late because it did not update today.
 */
export function FreshnessBadge({
  status,
  lastSuccess,
  size = 'md',
  className,
}: {
  status: string | null | undefined;
  lastSuccess?: string | null;
  size?: 'sm' | 'md';
  className?: string;
}) {
  const descriptor = health(status);
  return (
    <span className={cx('inline-flex items-center gap-2', className)}>
      <Badge size={size} className={descriptor.chip}>
        <span aria-hidden="true" className="text-[0.9em] leading-none">
          {descriptor.glyph}
        </span>
        {descriptor.label}
      </Badge>
      {lastSuccess !== undefined && (
        <span
          className="text-[12px] text-[--color-ink-muted]"
          title={lastSuccess ? formatDateTime(lastSuccess) : 'No successful retrieval recorded'}
        >
          {lastSuccess ? formatRelative(lastSuccess) : 'never'}
        </span>
      )}
    </span>
  );
}

/* -------------------------------------------------- classification badge -- */

export function ClassificationBadge({
  classification,
  size = 'sm',
  className,
}: {
  classification: Classification;
  size?: 'sm' | 'md';
  className?: string;
}) {
  return (
    <Badge size={size} className={cx(CLASSIFICATION_CHIP[classification], className)}>
      {classificationLabel(classification)}
    </Badge>
  );
}

/* ---------------------------------------------------- confidence indicator -- */

/**
 * Model confidence as a four-segment meter plus a numeric value.
 *
 * Rendered on a neutral scale, never the severity scale: high confidence in a
 * NORMAL result and high confidence in a CRITICAL result mean the same thing
 * about the model, and colouring them differently would misread as severity.
 */
export function ConfidenceIndicator({
  value,
  label = 'Model confidence',
  className,
}: {
  value: number | null | undefined;
  label?: string;
  className?: string;
}) {
  const known = value !== null && value !== undefined && Number.isFinite(value);
  const filled = known ? Math.max(0, Math.min(4, Math.round(value * 4))) : 0;

  return (
    <div className={cx('flex items-center gap-2', className)}>
      <span
        className="flex items-center gap-0.5"
        role="img"
        aria-label={
          known ? `${label}: ${formatConfidence(value)}` : `${label}: not reported`
        }
      >
        {[0, 1, 2, 3].map((index) => (
          <span
            key={index}
            className={cx(
              'h-3 w-1.5 rounded-[1px]',
              known && index < filled
                ? 'bg-[--color-brand-600]'
                : 'bg-[--color-line-strong]',
            )}
          />
        ))}
      </span>
      <span className="text-[13px] font-medium text-[--color-ink]">
        {known ? formatConfidence(value) : 'Not reported'}
      </span>
    </div>
  );
}

/* -------------------------------------------------------- stale indicator -- */

/**
 * Marks a record whose underlying inputs are outside their freshness window.
 * Uses the muted palette rather than a severity colour: staleness is a
 * statement about evidence, not about how dangerous the situation is.
 */
export function StaleBadge({ asOf, className }: { asOf?: string | null; className?: string }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-[--radius-xs] px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.045em]',
        'bg-[--color-muted-bg] text-[--color-muted-fg] ring-1 ring-inset ring-[--color-muted-line]',
        className,
      )}
      title={
        asOf
          ? `Most recent evidence: ${formatDateTime(asOf)}`
          : 'No current evidence within the accepted freshness window'
      }
    >
      <Clock className="size-3" aria-hidden="true" />
      Stale
    </span>
  );
}

/* ----------------------------------------------------------- generic chip -- */

/** Neutral metadata chip for domain, geography level, period and similar. */
export function MetaChip({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center gap-1 rounded-[--radius-xs] bg-[--color-surface-sunken]',
        'px-2 py-0.5 text-[11px] font-medium text-[--color-ink-secondary]',
        className,
      )}
    >
      {children}
    </span>
  );
}
