/**
 * Empty, error and access-boundary states.
 *
 * The product rule these encode: a technical failure must never be dressed up
 * as "no data". An operator who sees "No warnings require review" has to be
 * able to trust that the queue is genuinely empty and not that a request 500'd.
 * `ErrorState` and `EmptyState` are therefore visually and textually distinct,
 * and `QueryBoundary` picks between them from the error's normalised kind.
 */

import type { ReactNode } from 'react';
import {
  AlertTriangle,
  Ban,
  Inbox,
  Lock,
  RefreshCw,
  ServerCrash,
  WifiOff,
} from 'lucide-react';

import { ApiError } from '../../api/client';
import { Button, cx } from './primitives';

/* ------------------------------------------------------------ empty state -- */

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
  compact,
}: {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cx(
        'flex flex-col items-center justify-center rounded-[--radius-lg] border border-dashed',
        'border-[--color-line-strong] bg-[--color-surface-subtle] text-center',
        compact ? 'gap-2 px-4 py-8' : 'gap-3 px-6 py-14',
        className,
      )}
      role="status"
    >
      <span className="flex size-9 items-center justify-center rounded-full bg-[--color-surface-sunken] text-[--color-ink-faint]">
        {icon ?? <Inbox className="size-4.5" aria-hidden="true" />}
      </span>
      <p className="text-sm font-semibold text-[--color-ink]">{title}</p>
      {description && (
        <p className="max-w-md text-[13px] leading-5 text-[--color-ink-muted]">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------ error state -- */

function iconForError(error: ApiError): ReactNode {
  switch (error.kind) {
    case 'network':
      return <WifiOff className="size-4.5" aria-hidden="true" />;
    case 'timeout':
      return <RefreshCw className="size-4.5" aria-hidden="true" />;
    case 'forbidden':
      return <Lock className="size-4.5" aria-hidden="true" />;
    case 'unauthorized':
      return <Lock className="size-4.5" aria-hidden="true" />;
    case 'not_found':
      return <Ban className="size-4.5" aria-hidden="true" />;
    case 'server':
      return <ServerCrash className="size-4.5" aria-hidden="true" />;
    default:
      return <AlertTriangle className="size-4.5" aria-hidden="true" />;
  }
}

function titleForError(error: ApiError): string {
  switch (error.kind) {
    case 'network':
      return 'Cannot reach the platform service';
    case 'timeout':
      return 'The service did not respond in time';
    case 'unauthorized':
      return 'Your session has ended';
    case 'forbidden':
      return 'Access not authorised';
    case 'not_found':
      return 'Not found in your scope';
    case 'conflict':
      return 'This record changed while you were working';
    case 'validation':
      return 'The request was rejected';
    case 'server':
      return 'The service reported an internal error';
    default:
      return 'Something went wrong';
  }
}

export function ErrorState({
  error,
  onRetry,
  className,
  compact,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}) {
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError(0, 'unknown', error instanceof Error ? error.message : 'Unexpected failure.');

  const boundary = apiError.isAccessBoundary;

  return (
    <div
      className={cx(
        'flex flex-col items-center justify-center rounded-[--radius-lg] text-center ring-1',
        boundary
          ? 'bg-[--color-muted-bg] ring-[--color-muted-line]'
          : 'bg-[--color-danger-bg] ring-[--color-danger-line]',
        compact ? 'gap-2 px-4 py-8' : 'gap-3 px-6 py-12',
        className,
      )}
      role="alert"
    >
      <span
        className={cx(
          'flex size-9 items-center justify-center rounded-full',
          boundary
            ? 'bg-[--color-surface] text-[--color-muted-fg]'
            : 'bg-[--color-surface] text-[--color-danger-fg]',
        )}
      >
        {iconForError(apiError)}
      </span>
      <p
        className={cx(
          'text-sm font-semibold',
          boundary ? 'text-[--color-ink]' : 'text-[--color-danger-fg]',
        )}
      >
        {titleForError(apiError)}
      </p>
      <p className="max-w-md text-[13px] leading-5 text-[--color-ink-secondary]">
        {apiError.message}
      </p>
      {onRetry && apiError.retryable && (
        <Button size="sm" variant="secondary" onClick={onRetry} className="mt-1">
          <RefreshCw className="size-3.5" aria-hidden="true" />
          Try again
        </Button>
      )}
    </div>
  );
}

/* ------------------------------------------------------- access boundary -- */

/**
 * Shown when the signed-in role genuinely lacks a capability. Distinct from
 * `ErrorState` because nothing has failed — the system is working correctly
 * and the user simply is not authorised.
 */
export function AccessDenied({
  capability,
  what = 'this information',
  className,
}: {
  capability?: string;
  what?: string;
  className?: string;
}) {
  return (
    <div
      className={cx(
        'flex flex-col items-center justify-center gap-3 rounded-[--radius-lg]',
        'bg-[--color-muted-bg] px-6 py-12 text-center ring-1 ring-[--color-muted-line]',
        className,
      )}
      role="status"
    >
      <span className="flex size-9 items-center justify-center rounded-full bg-[--color-surface] text-[--color-muted-fg]">
        <Lock className="size-4.5" aria-hidden="true" />
      </span>
      <p className="text-sm font-semibold text-[--color-ink]">Access not authorised</p>
      <p className="max-w-md text-[13px] leading-5 text-[--color-ink-secondary]">
        Your assigned role does not grant access to {what}. If you need it, ask a platform
        administrator to review your role assignment.
      </p>
      {capability && (
        <p className="text-[12px] text-[--color-ink-muted]">
          Required capability: <code className="font-mono text-[11px]">{capability}</code>
        </p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------- query boundary -- */

export interface QueryBoundaryProps<T> {
  /** The subset of a TanStack query result this component needs. */
  query: {
    data: T | undefined;
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch?: () => unknown;
  };
  /** Skeleton matching the resolved layout. */
  skeleton: ReactNode;
  /** Rendered when the request succeeded but returned nothing. */
  empty?: ReactNode;
  /** True when `data` should be treated as empty. */
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
  compact?: boolean;
}

/**
 * Renders exactly one of: skeleton, error, empty, or content.
 *
 * Keeping this decision in one component is what prevents a page from
 * accidentally rendering an empty table when the request actually failed.
 */
export function QueryBoundary<T>({
  query,
  skeleton,
  empty,
  isEmpty,
  children,
  compact,
}: QueryBoundaryProps<T>) {
  if (query.isPending) return <>{skeleton}</>;

  if (query.isError) {
    return (
      <ErrorState
        error={query.error}
        onRetry={query.refetch ? () => query.refetch?.() : undefined}
        compact={compact}
      />
    );
  }

  if (query.data === undefined) {
    return <>{skeleton}</>;
  }

  if (isEmpty?.(query.data) && empty) {
    return <>{empty}</>;
  }

  return <>{children(query.data)}</>;
}

/* ------------------------------------------------------------- inline note -- */

export type NoteTone = 'info' | 'caution' | 'neutral';

const NOTE_TONE: Record<NoteTone, string> = {
  info: 'bg-[--color-info-bg] text-[--color-info-fg] ring-[--color-info-line]',
  caution: 'bg-[--color-risk-watch-bg] text-[--color-risk-watch-fg] ring-[--color-risk-watch-line]',
  neutral: 'bg-[--color-muted-bg] text-[--color-muted-fg] ring-[--color-muted-line]',
};

/**
 * Short contextual statement — scope limitations, methodology caveats,
 * suppression reasons. Deliberately not a severity colour.
 */
export function Note({
  tone = 'neutral',
  icon,
  children,
  className,
}: {
  tone?: NoteTone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        'flex items-start gap-2.5 rounded-[--radius-md] px-3 py-2.5 text-[13px] leading-5 ring-1 ring-inset',
        NOTE_TONE[tone],
        className,
      )}
    >
      {icon && <span className="mt-px shrink-0">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
