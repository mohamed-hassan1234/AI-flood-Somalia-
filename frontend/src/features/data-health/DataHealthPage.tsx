/**
 * Data Health — source freshness and ingestion status.
 *
 * The governing rule: each source is judged against *its own* declared
 * cadence, never a blanket daily expectation. IPC is not late because it did
 * not publish today; MODIS composites are not stale at 24 hours. The backend
 * already encodes this in `assess_health`, comparing age against the source's
 * `expected_frequency_minutes`, so this page renders that verdict rather than
 * recomputing freshness with an assumption of its own.
 *
 * Health is fetched per source, so one failing endpoint degrades a single row
 * instead of blanking the page.
 */

import { useMemo } from 'react';
import { Database, TriangleAlert } from 'lucide-react';

import { useDataSourceHealth, useDataSources } from '../../api/queries';
import { Card, Skeleton, cx } from '../../components/ui/primitives';
import {
  MetaBar,
  MetaItem,
  MetricCard,
  PageHeader,
  SectionHeader,
  Table,
  TableScroll,
  Td,
  Th,
} from '../../components/ui/layout';
import { EmptyState, Note, QueryBoundary } from '../../components/ui/states';
import { ClassificationBadge, FreshnessBadge, MetaChip } from '../../components/intelligence/badges';
import { health } from '../../lib/risk';
import { formatCadence, formatCount, humanise } from '../../lib/format';
import { formatDateTime } from '../../lib/time';
import type { DataSource } from '../../types/api';

export function DataHealthPage() {
  const sources = useDataSources(true);

  const enabled = useMemo(
    () => (sources.data ?? []).filter((source) => source.enabled),
    [sources.data],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Assurance"
        title="Data Health"
        description="Ingestion status for every configured operational source. Each source is assessed against its own declared cadence."
        meta={
          <MetaBar>
            <MetaItem label="Sources configured" value={formatCount(sources.data?.length ?? 0)} />
            <MetaItem label="Enabled" value={formatCount(enabled.length)} />
            <MetaItem
              label="Verified metadata"
              value={formatCount((sources.data ?? []).filter((s) => s.verified).length)}
            />
          </MetaBar>
        }
      />

      <Note tone="neutral" icon={<TriangleAlert className="size-3.5" aria-hidden="true" />}>
        <span className="font-semibold text-[--color-ink]">Cadence matters. </span>
        A source is <em>fresh</em> when its last successful retrieval falls within its own expected
        frequency, <em>delayed</em> up to twice that interval, and <em>stale</em> beyond it. Sources
        that publish weekly, seasonally or on assessment cycles are not judged by a daily standard.
      </Note>

      <QueryBoundary
        query={sources}
        skeleton={
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-24" />
              ))}
            </div>
            <Skeleton className="h-72" />
          </div>
        }
        isEmpty={(data) => data.length === 0}
        empty={
          <EmptyState
            icon={<Database className="size-4.5" aria-hidden="true" />}
            title="No data sources configured"
            description="No operational source has been registered on this deployment. Source registration is an administrative action."
          />
        }
      >
        {(data) => (
          <>
            <Card flush>
              <div className="border-b border-[--color-line] px-4 py-3">
                <SectionHeader
                  className="mb-0"
                  title="Source status"
                  description="Freshness is resolved per source from its own health endpoint"
                />
              </div>

              {/* Desktop table. */}
              <div className="hidden md:block">
                <TableScroll className="px-4 py-2 sm:px-4">
                  <Table>
                    <thead>
                      <tr>
                        <Th>Source</Th>
                        <Th>Purpose</Th>
                        <Th>Cadence</Th>
                        <Th>Freshness</Th>
                        <Th align="right">Last success</Th>
                        <Th align="right" className="hidden lg:table-cell">
                          Rows
                        </Th>
                        <Th className="hidden lg:table-cell">Access</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.map((source) => (
                        <SourceRow key={source.id} source={source} />
                      ))}
                    </tbody>
                  </Table>
                </TableScroll>
              </div>

              {/* Mobile cards. */}
              <ul className="flex flex-col gap-2 p-3 md:hidden">
                {data.map((source) => (
                  <li key={source.id}>
                    <SourceCard source={source} />
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <SectionHeader
                title="Governance metadata"
                description="Sources without complete licensing and attribution metadata are flagged"
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {data.map((source) => (
                  <div
                    key={source.id}
                    className="flex flex-col gap-2 rounded-[--radius-md] bg-[--color-surface-subtle] p-3 ring-1 ring-[--color-line]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 truncate text-[13px] font-semibold text-[--color-ink]">
                        {source.name}
                      </p>
                      <MetaChip
                        className={
                          source.verified
                            ? 'bg-[--color-ok-bg] text-[--color-ok-fg]'
                            : 'bg-[--color-muted-bg] text-[--color-muted-fg]'
                        }
                      >
                        {source.verified ? 'Verified' : 'Unverified'}
                      </MetaChip>
                    </div>
                    <dl className="flex flex-col gap-1 text-[12px]">
                      <Fact label="Owner" value={source.owner} />
                      <Fact label="Licence" value={source.license} />
                      <Fact label="Resolution" value={source.geographic_resolution} />
                    </dl>
                  </div>
                ))}
              </div>
            </Card>
          </>
        )}
      </QueryBoundary>
    </div>
  );
}

/* ------------------------------------------------------------------- row -- */

function SourceRow({ source }: { source: DataSource }) {
  const healthQuery = useDataSourceHealth(source.id, true);
  const descriptor = healthQuery.data ? health(healthQuery.data.status) : null;

  return (
    <tr className={cx(!source.enabled && 'opacity-55')}>
      <Td>
        <p className="font-medium text-[--color-ink]">{source.name}</p>
        {!source.enabled && (
          <p className="text-[11px] text-[--color-ink-muted]">Disabled</p>
        )}
      </Td>
      <Td className="text-[--color-ink-secondary]">{humanise(source.domain)}</Td>
      <Td className="whitespace-nowrap text-[--color-ink-secondary]">
        {formatCadence(source.expected_frequency_minutes)}
      </Td>
      <Td>
        {healthQuery.isPending ? (
          <Skeleton className="h-5 w-20" />
        ) : healthQuery.isError ? (
          // One failing health endpoint degrades this cell only.
          <MetaChip title={healthQuery.error.message}>Status unavailable</MetaChip>
        ) : (
          <FreshnessBadge size="sm" status={healthQuery.data?.status} />
        )}
      </Td>
      <Td align="right" className="whitespace-nowrap text-[--color-ink-secondary]">
        {healthQuery.data?.last_success
          ? formatDateTime(healthQuery.data.last_success)
          : healthQuery.isPending
            ? '—'
            : 'Never'}
      </Td>
      <Td align="right" className="hidden tabular-nums text-[--color-ink-secondary] lg:table-cell">
        {healthQuery.data ? (
          <span title={`${healthQuery.data.rows_quarantined} quarantined`}>
            {formatCount(healthQuery.data.rows_received)}
            {healthQuery.data.rows_quarantined > 0 && (
              <span className="ml-1 text-[--color-risk-warning-fg]">
                ({formatCount(healthQuery.data.rows_quarantined)} held)
              </span>
            )}
          </span>
        ) : (
          '—'
        )}
      </Td>
      <Td className="hidden lg:table-cell">
        <span className="flex items-center gap-1.5">
          <MetaChip>{humanise(source.access_method)}</MetaChip>
          <ClassificationBadge classification={source.classification} />
        </span>
      </Td>
      {descriptor?.degraded && (
        <td className="sr-only">{descriptor.meaning}</td>
      )}
    </tr>
  );
}

function SourceCard({ source }: { source: DataSource }) {
  const healthQuery = useDataSourceHealth(source.id, true);

  return (
    <div
      className={cx(
        'flex flex-col gap-2 rounded-[--radius-md] bg-[--color-surface] p-3 ring-1 ring-[--color-line]',
        !source.enabled && 'opacity-55',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-[13px] font-semibold text-[--color-ink]">{source.name}</p>
        {healthQuery.isPending ? (
          <Skeleton className="h-5 w-16" />
        ) : healthQuery.isError ? (
          <MetaChip>Status unavailable</MetaChip>
        ) : (
          <FreshnessBadge size="sm" status={healthQuery.data?.status} />
        )}
      </div>
      <dl className="flex flex-col gap-1 text-[12px]">
        <Fact label="Purpose" value={humanise(source.domain)} />
        <Fact label="Cadence" value={formatCadence(source.expected_frequency_minutes)} />
        <Fact
          label="Last success"
          value={
            healthQuery.data?.last_success
              ? formatDateTime(healthQuery.data.last_success)
              : healthQuery.isPending
                ? null
                : 'Never'
          }
        />
      </dl>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-[--color-ink-muted]">{label}</dt>
      <dd
        className={cx(
          'truncate text-right font-medium',
          value ? 'text-[--color-ink]' : 'text-[--color-ink-faint]',
        )}
      >
        {value ?? 'Not declared'}
      </dd>
    </div>
  );
}

/** Compact health tile used by the overview page. */
export function HealthSummaryTile({
  label,
  count,
  tone,
}: {
  label: string;
  count: number;
  tone: 'ok' | 'warn' | 'bad';
}) {
  return (
    <MetricCard
      label={label}
      value={formatCount(count)}
      accent={
        tone === 'bad'
          ? 'border-l-[--color-risk-critical-solid]'
          : tone === 'warn'
            ? 'border-l-[--color-risk-watch-solid]'
            : 'border-l-[--color-risk-normal-solid]'
      }
    />
  );
}
