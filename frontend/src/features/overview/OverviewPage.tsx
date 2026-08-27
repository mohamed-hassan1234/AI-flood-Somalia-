/**
 * National Early Warning Overview.
 *
 * Composition follows SUMMARY → MAP → PRIORITIES → EVIDENCE, so the country's
 * operational picture is readable in under ten seconds.
 *
 * Each panel owns its own query and its own failure state. A failing data
 * health widget must never blank the map or the review queue — partial service
 * degradation is the normal condition of this platform, not an exception.
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Database,
  Droplets,
  Inbox,
  Sun,
  TriangleAlert,
  Wheat,
} from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import {
  useAlerts,
  useBoundaries,
  useDashboardScopes,
  useDataSources,
  useNationalSummary,
} from '../../api/queries';
import { Button, Card, Select, Skeleton, cx } from '../../components/ui/primitives';
import {
  MetaBar,
  MetaItem,
  MetricCard,
  MetricCardSkeleton,
  PageHeader,
  SectionHeader,
} from '../../components/ui/layout';
import { EmptyState, ErrorState, Note, QueryBoundary } from '../../components/ui/states';
import {
  MetaChip,
  RiskBadge,
  StaleBadge,
  StatusBadge,
} from '../../components/intelligence/badges';
import { SomaliaMap, type MapUnit } from '../../components/maps/SomaliaMap';
import { useDomainIntelligence } from '../../hooks/useDomainIntelligence';
import { domain as domainDescriptor, severity, toSeverity } from '../../lib/risk';
import { formatCount, formatProbability, pluralise } from '../../lib/format';
import { formatDateTime, formatRelative, formatTime, nextScheduledRun } from '../../lib/time';
import type { AlertListItem, NationalDomainSummary, RiskDomain } from '../../types/api';

/* ------------------------------------------------------------ data status -- */

type DataStatus = 'good' | 'partial' | 'stale' | 'insufficient';

/**
 * Derives an overall data posture from the per-domain staleness the API
 * reports. Deliberately pessimistic: any stale domain downgrades the whole
 * picture, because an operator reading "GOOD" must be able to trust it.
 */
function deriveDataStatus(domains: NationalDomainSummary[] | undefined): {
  status: DataStatus;
  label: string;
  chip: string;
  detail: string;
} {
  if (!domains?.length) {
    return {
      status: 'insufficient',
      label: 'INSUFFICIENT',
      chip: 'bg-[--color-muted-bg] text-[--color-muted-fg] ring-[--color-muted-line]',
      detail: 'No risk domains were returned for this scope.',
    };
  }

  const evaluated = domains.filter((item) => item.admin_units_evaluated > 0);
  const stale = domains.filter((item) => item.stale);

  if (evaluated.length === 0) {
    return {
      status: 'insufficient',
      label: 'INSUFFICIENT',
      chip: 'bg-[--color-muted-bg] text-[--color-muted-fg] ring-[--color-muted-line]',
      detail: 'No domain currently holds evaluated intelligence for this scope.',
    };
  }
  if (stale.length === domains.length) {
    return {
      status: 'stale',
      label: 'STALE',
      chip: 'bg-[--color-risk-warning-bg] text-[--color-risk-warning-fg] ring-[--color-risk-warning-line]',
      detail: 'Every domain is outside its accepted freshness window.',
    };
  }
  if (stale.length > 0 || evaluated.length < domains.length) {
    return {
      status: 'partial',
      label: 'PARTIAL',
      chip: 'bg-[--color-risk-watch-bg] text-[--color-risk-watch-fg] ring-[--color-risk-watch-line]',
      detail: `${stale.length > 0 ? `${stale.length} of ${domains.length} domains are stale. ` : ''}${
        evaluated.length < domains.length
          ? `${domains.length - evaluated.length} domains hold no evaluated intelligence.`
          : ''
      }`.trim(),
    };
  }
  return {
    status: 'good',
    label: 'GOOD',
    chip: 'bg-[--color-ok-bg] text-[--color-ok-fg] ring-[--color-ok-line]',
    detail: 'All domains are within their accepted freshness windows.',
  };
}

/* ---------------------------------------------------------- domain cards -- */

const DOMAIN_ICON: Record<RiskDomain, typeof Sun> = {
  drought: Sun,
  river_flood: Droplets,
  flash_flood: Droplets,
  food_security_deterioration: Wheat,
};

function DomainSummaryCard({
  summary,
  onOpen,
}: {
  summary: NationalDomainSummary;
  onOpen?: () => void;
}) {
  const descriptor = domainDescriptor(summary.domain);
  const Icon = DOMAIN_ICON[summary.domain];
  const level = toSeverity(summary.level);
  const levelDescriptor = severity(level);
  const evaluated = summary.admin_units_evaluated;

  return (
    <MetricCard
      label={
        <span className="flex items-center gap-1.5">
          <Icon className="size-3.5" aria-hidden="true" />
          {descriptor.label}
        </span>
      }
      value={
        evaluated > 0 ? (
          <span className={levelDescriptor.text}>{levelDescriptor.label}</span>
        ) : (
          <span className="text-[20px] text-[--color-ink-muted]">No evidence</span>
        )
      }
      accent={evaluated > 0 ? levelDescriptor.accent : 'border-l-[--color-muted-line]'}
      badge={summary.stale ? <StaleBadge asOf={summary.as_of} /> : undefined}
      caption={
        evaluated > 0
          ? `Highest current level across ${pluralise(evaluated, descriptor.unitNoun, descriptor.unitNounPlural)}`
          : `No ${descriptor.unitNoun} in this scope holds current evaluated intelligence.`
      }
      onClick={onOpen}
      footer={
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[--color-ink-muted]">
          {summary.as_of && (
            <span title={formatDateTime(summary.as_of)}>
              Updated {formatRelative(summary.as_of)}
            </span>
          )}
          <span>{pluralise(summary.source_ids.length, 'source')}</span>
        </div>
      }
    />
  );
}

/* --------------------------------------------------------- priority queue -- */

/** Warning states that still require a human decision. */
const NEEDS_DECISION = new Set(['draft', 'in_review', 'verification_required', 'verified']);

function PriorityWarnings() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const alerts = useAlerts(can('alerts.read'));

  const priority = useMemo(() => {
    const pending = (alerts.data ?? []).filter((alert) => NEEDS_DECISION.has(alert.status));
    // Most severe first; ties broken by age, oldest first — a critical warning
    // that has been waiting is the most urgent thing on this screen.
    return [...pending]
      .sort((a, b) => {
        const bySeverity = severity(b.risk_level).rank - severity(a.risk_level).rank;
        if (bySeverity !== 0) return bySeverity;
        return a.created_at.localeCompare(b.created_at);
      })
      .slice(0, 6);
  }, [alerts.data]);

  if (!can('alerts.read')) return null;

  return (
    <Card flush className="flex h-full flex-col">
      <div className="border-b border-[--color-line] px-4 py-3">
        <SectionHeader
          className="mb-0"
          title="Priority warnings"
          description="Awaiting a human decision"
          actions={
            <Button size="sm" variant="ghost" onClick={() => navigate('/app/warnings')}>
              All warnings
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Button>
          }
        />
      </div>

      <div className="min-h-0 flex-1 p-3">
        <QueryBoundary
          query={alerts}
          compact
          skeleton={
            <div className="flex flex-col gap-2">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-20" />
              ))}
            </div>
          }
          isEmpty={() => priority.length === 0}
          empty={
            <EmptyState
              compact
              icon={<Inbox className="size-4.5" aria-hidden="true" />}
              title="No warnings require review"
              description="Nothing is currently waiting on an analyst decision in your scope."
            />
          }
        >
          {() => (
            <ul className="flex flex-col gap-2">
              {priority.map((alert) => (
                <li key={alert.id}>
                  <PriorityWarningRow
                    alert={alert}
                    onOpen={() => navigate(`/app/warnings/${alert.id}`)}
                  />
                </li>
              ))}
            </ul>
          )}
        </QueryBoundary>
      </div>
    </Card>
  );
}

function PriorityWarningRow({
  alert,
  onOpen,
}: {
  alert: AlertListItem;
  onOpen: () => void;
}) {
  const descriptor = severity(alert.risk_level);
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cx(
        'flex w-full flex-col gap-2 rounded-[--radius-md] border-l-[3px] bg-[--color-surface] p-3 text-left',
        'ring-1 ring-[--color-line] transition-shadow hover:shadow-[--shadow-sm] hover:ring-[--color-line-strong]',
        descriptor.accent,
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <RiskBadge level={alert.risk_level} size="sm" />
        <MetaChip>{domainDescriptor(alert.risk_domain).label}</MetaChip>
        <StatusBadge status={alert.status} size="sm" />
      </div>
      <p className="line-clamp-2 text-[13px] font-medium leading-5 text-[--color-ink]">
        {alert.title}
      </p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[--color-ink-muted]">
        <span>{alert.target_period}</span>
        <span title={formatDateTime(alert.created_at)}>
          Generated {formatRelative(alert.created_at)}
        </span>
      </div>
    </button>
  );
}

/* ------------------------------------------------------------ data health -- */

function DataHealthSummary() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const sources = useDataSources(can('data_sources.read'));

  if (!can('data_sources.read')) return null;

  return (
    <Card className="flex h-full flex-col">
      <SectionHeader
        title="Data health"
        description="Configured operational sources"
        actions={
          <Button size="sm" variant="ghost" onClick={() => navigate('/app/data-health')}>
            Details
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Button>
        }
      />
      <QueryBoundary
        query={sources}
        compact
        skeleton={
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-9" />
            ))}
          </div>
        }
        isEmpty={(data) => data.length === 0}
        empty={
          <EmptyState
            compact
            icon={<Database className="size-4.5" aria-hidden="true" />}
            title="No data sources configured"
            description="No operational source has been registered on this deployment."
          />
        }
      >
        {(data) => (
          <ul className="flex flex-col divide-y divide-[--color-line]">
            {data.slice(0, 6).map((source) => (
              <li key={source.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-[--color-ink]">
                    {source.name}
                  </p>
                  <p className="truncate text-[11px] text-[--color-ink-muted]">{source.domain}</p>
                </div>
                {/* Freshness per source is resolved on the Data Health page,
                    which queries each source's own health endpoint. Here we
                    show only what the list endpoint actually returns. */}
                <MetaChip className={source.enabled ? '' : 'opacity-60'}>
                  {source.enabled ? 'Enabled' : 'Disabled'}
                </MetaChip>
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
    </Card>
  );
}

/* ------------------------------------------------------------------ page -- */

export function OverviewPage() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [scopeId, setScopeId] = useState('');

  const mayReadPredictions = can('predictions.read');
  const mayReadGeography = can('geography.read');

  const scopes = useDashboardScopes(mayReadGeography);
  const summary = useNationalSummary(scopeId || undefined, mayReadPredictions || can('alerts.read'));
  const boundaries = useBoundaries(undefined, mayReadGeography);

  // The map shades whichever domain currently carries the highest severity, so
  // the landing view leads with the most consequential picture.
  const drought = useDomainIntelligence('drought', mayReadPredictions);
  const flood = useDomainIntelligence('river_flood', mayReadPredictions);
  const foodSecurity = useDomainIntelligence('food_security_deterioration', mayReadPredictions);

  const mapUnits = useMemo<MapUnit[]>(() => {
    // Drought is district-scoped and covers the most geography, so it is the
    // honest default choropleth. Flood is deliberately excluded — it is
    // gauge-scoped and must not be painted as area coverage.
    return drought.ranked.map((row) => ({
      adminUnitId: row.signal.admin_unit_id,
      level: row.level,
      name: row.unitName,
      detail:
        row.probability !== null
          ? `Probability ${formatProbability(row.probability)}`
          : 'Probability withheld',
    }));
  }, [drought.ranked]);

  const dataStatus = deriveDataStatus(summary.data?.domains);
  const nextRun = useMemo(() => nextScheduledRun(), []);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="National situation"
        title="National Early Warning Overview"
        description="Current modelled risk across drought, river flood and food security, with the evidence and governance state attached to every signal."
        actions={
          scopes.data && scopes.data.length > 0 ? (
            <label className="flex items-center gap-2">
              <span className="text-[12px] font-medium text-[--color-ink-secondary]">Scope</span>
              <Select
                value={scopeId}
                onChange={(event) => setScopeId(event.target.value)}
                aria-label="Dashboard geographic scope"
                className="w-48"
              >
                <option value="">National</option>
                {scopes.data.map((scope) => (
                  <option key={scope.id} value={scope.id}>
                    {scope.name} ({scope.level})
                  </option>
                ))}
              </Select>
            </label>
          ) : undefined
        }
        meta={
          <MetaBar>
            {summary.data ? (
              <>
                <MetaItem
                  label="As of"
                  value={
                    <time dateTime={summary.data.generated_at}>
                      {formatDateTime(summary.data.generated_at)}
                    </time>
                  }
                />
                <MetaItem label="Scope" value={`${summary.data.scope_name} · ${summary.data.scope_level}`} />
                <MetaItem label="Next scheduled run" value={formatTime(nextRun)} />
                <MetaItem
                  label="Data status"
                  value={
                    <span
                      className={cx(
                        'rounded-[--radius-xs] px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset',
                        dataStatus.chip,
                      )}
                      title={dataStatus.detail}
                    >
                      {dataStatus.label}
                    </span>
                  }
                />
                {summary.data.boundary_version && (
                  <MetaItem label="Boundary" value={summary.data.boundary_version} />
                )}
              </>
            ) : (
              <MetaItem label="As of" value={summary.isPending ? 'Loading…' : 'Unavailable'} />
            )}
          </MetaBar>
        }
      />

      {/* An honest banner whenever the platform's own summary reports degraded
          inputs. This must never be suppressed to make the screen look calm. */}
      {summary.data && dataStatus.status !== 'good' && (
        <Note tone="caution" icon={<TriangleAlert className="size-3.5" aria-hidden="true" />}>
          <span className="font-semibold">
            Current intelligence is limited ({dataStatus.label.toLowerCase()}).
          </span>{' '}
          {dataStatus.detail} Risk levels below reflect the most recent eligible evidence only.
        </Note>
      )}

      {/* ---- SUMMARY ------------------------------------------------ */}
      <section aria-label="National summary">
        <QueryBoundary
          query={summary}
          skeleton={
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((index) => (
                <MetricCardSkeleton key={index} />
              ))}
            </div>
          }
          isEmpty={(data) => data.domains.length === 0}
          empty={
            <EmptyState
              title="No current intelligence"
              description="No eligible intelligence is available for this geography and period."
            />
          }
        >
          {(data) => (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {data.domains.map((item) => (
                <DomainSummaryCard
                  key={item.domain}
                  summary={item}
                  onOpen={() => navigate(domainRoute(item.domain))}
                />
              ))}
              {can('alerts.read') && <ReviewQueueCard />}
            </div>
          )}
        </QueryBoundary>
      </section>

      {/* ---- MAP + PRIORITIES --------------------------------------- */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,1fr)]">
        <Card flush className="overflow-hidden">
          <div className="border-b border-[--color-line] px-4 py-3">
            <SectionHeader
              className="mb-0"
              title="Somalia risk map"
              description="District drought signal. Gauge-scoped flood intelligence is shown on the flood page."
              actions={
                <Button size="sm" variant="ghost" onClick={() => navigate('/app/map')}>
                  Open explorer
                  <ArrowRight className="size-3.5" aria-hidden="true" />
                </Button>
              }
            />
          </div>
          {mayReadGeography ? (
            <SomaliaMap
              boundaries={boundaries.data}
              units={mapUnits}
              loading={boundaries.isPending || drought.isPending}
              legendTitle="Drought risk"
              scopeNote="Shading shows district-level drought signal only."
              height="h-[380px] sm:h-[460px]"
              className="rounded-none ring-0"
              onSelectUnit={() => navigate('/app/map')}
            />
          ) : (
            <div className="p-4">
              <EmptyState
                compact
                title="Map unavailable for your role"
                description="Displaying the national map requires the geography read capability."
              />
            </div>
          )}
          {boundaries.isError && (
            <div className="p-4">
              <ErrorState compact error={boundaries.error} onRetry={() => void boundaries.refetch()} />
            </div>
          )}
        </Card>

        <PriorityWarnings />
      </div>

      {/* ---- EVIDENCE ------------------------------------------------ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(300px,1fr)]">
        <Card>
          <SectionHeader
            title="Highest current risk"
            description="Most severe modelled units across all domains you can read"
          />
          {mayReadPredictions ? (
            <TopRiskTable
              rows={[...drought.ranked, ...flood.ranked, ...foodSecurity.ranked]
                .filter((row) => severity(row.level).rank >= 1)
                .sort((a, b) => {
                  const bySeverity = severity(b.level).rank - severity(a.level).rank;
                  if (bySeverity !== 0) return bySeverity;
                  return (b.probability ?? -1) - (a.probability ?? -1);
                })
                .slice(0, 8)}
              pending={drought.isPending || flood.isPending || foodSecurity.isPending}
            />
          ) : (
            <EmptyState
              compact
              title="Risk detail not available for your role"
              description="Reading modelled risk requires the predictions read capability."
            />
          )}
        </Card>

        <DataHealthSummary />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- fragments -- */

function domainRoute(key: RiskDomain): string {
  switch (key) {
    case 'drought':
      return '/app/drought';
    case 'river_flood':
    case 'flash_flood':
      return '/app/flood';
    case 'food_security_deterioration':
      return '/app/food-security';
    default:
      return '/app/map';
  }
}

function ReviewQueueCard() {
  const navigate = useNavigate();
  const alerts = useAlerts(true);

  const counts = useMemo(() => {
    const data = alerts.data ?? [];
    return {
      needsReview: data.filter((alert) => NEEDS_DECISION.has(alert.status)).length,
      published: data.filter((alert) => alert.status === 'published').length,
      severe: data.filter(
        (alert) => NEEDS_DECISION.has(alert.status) && severity(alert.risk_level).rank >= 3,
      ).length,
    };
  }, [alerts.data]);

  if (alerts.isPending) return <MetricCardSkeleton />;
  if (alerts.isError) {
    return (
      <Card className="flex items-center">
        <ErrorState compact error={alerts.error} onRetry={() => void alerts.refetch()} />
      </Card>
    );
  }

  return (
    <MetricCard
      label={
        <span className="flex items-center gap-1.5">
          <Inbox className="size-3.5" aria-hidden="true" />
          Warnings
        </span>
      }
      value={formatCount(counts.needsReview)}
      unit="awaiting review"
      accent={counts.severe > 0 ? 'border-l-[--color-risk-critical-solid]' : 'border-l-[--color-line-strong]'}
      caption={
        counts.severe > 0
          ? `${counts.severe} critical ${counts.severe === 1 ? 'warning needs' : 'warnings need'} attention`
          : 'No critical warnings are waiting on a decision'
      }
      onClick={() => navigate('/app/warnings?status=needs_review')}
      footer={
        <span className="text-[11px] text-[--color-ink-muted]">
          {formatCount(counts.published)} published
        </span>
      }
    />
  );
}

function TopRiskTable({
  rows,
  pending,
}: {
  rows: ReturnType<typeof useDomainIntelligence>['ranked'];
  pending: boolean;
}) {
  const navigate = useNavigate();

  if (pending) {
    return (
      <div className="flex flex-col gap-2">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-9" />
        ))}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        compact
        title="No elevated risk in scope"
        description="No unit currently sits at Watch or above in the domains you can read."
      />
    );
  }

  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-1 pb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-muted]">
              Location
            </th>
            <th scope="col" className="px-1 pb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-muted]">
              Domain
            </th>
            <th scope="col" className="px-1 pb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-muted]">
              Risk
            </th>
            <th scope="col" className="px-1 pb-2 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-muted]">
              Probability
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.signal.id}
              onClick={() => navigate(domainRoute(row.signal.domain))}
              className="cursor-pointer border-t border-[--color-line] transition-colors hover:bg-[--color-surface-subtle]"
            >
              <td className="px-1 py-2">
                <p className="text-[13px] font-medium text-[--color-ink]">{row.unitName}</p>
                {row.parentName && (
                  <p className="text-[11px] text-[--color-ink-muted]">{row.parentName}</p>
                )}
              </td>
              <td className="px-1 py-2">
                <MetaChip>{domainDescriptor(row.signal.domain).label}</MetaChip>
              </td>
              <td className="px-1 py-2">
                <span className="flex items-center gap-1.5">
                  <RiskBadge level={row.level} size="sm" />
                  {row.degraded && <StaleBadge />}
                </span>
              </td>
              <td className="px-1 py-2 text-right text-[13px] font-medium tabular-nums text-[--color-ink]">
                {formatProbability(row.probability)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
