/**
 * Warning Center — the operational review queue.
 *
 * `/alerts` returns every alert the principal may read, newest first, with no
 * server-side filtering. Filtering, searching and pagination are therefore
 * applied client-side here, and the filter state is mirrored into the URL so a
 * view can be shared with a colleague or reproduced during an audit.
 *
 * Critical warnings awaiting a decision are made prominent through a left
 * accent rule and ordering, not by flooding the screen with red.
 */

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Filter, Inbox, Search, X } from 'lucide-react';

import { useAlerts } from '../../api/queries';
import { Button, Card, Input, Select, Skeleton, cx } from '../../components/ui/primitives';
import {
  MetaBar,
  MetaItem,
  PageHeader,
  Tabs,
  type TabDefinition,
} from '../../components/ui/layout';
import { EmptyState, ErrorState, QueryBoundary } from '../../components/ui/states';
import {
  ClassificationBadge,
  MetaChip,
  RiskBadge,
  StatusBadge,
} from '../../components/intelligence/badges';
import { useUrlFilters } from '../../hooks/useUrlFilters';
import {
  DOMAIN_ORDER,
  SEVERITY_ORDER,
  domain as domainDescriptor,
  severity,
  workflow,
} from '../../lib/risk';
import { formatCount } from '../../lib/format';
import { formatDateTime, formatRelative } from '../../lib/time';
import type { AlertListItem, AlertStatus } from '../../types/api';

/* ------------------------------------------------------------------ tabs -- */

/**
 * Queue groupings. `needs_review` spans every pre-approval state, because an
 * analyst triaging work does not care whether a warning is a draft or awaiting
 * field evidence — only that it still needs a human.
 *
 * There is deliberately no HELD, REJECTED or SUPPRESSED tab: the backend
 * workflow (`backend/app/modules/alerts/service.py`) defines no such states,
 * and offering a filter that can never match anything would misrepresent the
 * system's actual capabilities.
 */
type QueueTab =
  | 'needs_review'
  | 'verification'
  | 'approved'
  | 'published'
  | 'resolved'
  | 'all';

const TAB_STATUSES: Record<QueueTab, AlertStatus[] | null> = {
  needs_review: ['draft', 'in_review'],
  verification: ['verification_required', 'verified'],
  approved: ['approved'],
  published: ['published'],
  resolved: ['resolved'],
  all: null,
};

const TAB_LABELS: Record<QueueTab, string> = {
  needs_review: 'Needs review',
  verification: 'Verification',
  approved: 'Approved',
  published: 'Published',
  resolved: 'Resolved',
  all: 'All',
};

const TAB_ORDER: QueueTab[] = [
  'needs_review',
  'verification',
  'approved',
  'published',
  'resolved',
  'all',
];

function isQueueTab(value: string): value is QueueTab {
  return TAB_ORDER.includes(value as QueueTab);
}

/* ------------------------------------------------------------------ page -- */

export function WarningCenterPage() {
  const navigate = useNavigate();
  const alerts = useAlerts(true);

  const [filters, setFilters, resetFilters] = useUrlFilters({
    status: 'needs_review',
    severity: '',
    type: '',
    q: '',
  });

  const activeTab: QueueTab = isQueueTab(filters.status) ? filters.status : 'needs_review';

  const counts = useMemo(() => {
    const data = alerts.data ?? [];
    const result = {} as Record<QueueTab, number>;
    for (const tab of TAB_ORDER) {
      const statuses = TAB_STATUSES[tab];
      result[tab] = statuses
        ? data.filter((alert) => statuses.includes(alert.status)).length
        : data.length;
    }
    return result;
  }, [alerts.data]);

  const filtered = useMemo(() => {
    const data = alerts.data ?? [];
    const statuses = TAB_STATUSES[activeTab];
    const search = filters.q.trim().toLowerCase();

    return data
      .filter((alert) => {
        if (statuses && !statuses.includes(alert.status)) return false;
        if (filters.severity && alert.risk_level !== filters.severity) return false;
        if (filters.type && alert.risk_domain !== filters.type) return false;
        if (search) {
          const haystack = `${alert.title} ${alert.summary} ${alert.target_period}`.toLowerCase();
          if (!haystack.includes(search)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        // Most severe first; equal severity ordered oldest-first so a warning
        // that has been waiting rises above one that just arrived.
        const bySeverity = severity(b.risk_level).rank - severity(a.risk_level).rank;
        if (bySeverity !== 0) return bySeverity;
        return a.created_at.localeCompare(b.created_at);
      });
  }, [alerts.data, activeTab, filters]);

  const tabs: Array<TabDefinition<QueueTab>> = TAB_ORDER.map((tab) => ({
    id: tab,
    label: TAB_LABELS[tab],
    count: counts[tab],
  }));

  const filtersActive = Boolean(filters.severity || filters.type || filters.q);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Operations"
        title="Warning Center"
        description="Every warning passes through analyst review and authorised approval. No warning in this queue publishes itself."
        meta={
          <MetaBar>
            <MetaItem label="Awaiting decision" value={formatCount(counts.needs_review + counts.verification)} />
            <MetaItem label="Published" value={formatCount(counts.published)} />
            <MetaItem label="Total in scope" value={formatCount(counts.all)} />
          </MetaBar>
        }
      />

      <Card flush className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-[--color-line] p-3 sm:p-4">
          <Tabs
            tabs={tabs}
            value={activeTab}
            onChange={(tab) => setFilters({ status: tab })}
            label="Warning workflow state"
          />

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-0 flex-1 sm:max-w-xs">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[--color-ink-faint]"
                aria-hidden="true"
              />
              <Input
                type="search"
                placeholder="Search title, summary or period"
                aria-label="Search warnings"
                value={filters.q}
                onChange={(event) => setFilters({ q: event.target.value })}
                className="h-8 pl-9 text-[13px]"
              />
            </div>

            <Select
              aria-label="Filter by severity"
              className="h-8 w-36 text-[13px]"
              value={filters.severity}
              onChange={(event) => setFilters({ severity: event.target.value })}
            >
              <option value="">All severities</option>
              {SEVERITY_ORDER.filter((level) => level !== 'unknown').map((level) => (
                <option key={level} value={level}>
                  {severity(level).label}
                </option>
              ))}
            </Select>

            <Select
              aria-label="Filter by risk type"
              className="h-8 w-40 text-[13px]"
              value={filters.type}
              onChange={(event) => setFilters({ type: event.target.value })}
            >
              <option value="">All risk types</option>
              {DOMAIN_ORDER.map((key) => (
                <option key={key} value={key}>
                  {domainDescriptor(key).label}
                </option>
              ))}
            </Select>

            {filtersActive && (
              <Button size="sm" variant="ghost" onClick={resetFilters}>
                <X className="size-3.5" aria-hidden="true" />
                Clear filters
              </Button>
            )}
          </div>
        </div>

        <div className="p-3 sm:p-4">
          <QueryBoundary
            query={alerts}
            skeleton={
              <div className="flex flex-col gap-2">
                {[0, 1, 2, 3, 4].map((index) => (
                  <Skeleton key={index} className="h-24" />
                ))}
              </div>
            }
            isEmpty={() => filtered.length === 0}
            empty={
              filtersActive ? (
                <EmptyState
                  icon={<Filter className="size-4.5" aria-hidden="true" />}
                  title="No warnings match these filters"
                  description="Clear or widen the filters to see more of the queue."
                  action={
                    <Button size="sm" variant="secondary" onClick={resetFilters}>
                      Clear filters
                    </Button>
                  }
                />
              ) : (
                <EmptyState
                  icon={<Inbox className="size-4.5" aria-hidden="true" />}
                  title={emptyTitleFor(activeTab)}
                  description={emptyDescriptionFor(activeTab)}
                />
              )
            }
          >
            {() => (
              <>
                <p className="mb-3 text-[12px] text-[--color-ink-muted]" role="status">
                  {formatCount(filtered.length)}{' '}
                  {filtered.length === 1 ? 'warning' : 'warnings'} shown
                </p>
                <ul className="flex flex-col gap-2">
                  {filtered.map((alert) => (
                    <li key={alert.id}>
                      <WarningRow
                        alert={alert}
                        onOpen={() => navigate(`/app/warnings/${alert.id}`)}
                      />
                    </li>
                  ))}
                </ul>
              </>
            )}
          </QueryBoundary>

          {alerts.isError && (
            <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
          )}
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------- row -- */

function WarningRow({ alert, onOpen }: { alert: AlertListItem; onOpen: () => void }) {
  const descriptor = severity(alert.risk_level);
  const state = workflow(alert.status);
  const needsDecision = !state.humanApproved;
  const urgent = needsDecision && descriptor.rank >= 3;

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cx(
        'flex w-full items-start gap-3 rounded-[--radius-md] border-l-[3px] bg-[--color-surface] p-3.5 text-left',
        'ring-1 transition-shadow hover:shadow-[--shadow-sm]',
        descriptor.accent,
        // Prominence for a critical warning still awaiting a decision, without
        // turning the whole surface red.
        urgent
          ? 'ring-[--color-risk-critical-line] bg-[--color-risk-critical-bg]/30'
          : 'ring-[--color-line] hover:ring-[--color-line-strong]',
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <RiskBadge level={alert.risk_level} size="sm" />
          <MetaChip>{domainDescriptor(alert.risk_domain).label}</MetaChip>
          <StatusBadge status={alert.status} size="sm" />
          <ClassificationBadge classification={alert.classification} />
        </div>

        <p className="mt-2 text-[14px] font-semibold leading-5 text-[--color-ink]">
          {alert.title}
        </p>
        <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-[--color-ink-secondary]">
          {alert.summary}
        </p>

        <dl className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[--color-ink-muted]">
          <div className="flex gap-1">
            <dt className="font-medium">Period</dt>
            <dd>{alert.target_period || '—'}</dd>
          </div>
          <div className="flex gap-1">
            <dt className="font-medium">Generated</dt>
            <dd title={formatDateTime(alert.created_at)}>{formatRelative(alert.created_at)}</dd>
          </div>
          {alert.published_at && (
            <div className="flex gap-1">
              <dt className="font-medium">Published</dt>
              <dd title={formatDateTime(alert.published_at)}>
                {formatRelative(alert.published_at)}
              </dd>
            </div>
          )}
        </dl>
      </div>

      <ChevronRight
        className="mt-1 size-4 shrink-0 text-[--color-ink-faint]"
        aria-hidden="true"
      />
    </button>
  );
}

/* -------------------------------------------------------------- messages -- */

function emptyTitleFor(tab: QueueTab): string {
  switch (tab) {
    case 'needs_review':
      return 'No warnings require review';
    case 'verification':
      return 'No warnings awaiting verification';
    case 'approved':
      return 'No approved warnings';
    case 'published':
      return 'No published warnings';
    case 'resolved':
      return 'No resolved warnings';
    default:
      return 'No warnings in scope';
  }
}

function emptyDescriptionFor(tab: QueueTab): string {
  switch (tab) {
    case 'needs_review':
      return 'No warnings currently require an analyst decision in your scope.';
    case 'verification':
      return 'No warning is currently waiting on field verification.';
    case 'approved':
      return 'No warning has been approved and is awaiting publication.';
    case 'published':
      return 'No warning has been published to its audience yet.';
    case 'resolved':
      return 'No warning has been resolved and archived.';
    default:
      return 'No governed warning records are visible to your role and geographic scope.';
  }
}
