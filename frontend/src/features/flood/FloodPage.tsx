/**
 * River Flood Intelligence — gauge-scoped.
 *
 * The defining constraint of this page is that flood intelligence belongs to
 * individual river gauging stations, not to areas. Everything here is framed
 * as a station: the heading says RIVER FLOOD MONITORING, counts are counts of
 * gauges, and the map draws discrete markers rather than filled polygons.
 * Painting a district because a gauge inside it is in warning would imply an
 * inundation extent the platform does not model.
 */

import { useMemo, useState } from 'react';
import { Droplets, MapPin, Waves } from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import { useBoundaries } from '../../api/queries';
import { useDomainIntelligence, type IntelligenceRow } from '../../hooks/useDomainIntelligence';
import { Card, cx } from '../../components/ui/primitives';
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
import { DataQualityBadge, MetaChip, RiskBadge } from '../../components/intelligence/badges';
import { SomaliaMap, type MapMarker } from '../../components/maps/SomaliaMap';
import { domain as domainDescriptor, severity } from '../../lib/risk';
import {
  NOT_REPORTED,
  formatCount,
  formatProbability,
  humanise,
  renderUnknown,
} from '../../lib/format';
import { formatDateTime, formatRelative } from '../../lib/time';

/**
 * Reads a station attribute from the signal's open provenance envelope.
 * These fields originate in the Phase 03 flood record (`station_code`,
 * `river_name`, `impact_summary`). Nothing is fabricated when absent.
 */
function stationField(row: IntelligenceRow, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = row.signal.provenance?.[key];
    if (typeof value === 'string' && value.trim()) return value;
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return null;
}

function stationCoordinates(row: IntelligenceRow): { longitude: number; latitude: number } | null {
  const longitude = row.signal.provenance?.longitude;
  const latitude = row.signal.provenance?.latitude;
  if (typeof longitude === 'number' && typeof latitude === 'number') {
    return { longitude, latitude };
  }
  return null;
}

export function FloodPage() {
  const { can } = useAuth();
  const descriptor = domainDescriptor('river_flood');

  const intelligence = useDomainIntelligence('river_flood', can('predictions.read'));
  const boundaries = useBoundaries(undefined, can('geography.read'));
  const [selected, setSelected] = useState<IntelligenceRow | null>(null);

  // Only stations whose coordinates the API actually supplies can be mapped.
  // The rest remain fully available in the station table.
  const markers = useMemo<MapMarker[]>(
    () =>
      intelligence.ranked.flatMap((row) => {
        const point = stationCoordinates(row);
        if (!point) return [];
        return [
          {
            id: row.signal.admin_unit_id,
            longitude: point.longitude,
            latitude: point.latitude,
            level: row.level,
            name: stationField(row, 'station_code') ?? row.unitName,
            detail:
              row.probability !== null
                ? `Probability ${formatProbability(row.probability)}`
                : 'Probability withheld',
          },
        ];
      }),
    [intelligence.ranked],
  );

  const unmappedStations = intelligence.unitsEvaluated - markers.length;

  if (!can('predictions.read')) {
    return (
      <div className="flex flex-col gap-5">
        <PageHeader eyebrow="River flood" title={descriptor.longLabel} />
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
        eyebrow="River flood monitoring"
        title={descriptor.longLabel}
        description="Riverine early warning at supported Jubba and Shabelle gauging stations. Each signal describes conditions at its gauge."
        meta={
          <MetaBar>
            <MetaItem label="Gauges monitored" value={formatCount(intelligence.unitsEvaluated)} />
            <MetaItem label="Highest station risk" value={severity(intelligence.highest).label} />
            <MetaItem
              label="Latest signal"
              value={
                intelligence.latestAt ? formatDateTime(intelligence.latestAt) : 'Not available'
              }
            />
          </MetaBar>
        }
      />

      <ScopeNotice domain="river_flood" />

      {/* ---- summary --------------------------------------------------- */}
      <section aria-label="Flood summary" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {intelligence.isPending ? (
          [0, 1, 2, 3].map((index) => <MetricCardSkeleton key={index} />)
        ) : (
          <>
            <MetricCard
              label={
                <span className="flex items-center gap-1.5">
                  <Waves className="size-3.5" aria-hidden="true" />
                  Highest station risk
                </span>
              }
              value={
                <span className={severity(intelligence.highest).text}>
                  {severity(intelligence.highest).label}
                </span>
              }
              accent={severity(intelligence.highest).accent}
              caption="Most severe gauge currently in scope"
            />
            <MetricCard
              label="Gauges monitored"
              value={formatCount(intelligence.unitsEvaluated)}
              caption="Supported river gauging stations with a current signal"
            />
            <MetricCard
              label="Gauges at Watch+"
              value={formatCount(intelligence.watchPlus)}
              accent={intelligence.watchPlus > 0 ? 'border-l-[--color-risk-watch-solid]' : undefined}
              caption="Stations at Watch, Warning or Critical"
            />
            <MetricCard
              label="Gauges at Warning+"
              value={formatCount(intelligence.warningPlus)}
              accent={
                intelligence.warningPlus > 0 ? 'border-l-[--color-risk-warning-solid]' : undefined
              }
              caption={
                intelligence.criticalCount > 0
                  ? `${formatCount(intelligence.criticalCount)} at Critical`
                  : 'No gauge at Critical'
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
          {/* ---- map ---------------------------------------------------- */}
          <Card flush className="overflow-hidden">
            <div className="border-b border-[--color-line] px-4 py-3">
              <SectionHeader
                className="mb-0"
                title="River gauge network"
                description="Markers show individual gauging stations. Severity applies to the gauge, not the surrounding area."
              />
            </div>
            {can('geography.read') ? (
              <SomaliaMap
                boundaries={boundaries.data}
                markers={markers}
                loading={boundaries.isPending || intelligence.isPending}
                legendTitle="Station risk"
                scopeNote="Gauge-scoped. No area flood extent is modelled or implied."
                selectedId={selected?.signal.admin_unit_id ?? null}
                className="rounded-none ring-0"
                height="h-[380px] sm:h-[460px]"
                onSelectMarker={(id) => {
                  const row = intelligence.ranked.find((item) => item.signal.admin_unit_id === id);
                  if (row) setSelected(row);
                }}
                overlay={
                  unmappedStations > 0 ? (
                    <div className="pointer-events-none absolute inset-x-0 top-0 m-3">
                      <div className="pointer-events-auto rounded-[--radius-md] bg-[--color-surface] px-3 py-2 text-[12px] leading-4 text-[--color-ink-secondary] shadow-[--shadow-sm] ring-1 ring-[--color-line]">
                        <MapPin className="mr-1 inline size-3.5 align-[-2px]" aria-hidden="true" />
                        {formatCount(unmappedStations)} of{' '}
                        {formatCount(intelligence.unitsEvaluated)} gauges have no coordinates in the
                        API and cannot be placed on the map. They are listed in full below.
                      </div>
                    </div>
                  ) : undefined
                }
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

          {/* ---- station cards ----------------------------------------- */}
          <Card flush>
            <div className="border-b border-[--color-line] px-4 py-3">
              <SectionHeader
                className="mb-0"
                title="Station status"
                description={`${formatCount(intelligence.unitsEvaluated)} supported river gauges`}
              />
            </div>
            <div className="p-3">
              {intelligence.isPending ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {[0, 1, 2].map((index) => (
                    <MetricCardSkeleton key={index} />
                  ))}
                </div>
              ) : intelligence.ranked.length === 0 ? (
                <EmptyState
                  icon={<Droplets className="size-4.5" aria-hidden="true" />}
                  title="No current river flood intelligence"
                  description="No supported gauging station has an eligible signal for the current period in your scope."
                />
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {intelligence.ranked.map((row) => (
                    <StationCard key={row.signal.id} row={row} onOpen={() => setSelected(row)} />
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* ---- full table -------------------------------------------- */}
          {intelligence.ranked.length > 0 && (
            <Card flush>
              <div className="border-b border-[--color-line] px-4 py-3">
                <SectionHeader className="mb-0" title="All stations" description="Ranked by severity" />
              </div>
              <div className="p-3">
                <RiskTable
                  rows={intelligence.ranked}
                  unitHeader="Station"
                  onSelect={setSelected}
                  selectedId={selected?.signal.admin_unit_id ?? null}
                  columns={[
                    {
                      id: 'river',
                      header: 'River',
                      render: (row) => (
                        <span className="text-[--color-ink-secondary]">
                          {stationField(row, 'river_name', 'river') ?? NOT_REPORTED}
                        </span>
                      ),
                    },
                    {
                      id: 'level',
                      header: 'Level condition',
                      secondary: true,
                      render: (row) => (
                        <span className="text-[--color-ink-secondary]">
                          {humanise(stationField(row, 'level_condition')) ?? NOT_REPORTED}
                        </span>
                      ),
                    },
                  ]}
                />
              </div>
            </Card>
          )}
        </>
      )}

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={
          selected
            ? (stationField(selected, 'station_code') ?? selected.unitName)
            : 'Station intelligence'
        }
        description={selected ? (stationField(selected, 'river_name') ?? undefined) : undefined}
      >
        {selected && (
          <IntelligenceDetail
            row={selected}
            compact
            exposure={<StationExposure row={selected} />}
          />
        )}
      </Drawer>
    </div>
  );
}

/* ----------------------------------------------------------- station card -- */

function StationCard({ row, onOpen }: { row: IntelligenceRow; onOpen: () => void }) {
  const descriptor = severity(row.level);
  const code = stationField(row, 'station_code');
  const river = stationField(row, 'river_name', 'river');
  const levelCondition = stationField(row, 'level_condition');
  const rateOfRise = stationField(row, 'rate_of_rise_3d', 'rate_of_rise');
  const rainfall = stationField(row, 'antecedent_rainfall_7d', 'antecedent_rainfall');

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cx(
        'flex flex-col gap-3 rounded-[--radius-lg] border-l-[3px] bg-[--color-surface] p-4 text-left',
        'ring-1 ring-[--color-line] transition-shadow hover:shadow-[--shadow-sm] hover:ring-[--color-line-strong]',
        descriptor.accent,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold text-[--color-ink]">
            {code ?? row.unitName}
          </p>
          <p className="truncate text-[12px] text-[--color-ink-muted]">
            {river ? `${river} river` : row.unitName}
          </p>
        </div>
        <RiskBadge level={row.level} size="sm" />
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="text-[24px] font-bold leading-none tracking-[-0.03em] text-[--color-ink]">
          {formatProbability(row.probability)}
        </span>
        <span className="text-[12px] text-[--color-ink-muted]">modelled probability</span>
      </div>

      <dl className="flex flex-col gap-1 text-[12px]">
        <StationFact label="River level" value={humanise(levelCondition)} />
        <StationFact label="Rate of rise (3d)" value={humanise(rateOfRise)} />
        <StationFact label="Antecedent rainfall (7d)" value={humanise(rainfall)} />
      </dl>

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-[--color-line] pt-2.5">
        <DataQualityBadge
          size="sm"
          status={
            typeof row.signal.provenance?.data_quality === 'string'
              ? row.signal.provenance.data_quality
              : null
          }
        />
        <span
          className="text-[11px] text-[--color-ink-muted]"
          title={formatDateTime(row.signal.created_at)}
        >
          {formatRelative(row.signal.created_at)}
        </span>
      </div>
    </button>
  );
}

function StationFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-[--color-ink-muted]">{label}</dt>
      <dd
        className={cx(
          'text-right font-medium',
          value === NOT_REPORTED ? 'text-[--color-ink-faint]' : 'text-[--color-ink]',
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function StationExposure({ row }: { row: IntelligenceRow }) {
  const population = row.signal.provenance?.population_context;
  const linkedDistrict = stationField(row, 'linked_district_name');

  return (
    <div className="flex flex-col gap-2.5">
      <Note tone="neutral">
        Exposure for a gauge is reported as <strong>population context</strong> for the linked
        district — the people living near the station. It is not a count of people who would be
        flooded, because no validated inundation geometry exists for these stations.
      </Note>
      <dl className="flex flex-col gap-1.5 text-[13px]">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-[--color-ink-muted]">Population context</dt>
          <dd className="font-medium text-[--color-ink]">{renderUnknown(population)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-[--color-ink-muted]">Linked district</dt>
          <dd className="font-medium text-[--color-ink]">
            {linkedDistrict ? <MetaChip>{linkedDistrict}</MetaChip> : NOT_REPORTED}
          </dd>
        </div>
      </dl>
    </div>
  );
}
