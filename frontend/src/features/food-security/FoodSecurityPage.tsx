/**
 * Food Security Intelligence — region-scoped.
 *
 * Two constraints shape this page:
 *
 * 1. The model operates at region level. District-level food-security output
 *    is not produced and is not inferred here; there is no validated
 *    methodology for that disaggregation.
 * 2. This is a *model early-warning signal*, not an official IPC
 *    classification. The two are separated visually and in wording, because
 *    conflating them would misrepresent an IPC phase that only the IPC
 *    Technical Working Group can assign.
 */

import { useMemo, useState } from 'react';
import { BadgeInfo, Wheat } from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import { useBoundaries } from '../../api/queries';
import { useDomainIntelligence, type IntelligenceRow } from '../../hooks/useDomainIntelligence';
import { Card } from '../../components/ui/primitives';
import {
  Drawer,
  MetaBar,
  MetaItem,
  MetricCard,
  MetricCardSkeleton,
  PageHeader,
  SectionHeader,
} from '../../components/ui/layout';
import { EmptyState, ErrorState, Note } from '../../components/ui/states';
import { IntelligenceDetail, ScopeNotice } from '../../components/intelligence/IntelligenceDetail';
import { RiskTable } from '../../components/intelligence/RiskTable';
import { SomaliaMap, type MapUnit } from '../../components/maps/SomaliaMap';
import { SeverityDistribution } from '../drought/DroughtPage';
import { domain as domainDescriptor, severity } from '../../lib/risk';
import { NOT_REPORTED, formatCount, formatProbability, humanise } from '../../lib/format';
import { formatDateTime } from '../../lib/time';

function provenanceString(row: IntelligenceRow, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = row.signal.provenance?.[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

export function FoodSecurityPage() {
  const { can } = useAuth();
  const descriptor = domainDescriptor('food_security_deterioration');

  const intelligence = useDomainIntelligence(
    'food_security_deterioration',
    can('predictions.read'),
  );
  const boundaries = useBoundaries(undefined, can('geography.read'));
  const [selected, setSelected] = useState<IntelligenceRow | null>(null);

  const mapUnits = useMemo<MapUnit[]>(
    () =>
      intelligence.ranked.map((row) => ({
        adminUnitId: row.signal.admin_unit_id,
        level: row.level,
        name: row.unitName,
        detail:
          row.probability !== null
            ? `Model signal ${formatProbability(row.probability)}`
            : 'Signal withheld',
      })),
    [intelligence.ranked],
  );

  if (!can('predictions.read')) {
    return (
      <div className="flex flex-col gap-5">
        <PageHeader eyebrow="Food security" title={descriptor.longLabel} />
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
        description="Region-level early-warning signal for food-security deterioration, derived from climate, market and environmental indicators."
        meta={
          <MetaBar>
            <MetaItem label="Regions evaluated" value={formatCount(intelligence.unitsEvaluated)} />
            <MetaItem label="Highest level" value={severity(intelligence.highest).label} />
            <MetaItem
              label="Latest signal"
              value={
                intelligence.latestAt ? formatDateTime(intelligence.latestAt) : 'Not available'
              }
            />
          </MetaBar>
        }
      />

      {/* The distinction that matters most on this page, stated first. */}
      <Note tone="caution" icon={<BadgeInfo className="size-3.5" aria-hidden="true" />}>
        <span className="font-semibold">
          This is a model early-warning signal, not an IPC classification.
        </span>{' '}
        Output on this page indicates modelled deterioration risk. It does not assign, replace or
        anticipate an official IPC phase, which only the IPC Technical Working Group can determine.
      </Note>

      <ScopeNotice domain="food_security_deterioration" />

      {/* ---- summary --------------------------------------------------- */}
      <section aria-label="Food security summary" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {intelligence.isPending ? (
          [0, 1, 2, 3].map((index) => <MetricCardSkeleton key={index} />)
        ) : (
          <>
            <MetricCard
              label={
                <span className="flex items-center gap-1.5">
                  <Wheat className="size-3.5" aria-hidden="true" />
                  Highest level
                </span>
              }
              value={
                <span className={severity(intelligence.highest).text}>
                  {severity(intelligence.highest).label}
                </span>
              }
              accent={severity(intelligence.highest).accent}
              caption="Most severe regional signal in scope"
            />
            <MetricCard
              label="Regions monitored"
              value={formatCount(intelligence.unitsEvaluated)}
              caption="Regions with a current model signal"
            />
            <MetricCard
              label="Regions at Watch+"
              value={formatCount(intelligence.watchPlus)}
              accent={intelligence.watchPlus > 0 ? 'border-l-[--color-risk-watch-solid]' : undefined}
              caption="Regions at Watch, Warning or Critical"
            />
            <MetricCard
              label="Regions at Warning+"
              value={formatCount(intelligence.warningPlus)}
              accent={
                intelligence.warningPlus > 0 ? 'border-l-[--color-risk-warning-solid]' : undefined
              }
              caption={
                intelligence.criticalCount > 0
                  ? `${formatCount(intelligence.criticalCount)} at Critical`
                  : 'No region at Critical'
              }
            />
          </>
        )}
      </section>

      {intelligence.isError && (
        <ErrorState error={intelligence.error} onRetry={intelligence.refetch} />
      )}

      {!intelligence.isError && (
        <>
          {intelligence.unitsEvaluated > 0 && (
            <Card>
              <SectionHeader
                title="Regional distribution"
                description="How the modelled signal is spread across evaluated regions"
              />
              <SeverityDistribution
                counts={intelligence.countsByLevel}
                total={intelligence.unitsEvaluated}
              />
            </Card>
          )}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <Card flush className="overflow-hidden">
              <div className="border-b border-[--color-line] px-4 py-3">
                <SectionHeader
                  className="mb-0"
                  title="Regional food-security signal"
                  description="Shading is region-level. No district-level output exists."
                />
              </div>
              {can('geography.read') ? (
                <SomaliaMap
                  boundaries={boundaries.data}
                  units={mapUnits}
                  loading={boundaries.isPending || intelligence.isPending}
                  legendTitle="Model signal"
                  scopeNote="Region-level model signal. Not an IPC classification."
                  selectedId={selected?.signal.admin_unit_id ?? null}
                  className="rounded-none ring-0"
                  height="h-[400px] sm:h-[520px]"
                  onSelectUnit={(id) => {
                    const row = intelligence.ranked.find(
                      (item) => item.signal.admin_unit_id === id,
                    );
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
              <div className="border-b border-[--color-line] px-4 py-3">
                <SectionHeader
                  className="mb-0"
                  title="Regional risk ranking"
                  description="Ordered by modelled severity"
                />
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                <RiskTable
                  rows={intelligence.ranked}
                  unitHeader="Region"
                  pending={intelligence.isPending}
                  onSelect={setSelected}
                  selectedId={selected?.signal.admin_unit_id ?? null}
                  columns={[
                    {
                      id: 'ipc',
                      header: 'IPC context',
                      render: (row) => {
                        const ipc = provenanceString(row, 'ipc_phase', 'ipc_current');
                        return ipc ? (
                          <span className="inline-flex items-center gap-1 rounded-[--radius-xs] bg-[--color-surface-sunken] px-1.5 py-0.5 text-[11px] font-medium text-[--color-ink-secondary]">
                            {humanise(ipc)}
                          </span>
                        ) : (
                          <span className="text-[--color-ink-faint]">{NOT_REPORTED}</span>
                        );
                      },
                    },
                    {
                      id: 'period',
                      header: 'Season',
                      secondary: true,
                      render: (row) => (
                        <span className="text-[--color-ink-secondary]">
                          {row.signal.target_period || NOT_REPORTED}
                        </span>
                      ),
                    },
                  ]}
                  emptyTitle="No current food-security intelligence"
                  emptyDescription="No region in your scope holds an eligible food-security signal for the current period."
                />
              </div>
            </Card>
          </div>
        </>
      )}

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.unitName ?? 'Regional intelligence'}
        description="Region-level model signal"
      >
        {selected && (
          <IntelligenceDetail
            row={selected}
            compact
            exposure={
              <div className="flex flex-col gap-2.5">
                <Note tone="neutral">
                  Food-security exposure is expressed at region level. Any district figure shown
                  elsewhere in this platform is inherited from its region and labelled as such — it
                  is never a district-model output.
                </Note>
                <p className="text-[13px] leading-5 text-[--color-ink-muted]">
                  Where the API supplies population context for this region, it appears in the
                  exposure assessment attached to an approved warning.
                </p>
              </div>
            }
          />
        )}
      </Drawer>
    </div>
  );
}
