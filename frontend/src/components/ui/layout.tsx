/**
 * Page-level composition primitives: headers, metric cards, tabs, tables,
 * dialogs and drawers.
 *
 * The dialog and drawer implementations are deliberately small and native
 * rather than a component-library dependency: they need focus trapping,
 * Escape handling and scroll locking, and nothing more.
 */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

import { Button, IconButton, Skeleton, cx } from './primitives';

/* ------------------------------------------------------------ page header -- */

export function PageHeader({
  title,
  eyebrow,
  description,
  meta,
  actions,
  className,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  /** Compact status row — timestamps, scope, data status. */
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cx('flex flex-col gap-3', className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          {eyebrow && (
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[--color-ink-faint]">
              {eyebrow}
            </p>
          )}
          <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.02em] text-[--color-ink] sm:text-[26px]">
            {title}
          </h1>
          {description && (
            <p className="mt-1.5 max-w-3xl text-[13px] leading-5 text-[--color-ink-secondary]">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta}
    </header>
  );
}

/** Horizontal strip of small label/value pairs beneath a page title. */
export function MetaBar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        'flex flex-wrap items-center gap-x-5 gap-y-2 rounded-[--radius-md] bg-[--color-surface]',
        'px-3.5 py-2.5 ring-1 ring-[--color-line]',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function MetaItem({
  label,
  value,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx('flex items-baseline gap-1.5 min-w-0', className)}>
      <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-faint]">
        {label}
      </span>
      <span className="truncate text-[13px] font-medium text-[--color-ink]">{value}</span>
    </div>
  );
}

export function SectionHeader({
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
    <div className={cx('mb-3 flex flex-wrap items-end justify-between gap-3', className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[--color-ink]">{title}</h2>
        {description && (
          <p className="mt-0.5 text-[13px] text-[--color-ink-muted]">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------ metric card -- */

/**
 * A single headline figure with supporting breakdown.
 *
 * `accent` paints a 3px left rule and is the only place a severity colour may
 * appear on a metric card — the number itself stays neutral so that a large
 * red digit never implies severity it does not have.
 */
export function MetricCard({
  label,
  value,
  unit,
  caption,
  accent,
  badge,
  footer,
  onClick,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  caption?: ReactNode;
  accent?: string;
  badge?: ReactNode;
  footer?: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  const interactive = Boolean(onClick);
  const Container = interactive ? 'button' : 'div';

  return (
    <Container
      {...(interactive ? { type: 'button' as const, onClick } : {})}
      className={cx(
        'flex w-full flex-col gap-2 rounded-[--radius-lg] bg-[--color-surface] p-4',
        'ring-1 ring-[--color-line] shadow-[--shadow-xs] text-left',
        accent && 'border-l-[3px]',
        accent,
        interactive &&
          'transition-shadow hover:shadow-[--shadow-sm] hover:ring-[--color-line-strong] cursor-pointer',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[--color-ink-muted]">
          {label}
        </span>
        {badge}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-[28px] font-bold leading-none tracking-[-0.03em] text-[--color-ink]">
          {value}
        </span>
        {unit && (
          <span className="text-[13px] font-medium text-[--color-ink-muted]">{unit}</span>
        )}
      </div>
      {caption && <p className="text-[12px] leading-4 text-[--color-ink-muted]">{caption}</p>}
      {footer && <div className="mt-auto pt-1">{footer}</div>}
    </Container>
  );
}

export function MetricCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx(
        'flex flex-col gap-3 rounded-[--radius-lg] bg-[--color-surface] p-4 ring-1 ring-[--color-line]',
        className,
      )}
    >
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-16" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

/* ------------------------------------------------------------------- tabs -- */

export interface TabDefinition<T extends string> {
  id: T;
  label: string;
  /** Optional count rendered as a pill after the label. */
  count?: number;
}

/**
 * Tabs implemented with the ARIA tab pattern, including roving arrow-key
 * navigation. Selection is controlled so it can be mirrored into the URL.
 */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  className,
}: {
  tabs: Array<TabDefinition<T>>;
  value: T;
  onChange: (id: T) => void;
  label: string;
  className?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const index = tabs.findIndex((tab) => tab.id === value);
      if (index < 0) return;
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;

      event.preventDefault();
      onChange(tabs[next].id);
      const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
      buttons?.[next]?.focus();
    },
    [tabs, value, onChange],
  );

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cx(
        'flex gap-1 overflow-x-auto rounded-[--radius-md] bg-[--color-surface-sunken] p-1',
        className,
      )}
    >
      {tabs.map((tab) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cx(
              'inline-flex shrink-0 items-center gap-1.5 rounded-[--radius-sm] px-3 py-1.5',
              'text-[13px] font-medium transition-colors',
              selected
                ? 'bg-[--color-surface] text-[--color-ink] shadow-[--shadow-xs]'
                : 'text-[--color-ink-muted] hover:text-[--color-ink]',
            )}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span
                className={cx(
                  'rounded-full px-1.5 text-[11px] font-semibold tabular-nums',
                  selected
                    ? 'bg-[--color-surface-sunken] text-[--color-ink-secondary]'
                    : 'bg-[--color-line] text-[--color-ink-muted]',
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel<T extends string>({
  id,
  active,
  children,
}: {
  id: T;
  active: boolean;
  children: ReactNode;
}) {
  if (!active) return null;
  return (
    <div role="tabpanel" id={`tabpanel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ table -- */

/**
 * Table shell. Wide tables scroll inside their own container so the page body
 * never scrolls horizontally; pages that need a different mobile treatment
 * render a card list instead and hide the table below `sm`.
 */
export function TableScroll({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('-mx-4 overflow-x-auto sm:mx-0', className)}>
      <div className="inline-block min-w-full align-middle px-4 sm:px-0">{children}</div>
    </div>
  );
}

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <table className={cx('min-w-full border-collapse text-left text-sm', className)}>
      {children}
    </table>
  );
}

export function Th({
  children,
  align = 'left',
  className,
  scope = 'col',
  ...rest
}: React.ThHTMLAttributes<HTMLTableCellElement> & { align?: 'left' | 'right' | 'center' }) {
  return (
    <th
      scope={scope}
      className={cx(
        'whitespace-nowrap border-b border-[--color-line] px-3 py-2.5',
        'text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-muted]',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = 'left',
  className,
  ...rest
}: React.TdHTMLAttributes<HTMLTableCellElement> & { align?: 'left' | 'right' | 'center' }) {
  return (
    <td
      className={cx(
        'border-b border-[--color-line] px-3 py-2.5 text-[13px] text-[--color-ink]',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  );
}

export function TableSkeleton({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: columns }, (_, columnIndex) => (
            <Skeleton
              key={columnIndex}
              className={cx('h-8', columnIndex === 0 ? 'w-[28%]' : 'flex-1')}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------- overlays -- */

function useOverlayBehaviour(open: boolean, onClose: () => void) {
  const containerRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    restoreFocusRef.current = document.activeElement as HTMLElement | null;

    const { body } = document;
    const previousOverflow = body.style.overflow;
    body.style.overflow = 'hidden';

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      // Trap focus inside the overlay.
      const focusable = containerRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);

    // Move focus into the overlay so keyboard users are not stranded behind it.
    const timer = window.setTimeout(() => {
      // `data-autofocus` must win outright. A comma-separated selector returns
      // the first match in *document order*, which would hand focus to the
      // close button in the header instead of the safe control the caller
      // nominated — and on a publish confirmation that distinction matters.
      const preferred = containerRef.current?.querySelector<HTMLElement>('[data-autofocus]');
      const fallback = containerRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea',
      );
      (preferred ?? fallback)?.focus();
    }, 0);

    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      window.clearTimeout(timer);
      body.style.overflow = previousOverflow;
      restoreFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  return containerRef;
}

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  /** Constrains width; `md` suits confirmations, `lg` suits forms. */
  size?: 'sm' | 'md' | 'lg';
}

export function Dialog({ open, onClose, title, description, children, footer, size = 'md' }: DialogProps) {
  const containerRef = useOverlayBehaviour(open, onClose);
  const titleId = useId();
  const descriptionId = useId();

  if (!open || typeof document === 'undefined') return null;

  const width = size === 'sm' ? 'max-w-sm' : size === 'lg' ? 'max-w-2xl' : 'max-w-md';

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div
        className="absolute inset-0 bg-[--color-ink]/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={cx(
          'relative flex w-full flex-col rounded-t-[--radius-xl] bg-[--color-surface] shadow-[--shadow-xl]',
          'max-h-[92dvh] sm:rounded-[--radius-xl]',
          width,
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-[--color-line] px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-[15px] font-semibold text-[--color-ink]">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-[13px] leading-5 text-[--color-ink-secondary]">
                {description}
              </p>
            )}
          </div>
          <IconButton label="Close" size="sm" onClick={onClose}>
            <X className="size-4" aria-hidden="true" />
          </IconButton>
        </header>
        {children && <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>}
        {footer && (
          <footer className="flex flex-wrap justify-end gap-2 border-t border-[--color-line] px-5 py-3.5">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}

/**
 * Side drawer on desktop, bottom sheet on small screens. Used for map
 * selection detail so the map stays visible on a laptop and the detail gets
 * full width on a phone.
 */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: DialogProps) {
  const containerRef = useOverlayBehaviour(open, onClose);
  const titleId = useId();

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-stretch sm:justify-end">
      <div className="absolute inset-0 bg-[--color-ink]/30" onClick={onClose} aria-hidden="true" />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cx(
          'relative flex w-full flex-col bg-[--color-surface] shadow-[--shadow-xl]',
          'max-h-[88dvh] rounded-t-[--radius-xl]',
          'sm:h-full sm:max-h-none sm:w-[440px] sm:rounded-none sm:border-l sm:border-[--color-line]',
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-[--color-line] px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            <h2 id={titleId} className="truncate text-[15px] font-semibold text-[--color-ink]">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 text-[12px] text-[--color-ink-muted]">{description}</p>
            )}
          </div>
          <IconButton label="Close panel" size="sm" onClick={onClose}>
            <X className="size-4" aria-hidden="true" />
          </IconButton>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">{children}</div>
        {footer && (
          <footer className="border-t border-[--color-line] px-4 py-3 sm:px-5">{footer}</footer>
        )}
      </div>
    </div>,
    document.body,
  );
}

/* --------------------------------------------------------- confirm dialog -- */

/**
 * Confirmation for a consequential action. The confirm control is deliberately
 * not focused on open, so that a reflexive Enter keypress cannot publish a
 * warning.
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  consequence,
  confirmLabel,
  destructive,
  pending,
  children,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  consequence: string;
  confirmLabel: string;
  destructive?: boolean;
  pending?: boolean;
  children?: ReactNode;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={consequence}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending} data-autofocus>
            Cancel
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={pending}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}

/* ---------------------------------------------------------------- tooltip -- */

/**
 * Hint text on hover and focus. Implemented with a native `title` fallback in
 * addition to the visual bubble so the information is never lost on touch
 * devices, where hover does not exist.
 */
export function Tooltip({
  content,
  children,
  className,
}: {
  content: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cx('group/tt relative inline-flex', className)} title={content}>
      {children}
      <span
        role="tooltip"
        className={cx(
          'pointer-events-none absolute bottom-full left-1/2 z-30 mb-1.5 hidden -translate-x-1/2',
          'whitespace-nowrap rounded-[--radius-sm] bg-[--color-ink] px-2 py-1 text-[11px] text-white',
          'shadow-[--shadow-md] group-hover/tt:block group-focus-within/tt:block',
        )}
      >
        {content}
      </span>
    </span>
  );
}
