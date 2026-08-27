/**
 * Core interface primitives.
 *
 * These carry the design system's spacing rhythm, radii, borders and focus
 * treatment so that pages compose behaviour rather than repeating utility
 * strings. Severity colour is never applied here — that belongs to the risk
 * components, which draw it from `lib/risk.ts`.
 */

import {
  forwardRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react';

/** Minimal class combiner — avoids pulling in a dependency for this. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

/* ------------------------------------------------------------------ button -- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle';
type ButtonSize = 'sm' | 'md' | 'lg';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-[--color-brand-600] text-white hover:bg-[--color-brand-700] active:bg-[--color-brand-800] shadow-[--shadow-xs]',
  secondary:
    'bg-[--color-surface] text-[--color-ink] ring-1 ring-inset ring-[--color-line-strong] hover:bg-[--color-surface-sunken] shadow-[--shadow-xs]',
  ghost: 'text-[--color-ink-secondary] hover:bg-[--color-surface-sunken] hover:text-[--color-ink]',
  // Reserved for irreversible/destructive confirmation, never for severity.
  danger:
    'bg-[--color-risk-critical-fg] text-white hover:brightness-110 active:brightness-95 shadow-[--shadow-xs]',
  subtle:
    'bg-[--color-surface-sunken] text-[--color-ink-secondary] hover:bg-[--color-line] hover:text-[--color-ink]',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-[--radius-sm]',
  md: 'h-9.5 px-3.5 text-sm gap-2 rounded-[--radius-md]',
  lg: 'h-11 px-5 text-sm gap-2 rounded-[--radius-md]',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Renders a spinner and blocks interaction without changing layout width. */
  loading?: boolean;
  fullWidth?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, fullWidth, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex items-center justify-center font-medium whitespace-nowrap',
        'transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-50',
        BUTTON_SIZES[size],
        BUTTON_VARIANTS[variant],
        fullWidth && 'w-full',
        className,
      )}
      {...rest}
    >
      {loading && <Spinner className="size-4 shrink-0" />}
      {children}
    </button>
  );
});

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx('animate-spin', className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Square icon-only button. Requires an accessible label. */
export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = 'ghost', size = 'md', className, children, ...rest },
  ref,
) {
  const dimension = size === 'sm' ? 'size-8' : size === 'lg' ? 'size-11' : 'size-9.5';
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        'inline-flex items-center justify-center rounded-[--radius-md]',
        'transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50',
        dimension,
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

/* -------------------------------------------------------------------- card -- */

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Removes the default padding for cards that host tables or maps edge-to-edge. */
  flush?: boolean;
}

export function Card({ flush, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cx(
        'rounded-[--radius-lg] bg-[--color-surface] ring-1 ring-[--color-line] shadow-[--shadow-xs]',
        !flush && 'p-4 sm:p-5',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx('flex flex-wrap items-start justify-between gap-3', className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[--color-ink]">{title}</h2>
        {description && (
          <p className="mt-1 text-[13px] leading-5 text-[--color-ink-muted]">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Section divider inside a card. */
export function Divider({ className }: { className?: string }) {
  return <hr className={cx('border-0 border-t border-[--color-line]', className)} />;
}

/* ------------------------------------------------------------------ panel -- */

/** A labelled content region used inside detail views. */
export function Panel({
  title,
  eyebrow,
  actions,
  children,
  className,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cx(
        'rounded-[--radius-lg] bg-[--color-surface] ring-1 ring-[--color-line] shadow-[--shadow-xs]',
        className,
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[--color-line] px-4 py-3 sm:px-5">
        <div className="min-w-0">
          {eyebrow && (
            <p className="text-[11px] font-semibold uppercase tracking-[0.09em] text-[--color-ink-faint]">
              {eyebrow}
            </p>
          )}
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[--color-ink]">{title}</h2>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </header>
      <div className="px-4 py-4 sm:px-5">{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ badge -- */

export function Badge({
  children,
  className,
  size = 'md',
}: {
  children: ReactNode;
  className?: string;
  size?: 'sm' | 'md';
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-[--radius-xs] font-semibold whitespace-nowrap',
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-[11px]',
        'uppercase tracking-[0.045em]',
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ----------------------------------------------------------------- inputs -- */

export interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: ReactNode;
  error?: string | null;
  /** Visually hides the label while keeping it available to assistive tech. */
  hideLabel?: boolean;
  children: ReactNode;
  className?: string;
}

export function Field({ label, htmlFor, hint, error, hideLabel, children, className }: FieldProps) {
  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <label
        htmlFor={htmlFor}
        className={cx(
          'text-[13px] font-medium text-[--color-ink-secondary]',
          hideLabel && 'sr-only',
        )}
      >
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-[12px] text-[--color-danger-fg]" role="alert">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${htmlFor}-hint`} className="text-[12px] text-[--color-ink-muted]">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

const CONTROL_BASE =
  'w-full rounded-[--radius-md] bg-[--color-surface] px-3 text-sm text-[--color-ink] ' +
  'ring-1 ring-inset ring-[--color-line-strong] placeholder:text-[--color-ink-faint] ' +
  'transition-shadow focus:ring-2 focus:ring-[--color-brand-600] ' +
  'disabled:cursor-not-allowed disabled:bg-[--color-surface-sunken] disabled:text-[--color-ink-muted]';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={cx(CONTROL_BASE, 'h-9.5', className)} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <select ref={ref} className={cx(CONTROL_BASE, 'h-9.5 pr-8', className)} {...rest}>
        {children}
      </select>
    );
  },
);

/* -------------------------------------------------------------- skeletons -- */

/**
 * Loading placeholder. Skeletons mirror the shape of the content they replace
 * so the layout does not jump when data resolves.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx('animate-pulse rounded-[--radius-sm] bg-[--color-surface-sunken]', className)}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cx('flex flex-col gap-2', className)} aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className={cx('h-3.5', index === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ meta -- */

/** Label/value pair used throughout detail views. */
export function DataPoint({
  label,
  value,
  hint,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx('min-w-0', className)}>
      <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-faint]">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm font-medium text-[--color-ink]">{value}</dd>
      {hint && <p className="mt-0.5 text-[12px] text-[--color-ink-muted]">{hint}</p>}
    </div>
  );
}

/** Responsive grid of `DataPoint`s. */
export function DataGrid({
  children,
  columns = 3,
  className,
}: {
  children: ReactNode;
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  const columnClass =
    columns === 2
      ? 'sm:grid-cols-2'
      : columns === 4
        ? 'sm:grid-cols-2 lg:grid-cols-4'
        : 'sm:grid-cols-2 lg:grid-cols-3';
  return (
    <dl className={cx('grid grid-cols-1 gap-x-6 gap-y-4', columnClass, className)}>{children}</dl>
  );
}
