/**
 * Drought Intelligence — district-scoped.
 *
 * Layout is map + ranked table, with selection opening the shared intelligence
 * detail in a drawer. The page states explicitly that this is an agro-climatic
 * early-warning signal, not a famine forecast and not an IPC classification.
 */

import { useMemo, useState } from 'react';
import { Sun } from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import { useBoundaries } from '../../api/queries';
import { useDomainIntelligence, type IntelligenceRow } from '../../hooks/useDomainIntelligence';
import { Card, Select, cx } from '../../components/ui/primitives';
import {
  Drawer,
  MetaBar,
  MetaItem,
  MetricCard,
  MetricCardSkeleton,
  PageHeader,
  SectionHeader,
} from '../../components/ui/layout';
import { EmptyState, ErrorState } from '../../components/ui/states';
import { IntelligenceDetail, ScopeNotice } from '../../components/intelligence/IntelligenceDetail';
import { RiskTable } from '../../components/intelligence/RiskTable';
import { MetaChip } from '../../components/intelligence/badges';
import { SomaliaMap, type MapUnit } from '../../components/maps/SomaliaMap';
import { domain as domainDescriptor, severity, SEVERITY_ORDER, type Severity } from '../../lib/risk';
import { formatCount, formatProbability, humanise } from '../../lib/format';
import { formatDateTime } from '../../lib/time';
import { useUrlFilters } from '../../hooks/useUrlFilters';

export function DroughtPage() {
  const { can } = useAuth();
  const descriptor = domainDescriptor('drought');

  const intelligence = useDomainIntelligence('drought', can('predictions.read'));
  const boundaries = useBoundaries(undefined, can('geography.read'));

  const [filters, setFilters] = useUrlFilters({ severity: '', region: '' });
  const [selected, setSelected] = useState<IntelligenceRow | null>(null);

  const regions = useMemo(() => {
    const names = new Set<string>();
    for (const row of intelligence.ranked) {
      if (row.parentName) names.add(row.parentName);
    }
    return [...names].sort();
  }, [intelligence.ranked]);

  const filtered = useMemo(
    () =>
      intelligence.ranked.filter((row) => {
        if (filters.severity && row.level !== filters.severity) return false;
        if (filters.region && row.parentName !== filters.region) return false;
        return true;
      }),
    [intelligence.ranked, filters],
  );

  const mapUnits = useMemo<MapUnit[]>(
    () =>
      filtered.map((row) => ({
        adminUnitId: row.signal.admin_unit_id,
        level: row.level,
        name: row.unitName,
        detail:
          row.probability !== null
            ? `Probability ${formatProbability(row.probability)}`
            : 'Probability withheld',
      })),
    [filtered],
  );

  if (!can('predictions.read')) {
    return (
      <div className="flex flex-col gap-5">
        <PageHeader eyebrow="Drought" title={descriptor.longLabel} />
        <EmptyState
          title="Risk detail not available for your role"
          description="Reading modelled risk requires the predictions read capability."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Risk domain"
        title={descriptor.longLabel}
        description="District-level drought risk from the operational early-warning model, with vegetation, rainfall and climate drivers attached to every signal."
        meta={
          <MetaBar>
            <MetaItem
              label="Districts evaluated"
              value={formatCount(intelligence.unitsEvaluated)}
            />
            <MetaItem
              label="Highest level"
              value={severity(intelligence.highest).label}
            />
            <MetaItem
              label="Latest signal"
              value={
                intelligence.latestAt ? formatDateTime(intelligence.latestAt) : 'Not available'
              }
            />
          </MetaBar>
        }
      />

      <ScopeNotice domain="drought" />

      {/* ---- summary --------------------------------------------------- */}
      <section aria-label="Drought summary" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {intelligence.isPending ? (
          [0, 1, 2, 3].map((index) => <MetricCardSkeleton key={index} />)
        ) : (
          <>
            <MetricCard
              label={
                <span className="flex items-center gap-1.5">
                  <Sun className="size-3.5" aria-hidden="true" />
                  Highest level
                </span>
              }
              value={
                <span className={severity(intelligence.highest).text}>
                  {severity(intelligence.highest).label}
                </span>
              }
              accent={severity(intelligence.highest).accent}
              caption="Most severe district signal currently in scope"
            />
            <MetricCard
              label="Districts monitored"
              value={formatCount(intelligence.unitsEvaluated)}
              caption="Districts with a current drought signal"
            />
            <MetricCard
              label="Watch or above"
              value={formatCount(intelligence.watchPlus)}
              accent={intelligence.watchPlus > 0 ? 'border-l-[--color-risk-watch-solid]' : undefined}
              caption="Districts at Watch, Warning or Critical"
            />
            <MetricCard
              label="Warning or above"
              value={formatCount(intelligence.warningPlus)}
              accent={
                intelligence.warningPlus > 0 ? 'border-l-[--color-risk-warning-solid]' : undefined
              }
              caption={
                intelligence.criticalCount > 0
                  ? `${formatCount(intelligence.criticalCount)} at Critical`
                  : 'No district at Critical'
              }
            />
          </>
        )}
      </section>

      {intelligence.isError && (
        <ErrorState error={intelligence.error} onRetry={intelligence.refetch} />
      )}

      {/* ---- map + table ----------------------------------------------- */}
      {!intelligence.isError && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <Card flush className="overflow-hidden">
            <div className="border-b border-[--color-line] px-4 py-3">
              <SectionHeader
                className="mb-0"
                title="District drought risk"
                description="Select a district to open its full intelligence record"
              />
            </div>
            {can('geography.read') ? (
              <SomaliaMap
                boundaries={boundaries.data}
                units={mapUnits}
                loading={boundaries.isPending || intelligence.isPending}
                legendTitle="Drought risk"
                scopeNote="District-level drought signal only."
                selectedId={selected?.signal.admin_unit_id ?? null}
                className="rounded-none ring-0"
                height="h-[400px] sm:h-[520px]"
                onSelectUnit={(id) => {
                  const row = intelligence.ranked.find((item) => item.signal.admin_unit_id === id);
                  if (row) setSelected(row);
                }}
              />
            ) : (
              <div className="p-4">
                <EmptyState
                  compact
                  title="Map unavailable for your role"
                  description="Displaying boundaries requires the geography read capability."
                />
              </div>
            )}
          </Card>

          <Card flush className="flex flex-col overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-[--color-line] px-4 py-3">
              <SectionHeader
                className="mb-0"
                title="Ranked district risk"
                description={`${formatCount(filtered.length)} of ${formatCount(intelligence.unitsEvaluated)} districts shown`}
              />
              <div className="flex flex-wrap gap-2">
                <label className="flex items-center gap-2">
                  <span className="text-[12px] font-medium text-[--color-ink-secondary]">
                    Severity
                  </span>
                  <Select
                    aria-label="Filter by severity"
                    className="h-8 w-36 text-[13px]"
                    value={filters.severity}
                    onChange={(event) => setFilters({ severity: event.target.value })}
                  >
                    <option value="">All levels</option>
                    {SEVERITY_ORDER.map((level) => (
                      <option key={level} value={level}>
                        {severity(level).label}
                      </option>
                    ))}
                  </Select>
                </label>
                {regions.length > 0 && (
                  <label className="flex items-center gap-2">
                    <span className="text-[12px] font-medium text-[--color-ink-secondary]">
                      Region
                    </span>
                    <Select
                      aria-label="Filter by region"
                      className="h-8 w-40 text-[13px]"
                      value={filters.region}
                      onChange={(event) => setFilters({ region: event.target.value })}
                    >
                      <option value="">All regions</option>
                      {regions.map((region) => (
                        <option key={region} value={region}>
                          {region}
                        </option>
                      ))}
                    </Select>
                  </label>
                )}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              <RiskTable
                rows={filtered}
                unitHeader="District"
                pending={intelligence.isPending}
                selectedId={selected?.signal.admin_unit_id ?? null}
                onSelect={setSelected}
                columns={[
                  {
                    id: 'period',
                    header: 'Target period',
                    secondary: true,
                    render: (row) => (
                      <span className="text-[--color-ink-secondary]">
                        {row.signal.target_period || '—'}
                      </span>
                    ),
                  },
                ]}
                emptyTitle={
                  filters.severity || filters.region
                    ? 'No districts match these filters'
                    : 'No current drought intelligence'
                }
                emptyDescription={
                  filters.severity || filters.region
                    ? 'Clear or widen the filters to see more districts.'
                    : 'No eligible drought intelligence is available for your geographic scope and the current period.'
                }
              />
            </div>
          </Card>
        </div>
      )}

      <DroughtDetailDrawer row={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

/* ---------------------------------------------------------------- drawer -- */

function DroughtDetailDrawer({
  row,
  onClose,
}: {
  row: IntelligenceRow | null;
  onClose: () => void;
}) {
  return (
    <Drawer
      open={row !== null}
      onClose={onClose}
      title={row?.unitName ?? 'District intelligence'}
      description={row?.parentName}
    >
      {row && (
        <IntelligenceDetail
          row={row}
          compact
          exposure={
            <p className="text-[13px] leading-5 text-[--color-ink-muted]">
              Population exposure for this district is reported through the exposure assessment
              attached to an approved warning. Where no assessment exists, no figure is shown
              rather than an estimate being substituted.
            </p>
          }
        />
      )}
    </Drawer>
  );
}

/** Small helper used by domain pages that show a level distribution strip. */
export function SeverityDistribution({
  counts,
  total,
  className,
}: {
  counts: Record<Severity, number>;
  total: number;
  className?: string;
}) {
  if (total === 0) return null;
  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-[--color-surface-sunken]">
        {SEVERITY_ORDER.map((level) => {
          const value = counts[level];
          if (!value) return null;
          return (
            <span
              key={level}
              style={{ width: `${(value / total) * 100}%`, background: severity(level).solid }}
              title={`${severity(level).label}: ${value}`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {SEVERITY_ORDER.filter((level) => counts[level] > 0).map((level) => (
          <MetaChip key={level}>
            <span aria-hidden="true">{severity(level).glyph}</span>
            {humanise(severity(level).label)} {counts[level]}
          </MetaChip>
        ))}
      </div>
    </div>
  );
}
