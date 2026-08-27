/**
 * Somalia National Risk Map — the geographic explorer.
 *
 * Filters are held in the URL so a view can be shared or reproduced.
 *
 * The domain filter is what enforces scientific honesty here: selecting
 * "All domains" does not merge heterogeneous scopes into one choropleth.
 * Polygon shading always comes from a single area-scoped domain, and
 * gauge-scoped flood intelligence is always drawn as discrete markers on top.
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Info, Layers } from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import { useBoundaries } from '../../api/queries';
import { useDomainIntelligence, type IntelligenceRow } from '../../hooks/useDomainIntelligence';
import { useUrlFilters } from '../../hooks/useUrlFilters';
import { Button, Card, Select } from '../../components/ui/primitives';
import { Drawer, MetaBar, MetaItem, PageHeader, SectionHeader } from '../../components/ui/layout';
import { EmptyState, ErrorState, Note } from '../../components/ui/states';
import { IntelligenceDetail } from '../../components/intelligence/IntelligenceDetail';
import { RiskBadge } from '../../components/intelligence/badges';
import { SomaliaMap, type MapMarker, type MapUnit } from '../../components/maps/SomaliaMap';
import {
  SEVERITY_ORDER,
  domain as domainDescriptor,
  severity,
} from '../../lib/risk';
import { formatCount, formatProbability } from '../../lib/format';

type MapDomain = 'drought' | 'food_security_deterioration';

export function RiskMapPage() {
  const { can } = useAuth();
  const navigate = useNavigate();

  const [filters, setFilters, reset] = useUrlFilters({
    type: 'drought',
    severity: '',
    flood: 'on',
  });

  const boundaries = useBoundaries(undefined, can('geography.read'));
  const mayReadPredictions = can('predictions.read');

  const drought = useDomainIntelligence('drought', mayReadPredictions);
  const foodSecurity = useDomainIntelligence('food_security_deterioration', mayReadPredictions);
  const flood = useDomainIntelligence('river_flood', mayReadPredictions);

  const [selected, setSelected] = useState<IntelligenceRow | null>(null);

  const areaDomain: MapDomain =
    filters.type === 'food_security_deterioration' ? 'food_security_deterioration' : 'drought';
  const areaSource = areaDomain === 'drought' ? drought : foodSecurity;

  const filteredRows = useMemo(
    () =>
      areaSource.ranked.filter(
        (row) => !filters.severity || row.level === filters.severity,
      ),
    [areaSource.ranked, filters.severity],
  );

  const units = useMemo<MapUnit[]>(
    () =>
      filteredRows.map((row) => ({
        adminUnitId: row.signal.admin_unit_id,
        level: row.level,
        name: row.unitName,
        detail:
          row.probability !== null
            ? `Probability ${formatProbability(row.probability)}`
            : 'Probability withheld',
      })),
    [filteredRows],
  );

  const markers = useMemo<MapMarker[]>(() => {
    if (filters.flood !== 'on') return [];
    return flood.ranked.flatMap((row) => {
      const longitude = row.signal.provenance?.longitude;
      const latitude = row.signal.provenance?.latitude;
      if (typeof longitude !== 'number' || typeof latitude !== 'number') return [];
      if (filters.severity && row.level !== filters.severity) return [];
      return [
        {
          id: row.signal.admin_unit_id,
          longitude,
          latitude,
          level: row.level,
          name:
            typeof row.signal.provenance?.station_code === 'string'
              ? row.signal.provenance.station_code
              : row.unitName,
          detail:
            row.probability !== null
              ? `Probability ${formatProbability(row.probability)}`
              : 'Probability withheld',
        },
      ];
    });
  }, [flood.ranked, filters.flood, filters.severity]);

  if (!can('geography.read')) {
    return (
      <div className="flex flex-col gap-5">
        <PageHeader eyebrow="Geography" title="Somalia Risk Map" />
        <EmptyState
          title="Map unavailable for your role"
          description="Displaying administrative boundaries requires the geography read capability."
        />
      </div>
    );
  }

  const areaDescriptor = domainDescriptor(areaDomain);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Geography"
        title="Somalia National Risk Map"
        description="Explore modelled risk across administrative geography. Each domain is drawn only at the scope it is modelled at."
        meta={
          <MetaBar>
            <MetaItem
              label="Boundary version"
              value={
                boundaries.data?.features[0]?.properties?.boundary_version
                  ? String(boundaries.data.features[0].properties.boundary_version)
                  : 'Not reported'
              }
            />
            <MetaItem label="Units shaded" value={formatCount(units.length)} />
            <MetaItem label="Gauges shown" value={formatCount(markers.length)} />
          </MetaBar>
        }
      />

      <Note tone="neutral" icon={<Info className="size-3.5" aria-hidden="true" />}>
        <span className="font-semibold text-[--color-ink]">How to read this map. </span>
        Shaded areas show <strong>{areaDescriptor.label.toLowerCase()}</strong> risk at{' '}
        {areaDescriptor.scope} level. Circular markers are individual river gauges — their severity
        describes conditions at the gauge and does not imply a flooded area. Domains are never
        merged into a single combined score.
      </Note>

      <Card flush className="overflow-hidden">
        <div className="flex flex-wrap items-end gap-3 border-b border-[--color-line] p-3 sm:p-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[--color-ink-secondary]">
              Area shading
            </span>
            <Select
              aria-label="Area risk domain"
              className="h-8 w-52 text-[13px]"
              value={areaDomain}
              onChange={(event) => setFilters({ type: event.target.value })}
            >
              <option value="drought">Drought (district)</option>
              <option value="food_security_deterioration">Food security (region)</option>
            </Select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[--color-ink-secondary]">Severity</span>
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

          <label className="flex h-8 items-center gap-2 self-end">
            <input
              type="checkbox"
              checked={filters.flood === 'on'}
              onChange={(event) => setFilters({ flood: event.target.checked ? 'on' : 'off' })}
              className="size-4 rounded-[3px] accent-[--color-brand-600]"
            />
            <span className="text-[13px] font-medium text-[--color-ink-secondary]">
              Show river gauges
            </span>
          </label>

          <Button size="sm" variant="ghost" className="ml-auto" onClick={reset}>
            <Layers className="size-3.5" aria-hidden="true" />
            Reset view
          </Button>
        </div>

        {mayReadPredictions ? (
          <SomaliaMap
            boundaries={boundaries.data}
            units={units}
            markers={markers}
            loading={boundaries.isPending || areaSource.isPending}
            legendTitle={`${areaDescriptor.label} risk`}
            scopeNote={areaDescriptor.scopeStatement}
            selectedId={selected?.signal.admin_unit_id ?? null}
            className="rounded-none ring-0"
            height="h-[440px] sm:h-[560px] xl:h-[640px]"
            onSelectUnit={(id) => {
              const row = areaSource.ranked.find((item) => item.signal.admin_unit_id === id);
              if (row) setSelected(row);
            }}
            onSelectMarker={(id) => {
              const row = flood.ranked.find((item) => item.signal.admin_unit_id === id);
              if (row) setSelected(row);
            }}
          />
        ) : (
          <div className="p-4">
            <EmptyState
              title="Risk shading unavailable for your role"
              description="Boundaries are shown without risk shading because reading modelled risk requires the predictions read capability."
            />
          </div>
        )}
      </Card>

      {boundaries.isError && (
        <ErrorState error={boundaries.error} onRetry={() => void boundaries.refetch()} />
      )}
      {areaSource.isError && (
        <ErrorState error={areaSource.error} onRetry={areaSource.refetch} />
      )}

      {/* Compact list mirroring the map, so the information is reachable
          without a pointer and readable when the renderer is unavailable. */}
      {filteredRows.length > 0 && (
        <Card>
          <SectionHeader
            title={`${areaDescriptor.label} risk by ${areaDescriptor.unitNoun}`}
            description="The same data shown on the map, in rank order"
          />
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {filteredRows.slice(0, 24).map((row) => (
              <li key={row.signal.id}>
                <button
                  type="button"
                  onClick={() => setSelected(row)}
                  className="flex w-full items-center justify-between gap-3 rounded-[--radius-md] bg-[--color-surface-subtle] px-3 py-2 text-left ring-1 ring-[--color-line] transition-colors hover:bg-[--color-surface-sunken]"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium text-[--color-ink]">
                      {row.unitName}
                    </span>
                    {row.parentName && (
                      <span className="block truncate text-[11px] text-[--color-ink-muted]">
                        {row.parentName}
                      </span>
                    )}
                  </span>
                  <RiskBadge level={row.level} size="sm" />
                </button>
              </li>
            ))}
          </ul>
          {filteredRows.length > 24 && (
            <p className="mt-3 text-[12px] text-[--color-ink-muted]">
              Showing 24 of {formatCount(filteredRows.length)}.{' '}
              <button
                type="button"
                onClick={() =>
                  navigate(areaDomain === 'drought' ? '/app/drought' : '/app/food-security')
                }
                className="font-medium text-[--color-brand-700] underline underline-offset-2"
              >
                Open the full {areaDescriptor.label.toLowerCase()} page
              </button>
              .
            </p>
          )}
        </Card>
      )}

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.unitName ?? 'Intelligence'}
        description={selected ? domainDescriptor(selected.signal.domain).label : undefined}
        footer={
          selected && (
            <Button
              variant="primary"
              fullWidth
              onClick={() => {
                const target =
                  selected.signal.domain === 'drought'
                    ? '/app/drought'
                    : selected.signal.domain === 'food_security_deterioration'
                      ? '/app/food-security'
                      : '/app/flood';
                void navigate(target);
              }}
            >
              View full intelligence
            </Button>
          )
        }
      >
        {selected && <IntelligenceDetail row={selected} compact />}
      </Drawer>
    </div>
  );
}
