/**
 * Authenticated application shell.
 *
 * Desktop: persistent sidebar + sticky header + scrolling main region.
 * Tablet:  icon-only rail, expanded on hover/focus.
 * Mobile:  sidebar collapses into a drawer opened from the header.
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  ChevronDown,
  LogOut,
  Menu,
  ShieldAlert,
  User,
  X,
} from 'lucide-react';

import { useAuth } from '../providers/AuthProvider';
import { useAlerts, useNationalSummary } from '../../api/queries';
import { Button, IconButton, Skeleton, cx } from '../../components/ui/primitives';
import { formatDateTime, formatRelative, formatTime, nextScheduledRun } from '../../lib/time';
import { useI18n } from '../../i18n';
import {
  PROFILE_ITEM,
  isVisible,
  visibleSections,
  type NavItem,
} from './navigation';

/* --------------------------------------------------------------- sidebar -- */

function BrandMark({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <span
        className="flex size-8 shrink-0 items-center justify-center rounded-[--radius-md] bg-[--color-brand-700] text-white"
        aria-hidden="true"
      >
        {/* Somali five-pointed star — the platform's identity mark. */}
        <svg viewBox="0 0 24 24" className="size-4.5" fill="currentColor">
          <path d="M12 2.4l2.7 8.2h8.6l-6.9 5.1 2.6 8.3-7-5.1-7 5.1 2.6-8.3-6.9-5.1h8.6z" />
        </svg>
      </span>
      {!collapsed && (
        <span className="min-w-0">
          <span className="block text-[13px] font-bold leading-tight tracking-[0.02em] text-[--color-ink]">
            SOMALIA AI
          </span>
          <span className="block truncate text-[11px] leading-tight text-[--color-ink-muted]">
            Early Warning &amp; Early Action
          </span>
        </span>
      )}
    </div>
  );
}

function NavRow({
  item,
  collapsed,
  onNavigate,
  label,
}: {
  item: NavItem;
  collapsed?: boolean;
  onNavigate?: () => void;
  label: string;
}) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cx(
          'group relative flex items-center gap-2.5 rounded-[--radius-md] px-2.5 py-2 text-[13px] font-medium',
          'transition-colors duration-150',
          collapsed && 'justify-center px-2',
          isActive
            ? 'bg-[--color-brand-50] text-[--color-brand-700]'
            : 'text-[--color-ink-secondary] hover:bg-[--color-surface-sunken] hover:text-[--color-ink]',
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Active indicator is a shape, not only a colour. */}
          <span
            aria-hidden="true"
            className={cx(
              'absolute left-0 h-5 w-0.5 rounded-r-full bg-[--color-brand-600] transition-opacity',
              isActive ? 'opacity-100' : 'opacity-0',
            )}
          />
          <Icon className="size-4 shrink-0" aria-hidden="true" />
          {!collapsed && <span className="truncate">{label}</span>}
        </>
      )}
    </NavLink>
  );
}

function SidebarContent({
  collapsed,
  onNavigate,
}: {
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const { capabilities } = useAuth();
  const { t } = useI18n();
  const sections = useMemo(() => visibleSections(capabilities), [capabilities]);

  const label = useCallback(
    (item: NavItem) => (item.i18nKey ? t(item.i18nKey as never) : item.label),
    [t],
  );

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto px-3 py-4">
      <BrandMark collapsed={collapsed} />

      <nav className="flex flex-1 flex-col gap-4" aria-label="Primary">
        {sections.map((section) => (
          <div key={section.id} className="flex flex-col gap-0.5">
            {!collapsed && (
              <p className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-[--color-ink-faint]">
                {section.label}
              </p>
            )}
            {section.items.map((item) => (
              <NavRow
                key={item.to}
                item={item}
                collapsed={collapsed}
                onNavigate={onNavigate}
                label={label(item)}
              />
            ))}
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-0.5 border-t border-[--color-line] pt-3">
        {isVisible(PROFILE_ITEM, capabilities) && (
          <NavRow
            item={PROFILE_ITEM}
            collapsed={collapsed}
            onNavigate={onNavigate}
            label={label(PROFILE_ITEM)}
          />
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- header -- */

function currentPageTitle(pathname: string, capabilities: ReadonlySet<string>): string {
  for (const section of visibleSections(capabilities)) {
    for (const item of section.items) {
      if (pathname === item.to || pathname.startsWith(`${item.to}/`)) return item.label;
    }
  }
  if (pathname.startsWith(PROFILE_ITEM.to)) return PROFILE_ITEM.label;
  return 'Somalia AI';
}

/**
 * Header status strip. `LATEST INTELLIGENCE` is the generation time reported
 * by the API; `NEXT RUN` is the *scheduled* daily 08:00 Mogadishu cadence and
 * is labelled as scheduled so a stalled pipeline is never masked by it.
 */
function IntelligenceClock() {
  const { can } = useAuth();
  const summary = useNationalSummary(undefined, can('predictions.read') || can('alerts.read'));
  const nextRun = useMemo(() => nextScheduledRun(), []);

  if (summary.isPending) {
    return <Skeleton className="h-4 w-40" />;
  }

  if (summary.isError || !summary.data) {
    // Never invent a timestamp. An unavailable summary says so.
    return (
      <span className="text-[12px] text-[--color-ink-muted]">
        Latest intelligence unavailable
      </span>
    );
  }

  return (
    <div className="flex items-center gap-x-4 gap-y-1">
      <span className="flex items-baseline gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[--color-ink-faint]">
          As of
        </span>
        <time
          dateTime={summary.data.generated_at}
          className="text-[12px] font-medium text-[--color-ink]"
          title={formatDateTime(summary.data.generated_at)}
        >
          {formatRelative(summary.data.generated_at)}
        </time>
      </span>
      <span className="hidden items-baseline gap-1.5 lg:flex">
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[--color-ink-faint]">
          Next scheduled run
        </span>
        <span className="text-[12px] font-medium text-[--color-ink-secondary]">
          {formatTime(nextRun)}
        </span>
      </span>
    </div>
  );
}

/** Count of warnings sitting in a state that needs a human decision. */
function ReviewQueueButton() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const alerts = useAlerts(can('alerts.read'));

  const pending = useMemo(
    () =>
      (alerts.data ?? []).filter(
        (alert) =>
          alert.status === 'draft' ||
          alert.status === 'in_review' ||
          alert.status === 'verification_required' ||
          alert.status === 'verified',
      ).length,
    [alerts.data],
  );

  if (!can('alerts.read')) return null;

  return (
    <button
      type="button"
      onClick={() => navigate('/app/warnings?status=needs_review')}
      className={cx(
        'relative inline-flex h-9 items-center gap-2 rounded-[--radius-md] px-2.5',
        'text-[13px] font-medium text-[--color-ink-secondary]',
        'transition-colors hover:bg-[--color-surface-sunken] hover:text-[--color-ink]',
      )}
      aria-label={
        pending > 0
          ? `${pending} warnings await review. Open the warning center.`
          : 'Open the warning center'
      }
    >
      <Bell className="size-4" aria-hidden="true" />
      {pending > 0 && (
        <span className="rounded-full bg-[--color-risk-warning-bg] px-1.5 text-[11px] font-semibold tabular-nums text-[--color-risk-warning-fg] ring-1 ring-inset ring-[--color-risk-warning-line]">
          {pending}
        </span>
      )}
    </button>
  );
}

function ProfileMenu() {
  const { principal, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    // Close on any outside interaction or Escape.
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('click', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const initials = (principal?.display_name ?? principal?.email ?? '?')
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  return (
    <div className="relative" onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cx(
          'flex h-9 items-center gap-2 rounded-[--radius-md] pl-1 pr-2',
          'transition-colors hover:bg-[--color-surface-sunken]',
        )}
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-[--color-brand-100] text-[11px] font-bold text-[--color-brand-700]">
          {initials || '?'}
        </span>
        <span className="hidden max-w-[9rem] truncate text-[13px] font-medium text-[--color-ink] lg:block">
          {principal?.display_name ?? principal?.email ?? 'Account'}
        </span>
        <ChevronDown className="size-3.5 text-[--color-ink-muted]" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className={cx(
            'absolute right-0 top-full z-40 mt-1.5 w-64 overflow-hidden rounded-[--radius-lg]',
            'bg-[--color-surface] shadow-[--shadow-lg] ring-1 ring-[--color-line]',
          )}
        >
          <div className="border-b border-[--color-line] px-3.5 py-3">
            <p className="truncate text-[13px] font-semibold text-[--color-ink]">
              {principal?.display_name ?? 'Signed in'}
            </p>
            <p className="truncate text-[12px] text-[--color-ink-muted]">{principal?.email}</p>
            <p className="mt-1.5 text-[11px] text-[--color-ink-faint]">
              {principal?.capabilities.length ?? 0} capabilities granted
            </p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void navigate(PROFILE_ITEM.to);
            }}
            className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] text-[--color-ink-secondary] transition-colors hover:bg-[--color-surface-sunken] hover:text-[--color-ink]"
          >
            <User className="size-4" aria-hidden="true" />
            Profile &amp; access
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
              void navigate('/login');
            }}
            className="flex w-full items-center gap-2.5 border-t border-[--color-line] px-3.5 py-2.5 text-left text-[13px] text-[--color-ink-secondary] transition-colors hover:bg-[--color-surface-sunken] hover:text-[--color-ink]"
          >
            <LogOut className="size-4" aria-hidden="true" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- shell -- */

export function AppLayout() {
  const location = useLocation();
  const { capabilities } = useAuth();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Lock body scroll while the mobile drawer is open.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [mobileNavOpen]);

  const title = currentPageTitle(location.pathname, capabilities);

  return (
    <div className="min-h-dvh bg-[--color-canvas]">
      <a
        href="#main-content"
        className="sr-only-focusable absolute left-3 top-3 z-[60] rounded-[--radius-md] bg-[--color-brand-700] px-3 py-2 text-[13px] font-medium text-white"
      >
        Skip to main content
      </a>

      {/* Desktop sidebar. Hidden below lg, where the drawer takes over. */}
      <aside
        className={cx(
          'fixed inset-y-0 left-0 z-30 hidden w-[236px] border-r border-[--color-line]',
          'bg-[--color-surface] lg:block',
        )}
      >
        <SidebarContent />
      </aside>

      {/* Mobile / tablet drawer. */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-[--color-ink]/40"
            onClick={() => setMobileNavOpen(false)}
            aria-hidden="true"
          />
          <div
            className="absolute inset-y-0 left-0 w-[276px] max-w-[85vw] bg-[--color-surface] shadow-[--shadow-xl]"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <div className="flex justify-end px-3 pt-3">
              <IconButton label="Close navigation" size="sm" onClick={() => setMobileNavOpen(false)}>
                <X className="size-4" aria-hidden="true" />
              </IconButton>
            </div>
            <SidebarContent onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </div>
      )}

      <div className="lg:pl-[236px]">
        <header
          className={cx(
            'sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-[--color-line]',
            'bg-[--color-surface]/95 px-3 backdrop-blur sm:px-5',
          )}
        >
          <IconButton
            label="Open navigation"
            size="sm"
            className="lg:hidden"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu className="size-4.5" aria-hidden="true" />
          </IconButton>

          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] font-semibold text-[--color-ink]">{title}</p>
            <div className="hidden sm:block">
              <IntelligenceClock />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <ReviewQueueButton />
            <ProfileMenu />
          </div>
        </header>

        <main id="main-content" className="px-3 py-4 sm:px-5 sm:py-6 lg:px-7">
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

function RouteFallback() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading page">
      <Skeleton className="h-7 w-64" />
      <Skeleton className="h-4 w-96" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  );
}

/* -------------------------------------------------------- session notice -- */

/** Rendered by the router when a session expires mid-session. */
export function SessionExpiredNotice({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="mb-4 flex items-start gap-3 rounded-[--radius-md] bg-[--color-risk-watch-bg] px-3.5 py-3 ring-1 ring-inset ring-[--color-risk-watch-line]">
      <ShieldAlert className="mt-0.5 size-4 shrink-0 text-[--color-risk-watch-fg]" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-[--color-risk-watch-fg]">
          Your session ended
        </p>
        <p className="mt-0.5 text-[13px] leading-5 text-[--color-ink-secondary]">
          You were signed out because your session could not be renewed. Sign in again to continue
          — any unsaved decision was not submitted.
        </p>
      </div>
      <Button size="sm" variant="ghost" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  );
}
