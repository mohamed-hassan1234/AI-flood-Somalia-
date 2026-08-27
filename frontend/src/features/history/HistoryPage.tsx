/**
 * Historical Intelligence.
 *
 * Explores signals and warnings the platform has actually recorded. Every
 * series here is drawn from returned records — no interpolation, no synthetic
 * back-fill, and no chart drawn across a gap as though evidence existed there.
 */

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { History as HistoryIcon } from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useAuth } from '../../app/providers/AuthProvider';
import { useAdminUnits, useAlerts, useRiskSignals } from '../../api/queries';
import { useUrlFilters } from '../../hooks/useUrlFilters';
import { Button, Card, Input, Select, Skeleton } from '../../components/ui/primitives';
import {
  MetaBar,
  MetaItem,
  PageHeader,
  SectionHeader,
  Table,
  TableScroll,
  Td,
  Th,
} from '../../components/ui/layout';
import { EmptyState, ErrorState } from '../../components/ui/states';
import { MetaChip, RiskBadge, StatusBadge } from '../../components/intelligence/badges';
import {
  DOMAIN_ORDER,
  SEVERITY_ORDER,
  domain as domainDescriptor,
  domainLabel,
  severity,
  toSeverity,
} from '../../lib/risk';
import { formatCount, formatProbability, safeLabel } from '../../lib/format';
import { formatDate, formatDateTime, parseInstant, toDateInputValue } from '../../lib/time';
import type { RiskDomain } from '../../types/api';

export function HistoryPage() {
  const { can } = useAuth();
  const navigate = useNavigate();

  const [filters, setFilters, reset] = useUrlFilters({
    type: '',
    severity: '',
    unit: '',
    from: '',
    to: '',
  });

  const signals = useRiskSignals({ limit: 1000 }, can('predictions.read'));
  const alerts = useAlerts(can('alerts.read'));
  const units = useAdminUnits(undefined, can('geography.read'));

  const unitIndex = useMemo(() => {
    const index = new Map<string, string>();
    for (const unit of units.data ?? []) index.set(unit.id, unit.name);
    return index;
  }, [units.data]);

  const filteredSignals = useMemo(() => {
    const fromDate = filters.from ? parseInstant(`${filters.from}T00:00:00+03:00`) : null;
    const toDate = filters.to ? parseInstant(`${filters.to}T23:59:59+03:00`) : null;

    return (signals.data ?? []).filter((signal) => {
      if (filters.type && signal.domain !== filters.type) return false;
      if (filters.severity && toSeverity(signal.level) !== filters.severity) return false;
      if (filters.unit && signal.admin_unit_id !== filters.unit) return false;

      const created = parseInstant(signal.created_at);
      if (!created) return false;
      if (fromDate && created < fromDate) return false;
      if (toDate && created > toDate) return false;
      return true;
    });
  }, [signals.data, filters]);

  /**
   * Daily count of signals at Watch or above, per domain.
   *
   * Counts, not averaged probabilities: the operational contract is explicit
   * that heterogeneous per-unit probabilities must never be averaged into a
   * single national figure, because no validated methodology supports it.
   */
  const trend = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const signal of filteredSignals) {
      if (severity(signal.level).rank < 1) continue;
      const day = toDateInputValue(signal.created_at);
      if (!day) continue;
      const bucket = byDay.get(day) ?? {};
      bucket[signal.domain] = (bucket[signal.domain] ?? 0) + 1;
      byDay.set(day, bucket);
    }
    return [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, counts]) => ({ day, ...counts }));
  }, [filteredSignals]);

  const activeDomains = useMemo(() => {
    const present = new Set<RiskDomain>();
    for (const signal of filteredSignals) {
      if (severity(signal.level).rank >= 1) present.add(signal.domain);
    }
    return DOMAIN_ORDER.filter((key) => present.has(key));
  }, [filteredSignals]);

  const filteredAlerts = useMemo(() => {
    const fromDate = filters.from ? parseInstant(`${filters.from}T00:00:00+03:00`) : null;
    const toDate = filters.to ? parseInstant(`${filters.to}T23:59:59+03:00`) : null;

    return (alerts.data ?? []).filter((alert) => {
      if (filters.type && alert.risk_domain !== filters.type) return false;
      if (filters.severity && toSeverity(alert.risk_level) !== filters.severity) return false;
      if (filters.unit && alert.admin_unit_id !== filters.unit) return false;
      const created = parseInstant(alert.created_at);
      if (!created) return false;
      if (fromDate && created < fromDate) return false;
      if (toDate && created > toDate) return false;
      return true;
    });
  }, [alerts.data, filters]);

  const filtersActive = Object.values(filters).some(Boolean);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Operations"
        title="Historical Intelligence"
        description="Signals and warnings the platform has recorded. Only records the API actually returns are shown."
        meta={
          <MetaBar>
            <MetaItem label="Signals in range" value={formatCount(filteredSignals.length)} />
            <MetaItem label="Warnings in range" value={formatCount(filteredAlerts.length)} />
            <MetaItem
              label="Earliest record"
              value={
                filteredSignals.length > 0
                  ? formatDate(filteredSignals[filteredSignals.length - 1].created_at)
                  : 'None'
              }
            />
          </MetaBar>
        }
      />

      {/* ---- filters ---------------------------------------------------- */}
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[--color-ink-secondary]">Risk type</span>
            <Select
              aria-label="Filter by risk type"
              className="h-8 w-44 text-[13px]"
              value={filters.type}
              onChange={(event) => setFilters({ type: event.target.value })}
            >
              <option value="">All types</option>
              {DOMAIN_ORDER.map((key) => (
                <option key={key} value={key}>
                  {domainDescriptor(key).label}
                </option>
              ))}
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

          {(units.data?.length ?? 0) > 0 && (
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-medium text-[--color-ink-secondary]">
                Geography
              </span>
              <Select
                aria-label="Filter by administrative unit"
                className="h-8 w-48 text-[13px]"
                value={filters.unit}
                onChange={(event) => setFilters({ unit: event.target.value })}
              >
                <option value="">All units in scope</option>
                {(units.data ?? []).map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.name} ({unit.level})
                  </option>
                ))}
              </Select>
            </label>
          )}

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[--color-ink-secondary]">From</span>
            <Input
              type="date"
              aria-label="Range start date"
              className="h-8 w-40 text-[13px]"
              value={filters.from}
              max={filters.to || undefined}
              onChange={(event) => setFilters({ from: event.target.value })}
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[--color-ink-secondary]">To</span>
            <Input
              type="date"
              aria-label="Range end date"
              className="h-8 w-40 text-[13px]"
              value={filters.to}
              min={filters.from || undefined}
              onChange={(event) => setFilters({ to: event.target.value })}
            />
          </label>

          {filtersActive && (
            <Button size="sm" variant="ghost" onClick={reset}>
              Clear
            </Button>
          )}
        </div>
      </Card>

      {signals.isError && <ErrorState error={signals.error} onRetry={() => void signals.refetch()} />}

      {/* ---- trend ------------------------------------------------------ */}
      {can('predictions.read') && !signals.isError && (
        <Card>
          <SectionHeader
            title="Elevated signals over time"
            description="Count of units at Watch or above per day, by risk type. Counts are never averaged into a single national probability."
          />
          {signals.isPending ? (
            <Skeleton className="h-64 w-full" />
          ) : trend.length === 0 ? (
            <EmptyState
              compact
              icon={<HistoryIcon className="size-4.5" aria-hidden="true" />}
              title="No elevated signals in this range"
              description="No unit reached Watch or above within the selected filters."
            />
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 11, fill: 'var(--color-ink-muted)' }}
                    tickLine={false}
                    axisLine={{ stroke: 'var(--color-line)' }}
                    tickFormatter={(value: string) => formatDate(`${value}T00:00:00Z`)}
                    minTickGap={28}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: 'var(--color-ink-muted)' }}
                    tickLine={false}
                    axisLine={false}
                    label={{
                      value: 'Units at Watch+',
                      angle: -90,
                      position: 'insideLeft',
                      style: { fontSize: 11, fill: 'var(--color-ink-muted)' },
                    }}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      borderRadius: 8,
                      border: '1px solid var(--color-line)',
                      fontSize: 12,
                    }}
                    // Recharts types these callbacks with broad ReactNode/ValueType
                    // parameters, so the values are narrowed here rather than
                    // asserted at the prop boundary.
                    labelFormatter={(label) => formatDate(`${safeLabel(label)}T00:00:00Z`)}
                    formatter={(value, name) => [
                      `${Number(value)} units`,
                      domainLabel(safeLabel(name)),
                    ]}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 12 }}
                    formatter={(value) => domainLabel(safeLabel(value))}
                  />
                  {activeDomains.map((key) => (
                    <Line
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={DOMAIN_STROKE[key]}
                      strokeWidth={2}
                      dot={{ r: 2.5 }}
                      // Gaps are real: a missing day means no run, not zero risk.
                      connectNulls={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      )}

      {/* ---- signal history --------------------------------------------- */}
      {can('predictions.read') && (
        <Card flush>
          <div className="border-b border-[--color-line] px-4 py-3">
            <SectionHeader
              className="mb-0"
              title="Signal history"
              description={`${formatCount(filteredSignals.length)} records`}
            />
          </div>
          <div className="p-3">
            {signals.isPending ? (
              <Skeleton className="h-48 w-full" />
            ) : filteredSignals.length === 0 ? (
              <EmptyState
                title="No signals in this range"
                description="No risk signal matches the selected filters within your geographic scope."
              />
            ) : (
              <TableScroll>
                <Table>
                  <thead>
                    <tr>
                      <Th>Generated</Th>
                      <Th>Location</Th>
                      <Th>Risk type</Th>
                      <Th>Level</Th>
                      <Th align="right">Probability</Th>
                      <Th className="hidden lg:table-cell">Period</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSignals.slice(0, 200).map((signal) => (
                      <tr key={signal.id}>
                        <Td className="whitespace-nowrap text-[--color-ink-secondary]">
                          {formatDateTime(signal.created_at)}
                        </Td>
                        <Td className="font-medium">
                          {unitIndex.get(signal.admin_unit_id) ??
                            `Unit ${signal.admin_unit_id.slice(0, 8)}`}
                        </Td>
                        <Td>
                          <MetaChip>{domainDescriptor(signal.domain).label}</MetaChip>
                        </Td>
                        <Td>
                          <RiskBadge level={signal.level} size="sm" />
                        </Td>
                        <Td align="right" className="tabular-nums">
                          {formatProbability(signal.score)}
                        </Td>
                        <Td className="hidden text-[--color-ink-secondary] lg:table-cell">
                          {signal.target_period || '—'}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableScroll>
            )}
            {filteredSignals.length > 200 && (
              <p className="mt-3 text-[12px] text-[--color-ink-muted]">
                Showing the 200 most recent of {formatCount(filteredSignals.length)} matching
                records. Narrow the date range to see older signals.
              </p>
            )}
          </div>
        </Card>
      )}

      {/* ---- warning history -------------------------------------------- */}
      {can('alerts.read') && (
        <Card flush>
          <div className="border-b border-[--color-line] px-4 py-3">
            <SectionHeader
              className="mb-0"
              title="Warning history"
              description={`${formatCount(filteredAlerts.length)} records`}
            />
          </div>
          <div className="p-3">
            {alerts.isPending ? (
              <Skeleton className="h-40 w-full" />
            ) : filteredAlerts.length === 0 ? (
              <EmptyState
                title="No warnings in this range"
                description="No governed warning matches the selected filters."
              />
            ) : (
              <TableScroll>
                <Table>
                  <thead>
                    <tr>
                      <Th>Generated</Th>
                      <Th>Warning</Th>
                      <Th>Level</Th>
                      <Th>State</Th>
                      <Th align="right" className="hidden lg:table-cell">
                        Published
                      </Th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAlerts.slice(0, 100).map((alert) => (
                      <tr
                        key={alert.id}
                        onClick={() => navigate(`/app/warnings/${alert.id}`)}
                        className="cursor-pointer transition-colors hover:bg-[--color-surface-subtle]"
                      >
                        <Td className="whitespace-nowrap text-[--color-ink-secondary]">
                          {formatDateTime(alert.created_at)}
                        </Td>
                        <Td className="font-medium">{alert.title}</Td>
                        <Td>
                          <RiskBadge level={alert.risk_level} size="sm" />
                        </Td>
                        <Td>
                          <StatusBadge status={alert.status} size="sm" />
                        </Td>
                        <Td align="right" className="hidden whitespace-nowrap text-[--color-ink-secondary] lg:table-cell">
                          {alert.published_at ? formatDateTime(alert.published_at) : 'Not published'}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableScroll>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

/**
 * Series colours for the trend chart.
 *
 * Deliberately drawn from a neutral categorical set, not the severity scale:
 * a line here distinguishes *which domain*, and reusing severity colours would
 * suggest the drought series is somehow "green" in severity terms.
 */
const DOMAIN_STROKE: Record<RiskDomain, string> = {
  drought: '#b54708',
  river_flood: '#175cd3',
  flash_flood: '#5925dc',
  food_security_deterioration: '#0e7090',
};
